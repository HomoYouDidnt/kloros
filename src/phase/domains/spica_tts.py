"""
SPICA Derivative: Text-to-Speech Quality & Performance

SPICA-based TTS testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Voice quality (spectral clarity + transcription naturalness)
- Latency (first-token, total generation)
- Consistency (same input → similar output via audio fingerprinting)
- Resource usage (CPU, memory during generation)

KPIs: clarity_score, transcript_naturalness, consistency_score, latency_p50, latency_p95
"""
import time
import hashlib
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result


@dataclass
class TTSVariant:
    """D-REAM evolvable TTS variant configuration."""
    backend: str = "piper"
    voice: str = "en_US-amy"
    speed: float = 1.0
    pitch: float = 0.0
    prosody: float = 0.0
    seed: int = 1337
    anneal_temp: float = 1.0  # Temperature annealing for exploration→exploitation


def _sanitize_variant(v: TTSVariant) -> TTSVariant:
    """
    Safety clamps on evolvable knobs to prevent out-of-range synth states.

    Avoids weird synthesis failures under high temperature exploration.
    """
    v.speed = float(np.clip(v.speed, 0.6, 1.5))
    v.pitch = float(np.clip(v.pitch, -6.0, 6.0))
    v.prosody = float(np.clip(v.prosody, 0.0, 1.5))
    v.anneal_temp = float(np.clip(v.anneal_temp, 0.0, 1.0))
    return v


def _annealed_latency_targets(
    epoch: int,
    T_first0: float = 140.0,  # Initial first-token target (ms)
    T_total0: float = 650.0,  # Initial total latency target (ms)
    floor_first: float = 90.0,  # Final first-token floor (ms)
    floor_total: float = 500.0  # Final total latency floor (ms)
) -> Tuple[float, float]:
    """
    Tighten latency targets over epochs for free speed gains.

    Gently shifts pressure toward faster voices as training stabilizes.
    Fully tight by ~40 epochs.

    Args:
        epoch: Current epoch number
        T_first0: Initial first-token latency target (ms)
        T_total0: Initial total latency target (ms)
        floor_first: Minimum first-token latency floor (ms)
        floor_total: Minimum total latency floor (ms)

    Returns:
        (first_token_target_ms, total_latency_target_ms)
    """
    k = min(1.0, epoch / 40.0)  # Linear progression to epoch 40
    T_first = max(floor_first, T_first0 - 40.0 * k)
    T_total = max(floor_total, T_total0 - 150.0 * k)
    return T_first, T_total


@dataclass
class TTSTestConfig:
    """Configuration for TTS domain tests."""
    backends: List[str] = None
    test_texts: List[str] = None
    target_voices: List[str] = None
    max_latency_ms: int = 5000
    max_memory_mb: int = 2048
    max_cpu_percent: int = 80

    # D-REAM evolvable fitness weights (must sum to ~1.0)
    fitness_weight_clarity: float = 0.30       # Spectral clarity score
    fitness_weight_transcript: float = 0.30    # Transcription naturalness
    fitness_weight_consistency: float = 0.20   # Audio fingerprint stability
    fitness_weight_latency: float = 0.10       # Generation speed bonus
    fitness_weight_resource: float = 0.10      # CPU/memory efficiency

    # Quality thresholds
    min_clarity_score: float = 0.4
    min_transcript_naturalness: float = 0.5

    # Annealing experiment settings
    anneal_temps: List[float] = field(default_factory=lambda: [1.0])

    def __post_init__(self):
        if self.backends is None:
            self.backends = ["mock"]
        if self.test_texts is None:
            self.test_texts = [
                "Hello, I am KLoROS.",
                "The quick brown fox jumps over the lazy dog.",
                "Testing synthesis quality with a longer sentence that includes varied phonemes."
            ]
        if self.target_voices is None:
            self.target_voices = ["glados_piper_medium"]


@dataclass
class TTSTestResult:
    """Results from a single TTS test."""
    test_id: str
    backend: str
    voice: str
    text_hash: str
    status: str
    latency_ms: float
    first_token_ms: Optional[float]
    audio_duration_sec: float
    audio_hash: str

    # Multi-objective quality metrics
    clarity_score: float                # Spectral clarity (0.0-1.0)
    transcript_score: float             # Transcription naturalness (0.0-1.0)
    transcript_text: str                # Actual transcription
    consistency_score: float            # Audio fingerprint stability (0.0-1.0)
    temperature_used: float             # Annealing temperature used

    # Legacy compatibility
    mos_estimate: Optional[float] = None

    cpu_percent: float = 0.0
    memory_mb: float = 0.0


def _ensure_sr_i16(pcm_i16: np.ndarray, src_sr: int, dst_sr: int) -> bytes:
    """
    Resample audio to target sample rate if needed.

    Ensures metrics are apples-to-apples when TTS backends return different rates.
    Uses linear interpolation (cheap, sufficient for metrics).

    Args:
        pcm_i16: Input audio as int16 samples
        src_sr: Source sample rate
        dst_sr: Destination sample rate

    Returns:
        Resampled audio as int16 bytes
    """
    if src_sr == dst_sr:
        return pcm_i16.astype("<i2").tobytes()

    # Convert to float32 for resampling
    x = pcm_i16.astype(np.float32) / 32768.0

    # Linear resample
    n = int(len(x) * (dst_sr / src_sr))
    t = np.linspace(0, 1, len(x), endpoint=False)
    ti = np.linspace(0, 1, n, endpoint=False)
    y = np.interp(ti, t, x)

    # Clip and convert back to int16
    y = np.clip(y, -0.999, 0.999)
    return (y * 32767.0).astype("<i2").tobytes()


def _spectral_clarity_score(audio_bytes: bytes, sr: int = 22050) -> float:
    """
    Fast audio quality gate + spectral clarity heuristic.

    Returns 0.0-1.0 score based on:
    1. Speech-band energy (300-3400Hz)
    2. Temporal modulation (avoid flat/droning audio)

    This is a heuristic proxy. Upgrade path: swap for real speech quality model
    (e.g., DNSMOS, NISQA) when compute budget allows.
    """
    try:
        # Fast prefilter: silence/clipping/corruption
        if len(audio_bytes) < 1000:
            return 0.0

        # Convert bytes to int16 samples
        pcm_i16 = np.frombuffer(audio_bytes[:(len(audio_bytes)//2)*2], dtype="<i2")
        if len(pcm_i16) < sr // 10:  # Less than 100ms
            return 0.0

        # Check for silence (too many near-zero samples)
        nonzero = np.sum(np.abs(pcm_i16) > 100)
        if nonzero < len(pcm_i16) * 0.1:
            return 0.1

        # Check for clipping
        clipped = np.sum(np.abs(pcm_i16) > 30000)
        if clipped > len(pcm_i16) * 0.05:
            return 0.2

        # Convert to float32 [-1, 1]
        audio_f32 = pcm_i16.astype(np.float32) / 32768.0

        # Compute FFT for spectral analysis
        fft = np.fft.rfft(audio_f32)
        freqs = np.fft.rfftfreq(len(audio_f32), 1.0 / sr)
        magnitude = np.abs(fft)

        # Speech-band energy (300-3400 Hz)
        speech_mask = (freqs >= 300) & (freqs <= 3400)
        speech_energy = np.sum(magnitude[speech_mask])
        total_energy = np.sum(magnitude) + 1e-9
        speech_ratio = speech_energy / total_energy

        # Temporal modulation (detect flat/droning audio)
        # Split into 100ms windows, measure energy variance
        window_size = sr // 10
        num_windows = len(audio_f32) // window_size
        if num_windows > 1:
            windows = audio_f32[:num_windows * window_size].reshape(num_windows, window_size)
            window_energies = np.sum(windows**2, axis=1)
            energy_std = np.std(window_energies)
            temporal_score = np.clip(energy_std * 10, 0.0, 1.0)
        else:
            temporal_score = 0.5

        # Combine metrics: 70% speech-band, 30% temporal modulation
        clarity = 0.7 * speech_ratio + 0.3 * temporal_score

        return float(np.clip(clarity, 0.0, 1.0))

    except Exception as e:
        # Fallback for corrupted audio
        return 0.0


# Whisper singleton to avoid repeated model loading
_WHISPER = None


def _lazy_whisper():
    """Lazy-load Whisper backend singleton."""
    global _WHISPER
    if _WHISPER is None:
        from src.stt.whisper_backend import WhisperSttBackend
        _WHISPER = WhisperSttBackend(model_size="tiny", device="cpu")
    return _WHISPER


def _simple_vad_trim(pcm_f32: np.ndarray, sr: int) -> np.ndarray:
    """
    Energy-based VAD trim to remove leading/trailing silence.

    Cheap alternative to full VAD - avoids pulling in extra dependencies.
    Uses RMS energy with adaptive threshold based on median.
    """
    frm = max(256, int(0.02 * sr))  # ~20ms frames
    hop = frm // 2

    if pcm_f32.size < frm:
        return pcm_f32

    # Compute RMS energy for each frame
    rms = []
    for i in range(0, pcm_f32.size - frm + 1, hop):
        seg = pcm_f32[i:i+frm]
        rms.append(float(np.sqrt(np.mean(seg**2) + 1e-12)))

    rms = np.array(rms)

    # Adaptive threshold: 35% of median RMS
    thr = max(0.01, 0.35 * float(np.median(rms)))

    # Find active frames (above threshold)
    active = np.where(rms > thr)[0]
    if active.size == 0:
        return pcm_f32

    # Extract with 5-frame margin
    m = 5  # frames of margin
    start = max(0, (active[0] - m) * hop)
    end = min(pcm_f32.size, (active[-1] + m) * hop + frm)

    return pcm_f32[start:end]


def _transcribe_text(audio_bytes: bytes, sample_rate: int = 22050) -> str:
    """
    Convert int16 PCM → float32 for Whisper transcription.

    Uses singleton Whisper instance and VAD trimming to reduce cost.
    Returns transcription text or empty string on failure.
    """
    try:
        # Convert bytes to int16 samples
        pcm_i16 = np.frombuffer(audio_bytes[:(len(audio_bytes)//2)*2], dtype="<i2")
        if pcm_i16.size == 0:
            return ""

        # Convert to float32 [-1, 1] as required by Whisper
        audio_f32 = pcm_i16.astype(np.float32) / 32768.0

        # Trim silence before transcription (cuts STT cost)
        audio_f32 = _simple_vad_trim(audio_f32, sample_rate)

        # Use singleton Whisper backend
        backend = _lazy_whisper()

        # Transcribe
        result = backend.transcribe(audio_f32.copy(), sample_rate)

        # Extract text (handle both SttResult object and dict)
        text = getattr(result, "text", "") or ""
        return text.strip()

    except Exception:
        # Whisper not available or transcription failed
        return ""


class TTSEvaluator:
    """
    Multi-objective TTS fitness evaluator with 5 components:

    1. Clarity (30%): Spectral clarity + temporal modulation
    2. Transcript (30%): Transcription naturalness (Whisper + heuristics)
    3. Consistency (20%): Audio fingerprint stability (same input → same output)
    4. Latency (10%): Generation speed bonus
    5. Resource (10%): CPU/memory efficiency

    Temperature annealing: High temp (exploration) gets diversity bonus for non-determinism.
    """

    def __init__(self, weights: Dict[str, float] | None = None, target_sr: int = 22050):
        self.weights = weights or {
            "clarity": 0.30,
            "transcript": 0.30,
            "consistency": 0.20,
            "latency": 0.10,
            "resource": 0.10
        }
        self.target_sr = target_sr
        self.audio_cache: Dict[str, List[bytes]] = {}  # For consistency checks

    def evaluate(
        self,
        text: str,
        v: TTSVariant,
        audio_bytes: bytes,
        latency_ms: float,
        cpu_pct: float,
        mem_mb: float,
        repeats: int = 2,
        max_latency_ms: int = 5000,
        max_memory_mb: int = 2048
    ) -> Dict[str, Any]:
        """
        Evaluate TTS output with multi-objective fitness.

        Args:
            text: Input text that was synthesized
            v: TTS variant configuration
            audio_bytes: Raw audio output (int16 PCM)
            latency_ms: Generation time in milliseconds
            cpu_pct: CPU usage percentage
            mem_mb: Memory usage in MB
            repeats: Number of times to synthesize for consistency check
            max_latency_ms: Maximum acceptable latency
            max_memory_mb: Maximum acceptable memory

        Returns:
            Dict with fitness, components, and detailed metrics
        """
        # 1. Clarity score (spectral analysis)
        clarity = _spectral_clarity_score(audio_bytes, self.target_sr)

        # 2. Transcript score (Whisper + naturalness heuristics)
        transcript = _transcribe_text(audio_bytes, self.target_sr)

        # Naturalness heuristics:
        # - Penalize empty transcription
        # - Penalize very short transcription (likely garbled)
        # - Reward length match (transcript should be similar length to input)
        if not transcript:
            transcript_score = 0.0
        else:
            len_ratio = len(transcript) / max(1, len(text))
            len_score = 1.0 - abs(1.0 - len_ratio)  # Penalize mismatch
            len_score = np.clip(len_score, 0.0, 1.0)

            # Minimum length threshold
            if len(transcript) < 3:
                transcript_score = 0.2
            else:
                transcript_score = len_score

        # 3. Consistency score (audio fingerprint stability)
        cache_key = f"{v.backend}_{v.voice}_{v.speed}_{hashlib.sha256(text.encode()).hexdigest()[:8]}"

        if cache_key not in self.audio_cache:
            self.audio_cache[cache_key] = []

        self.audio_cache[cache_key].append(audio_bytes)

        # Compare with previous generations (if any)
        if len(self.audio_cache[cache_key]) > 1:
            # SHA1 fingerprint distance
            hashes = [hashlib.sha1(ab).hexdigest() for ab in self.audio_cache[cache_key][-repeats:]]

            # Count unique hashes
            unique_count = len(set(hashes))

            # Perfect consistency: all hashes identical
            # Poor consistency: all hashes different
            consistency_score = 1.0 - (unique_count - 1) / max(1, repeats - 1)
        else:
            # First generation: assume perfect consistency
            consistency_score = 1.0

        # 4. Latency score (normalized bonus)
        latency_normalized = 1.0 - min(1.0, latency_ms / max_latency_ms)

        # 5. Resource score (CPU + memory efficiency)
        cpu_normalized = 1.0 - min(1.0, cpu_pct / 100.0)
        mem_normalized = 1.0 - min(1.0, mem_mb / max_memory_mb)
        resource_score = (cpu_normalized + mem_normalized) / 2.0

        # Weighted combination
        clarity_component = self.weights["clarity"] * clarity
        transcript_component = self.weights["transcript"] * transcript_score
        consistency_component = self.weights["consistency"] * consistency_score
        latency_component = self.weights["latency"] * latency_normalized
        resource_component = self.weights["resource"] * resource_score

        base_fitness = (
            clarity_component +
            transcript_component +
            consistency_component +
            latency_component +
            resource_component
        )

        # Temperature annealing diversity bonus
        # High temp exploration gets bonus for generating diverse outputs
        diversity_bonus = 0.0
        if v.anneal_temp > 0.2 and len(self.audio_cache[cache_key]) > 1:
            # Measure clarity variance across recent generations
            clarity_vals = [_spectral_clarity_score(ab, self.target_sr)
                          for ab in self.audio_cache[cache_key][-repeats:]]
            cstd = float(np.std(clarity_vals))

            # Bonus scales with temp and diversity (capped at 0.05)
            diversity_bonus = np.clip(cstd, 0.0, 0.05) * min(1.0, v.anneal_temp)

        fitness = base_fitness + diversity_bonus
        fitness = float(np.clip(fitness, 0.0, 1.0))

        # Gate reason (why quality gate passed/failed)
        gate_reason = "ok"
        if len(audio_bytes) < 1000:
            gate_reason = "too_short"
        elif clarity < 0.1:
            gate_reason = "silent"
        elif clarity < 0.2:
            gate_reason = "clipped"
        elif not transcript:
            gate_reason = "no_transcript"

        return {
            "fitness": fitness,
            "components": {
                "clarity": clarity_component,
                "transcript": transcript_component,
                "consistency": consistency_component,
                "latency": latency_component,
                "resource": resource_component,
                "diversity_bonus": diversity_bonus
            },
            "raw_scores": {
                "clarity": clarity,
                "transcript_score": transcript_score,
                "transcript_text": transcript,
                "consistency": consistency_score,
                "latency_normalized": latency_normalized,
                "resource_score": resource_score
            },
            # Enhanced telemetry for PHASE dashboards
            "stats": {
                "tts_backend": v.backend,
                "voice": v.voice,
                "speed": v.speed,
                "pitch": v.pitch,
                "prosody": v.prosody,
                "seed": v.seed,
                "anneal_temp": v.anneal_temp,
                "sr": self.target_sr,
                "gate_reason": gate_reason,
                "audio_len_bytes": len(audio_bytes),
                "transcript_len": len(transcript),
                "latency_ms": latency_ms,
                "cpu_pct": cpu_pct,
                "mem_mb": mem_mb,
                "unique_hashes": len(set([hashlib.sha1(ab).hexdigest()
                                         for ab in self.audio_cache[cache_key][-repeats:]]))
                                if cache_key in self.audio_cache and len(self.audio_cache[cache_key]) > 0 else 1
            }
        }


class SpicaTTS(SpicaBase):
    """SPICA derivative for TTS quality and performance testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[TTSTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-tts-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'backends': test_config.backends,
                'test_texts': test_config.test_texts,
                'target_voices': test_config.target_voices,
                'max_latency_ms': test_config.max_latency_ms,
                'max_memory_mb': test_config.max_memory_mb,
                'max_cpu_percent': test_config.max_cpu_percent,
                # Fitness weights (evolvable by D-REAM)
                'fitness_weight_clarity': test_config.fitness_weight_clarity,
                'fitness_weight_transcript': test_config.fitness_weight_transcript,
                'fitness_weight_consistency': test_config.fitness_weight_consistency,
                'fitness_weight_latency': test_config.fitness_weight_latency,
                'fitness_weight_resource': test_config.fitness_weight_resource,
                # Quality thresholds
                'min_clarity_score': test_config.min_clarity_score,
                'min_transcript_naturalness': test_config.min_transcript_naturalness
            })

        super().__init__(spica_id=spica_id, domain="tts", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or TTSTestConfig()
        self.results: List[TTSTestResult] = []

        # Initialize TTSEvaluator with config weights
        self.evaluator = TTSEvaluator(weights={
            "clarity": self.test_config.fitness_weight_clarity,
            "transcript": self.test_config.fitness_weight_transcript,
            "consistency": self.test_config.fitness_weight_consistency,
            "latency": self.test_config.fitness_weight_latency,
            "resource": self.test_config.fitness_weight_resource
        })

        self.record_telemetry("spica_tts_init", {
            "backends": self.test_config.backends,
            "test_texts_count": len(self.test_config.test_texts),
            "target_voices_count": len(self.test_config.target_voices),
            "fitness_weights": {
                "clarity": self.test_config.fitness_weight_clarity,
                "transcript": self.test_config.fitness_weight_transcript,
                "consistency": self.test_config.fitness_weight_consistency,
                "latency": self.test_config.fitness_weight_latency,
                "resource": self.test_config.fitness_weight_resource
            }
        })

    def _hash_text(self, text: str) -> str:
        """Generate deterministic hash of input text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _hash_audio(self, audio_bytes: bytes) -> str:
        """Generate deterministic hash of audio output."""
        return hashlib.sha256(audio_bytes).hexdigest()[:16]

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """
        SPICA evaluate() with multi-objective fitness calculation.

        Fitness components:
        - Clarity (30%): Spectral clarity + temporal modulation
        - Transcript (30%): Transcription naturalness (Whisper + heuristics)
        - Consistency (20%): Audio fingerprint stability
        - Latency (10%): Generation speed bonus
        - Resource (10%): CPU/memory efficiency

        Returns fitness in [0, 1] range with detailed breakdown.
        """
        backend = test_input.get("backend", self.test_config.backends[0])
        voice = test_input.get("voice", self.test_config.target_voices[0])
        text = test_input.get("text", self.test_config.test_texts[0])
        anneal_temp = test_input.get("anneal_temp", 1.0)
        epoch_id = (context or {}).get("epoch_id", "unknown")

        result = self.run_test(backend, voice, text, epoch_id, anneal_temp=anneal_temp)

        # Multi-objective fitness calculation (already computed in run_test via evaluator)
        # But we reconstruct components for clarity and transparency
        clarity_component = self.test_config.fitness_weight_clarity * result.clarity_score
        transcript_component = self.test_config.fitness_weight_transcript * result.transcript_score
        consistency_component = self.test_config.fitness_weight_consistency * result.consistency_score

        # Latency normalized (faster = better)
        latency_normalized = 1.0 - min(1.0, result.latency_ms / self.test_config.max_latency_ms)
        latency_component = self.test_config.fitness_weight_latency * latency_normalized

        # Resource efficiency
        cpu_normalized = 1.0 - min(1.0, result.cpu_percent / 100.0)
        mem_normalized = 1.0 - min(1.0, result.memory_mb / self.test_config.max_memory_mb)
        resource_score = (cpu_normalized + mem_normalized) / 2.0
        resource_component = self.test_config.fitness_weight_resource * resource_score

        # Combine components
        fitness = (
            clarity_component +
            transcript_component +
            consistency_component +
            latency_component +
            resource_component
        )

        # Clamp to [0, 1]
        fitness = max(0.0, min(1.0, fitness))

        # Record detailed fitness breakdown for D-REAM analysis
        self.record_telemetry("fitness_calculated", {
            "fitness": fitness,
            "clarity_component": clarity_component,
            "transcript_component": transcript_component,
            "consistency_component": consistency_component,
            "latency_component": latency_component,
            "resource_component": resource_component,
            "latency_normalized": latency_normalized,
            "resource_score": resource_score,
            "test_id": result.test_id
        })

        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id,
            # Include fitness breakdown for D-REAM analysis
            "fitness_breakdown": {
                "clarity": clarity_component,
                "transcript": transcript_component,
                "consistency": consistency_component,
                "latency": latency_component,
                "resource": resource_component
            }
        }

    def run_test(self, backend: str, voice: str, text: str, epoch_id: str, anneal_temp: float = 1.0) -> TTSTestResult:
        """Execute single TTS test with multi-objective evaluation."""
        test_id = f"tts::{backend}::{voice[:20]}::{self._hash_text(text)}"

        try:
            # Lazy import to avoid dependency issues at module load time
            import tempfile
            import resource

            # This may fail if TTS backend dependencies aren't installed
            try:
                from src.tts.base import create_tts_backend
            except ImportError as e:
                # TTS dependencies not available, return graceful failure
                self.record_telemetry("tts_backend_unavailable", {"error": str(e)})
                result = TTSTestResult(
                    test_id=test_id, backend=backend, voice=voice,
                    text_hash=self._hash_text(text), status="fail",
                    latency_ms=0.0, first_token_ms=None, audio_duration_sec=0.0,
                    audio_hash="",
                    clarity_score=0.0, transcript_score=0.0, transcript_text="",
                    consistency_score=0.0, temperature_used=anneal_temp,
                    mos_estimate=None, cpu_percent=0.0, memory_mb=0.0
                )
                self.results.append(result)
                self.record_telemetry("test_skipped", {"test_id": test_id, "reason": "dependencies_missing"})
                return result

            start = time.time()

            tts_backend = create_tts_backend(backend)
            self.record_telemetry("tts_backend_created", {"backend": backend})

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    result_obj = tts_backend.synthesize(
                        text,
                        sample_rate=22050,
                        out_dir=tmp_dir,
                        basename="phase_test"
                    )

                    with open(result_obj.audio_path, 'rb') as f:
                        audio_bytes = f.read()

                    audio_duration_sec = result_obj.duration_s
                    first_token_ms = None
            except RuntimeError as synth_error:
                # TTS synthesis failed (missing model, etc.)
                self.record_telemetry("tts_synthesis_failed", {"error": str(synth_error)})
                result = TTSTestResult(
                    test_id=test_id, backend=backend, voice=voice,
                    text_hash=self._hash_text(text), status="fail",
                    latency_ms=0.0, first_token_ms=None, audio_duration_sec=0.0,
                    audio_hash="",
                    clarity_score=0.0, transcript_score=0.0, transcript_text="",
                    consistency_score=0.0, temperature_used=anneal_temp,
                    mos_estimate=None, cpu_percent=0.0, memory_mb=0.0
                )
                self.results.append(result)
                self.record_telemetry("test_skipped", {"test_id": test_id, "reason": "synthesis_failed"})
                return result

            latency_ms = (time.time() - start) * 1000

            usage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_percent = 0.0
            memory_mb = usage.ru_maxrss / 1024

            audio_hash = self._hash_audio(audio_bytes)

            # Create TTSVariant for evaluation
            variant = TTSVariant(
                backend=backend,
                voice=voice,
                speed=1.0,
                pitch=0.0,
                prosody=0.0,
                seed=1337,
                anneal_temp=anneal_temp
            )

            # Apply safety clamps to prevent out-of-range parameters
            variant = _sanitize_variant(variant)

            # Use TTSEvaluator for multi-objective quality assessment
            eval_result = self.evaluator.evaluate(
                text=text,
                v=variant,
                audio_bytes=audio_bytes,
                latency_ms=latency_ms,
                cpu_pct=cpu_percent,
                mem_mb=memory_mb,
                repeats=2,
                max_latency_ms=self.test_config.max_latency_ms,
                max_memory_mb=self.test_config.max_memory_mb
            )

            # Extract scores from evaluator
            clarity_score = eval_result["raw_scores"]["clarity"]
            transcript_score = eval_result["raw_scores"]["transcript_score"]
            transcript_text = eval_result["raw_scores"]["transcript_text"]
            consistency_score = eval_result["raw_scores"]["consistency"]

            self.record_telemetry("tts_synthesis_complete", {
                "backend": backend,
                "latency_ms": latency_ms,
                "audio_duration_sec": audio_duration_sec,
                "clarity_score": clarity_score,
                "transcript_score": transcript_score,
                "consistency_score": consistency_score,
                "transcript": transcript_text[:50]
            })

            # Multi-factor pass criteria
            status = "pass"
            if latency_ms > self.test_config.max_latency_ms:
                status = "fail"
            if memory_mb > self.test_config.max_memory_mb:
                status = "fail"
            if cpu_percent > self.test_config.max_cpu_percent:
                status = "fail"
            if clarity_score < self.test_config.min_clarity_score:
                status = "fail"
            if transcript_score < self.test_config.min_transcript_naturalness:
                status = "fail"

            result = TTSTestResult(
                test_id=test_id, backend=backend, voice=voice,
                text_hash=self._hash_text(text), status=status,
                latency_ms=latency_ms, first_token_ms=first_token_ms,
                audio_duration_sec=audio_duration_sec, audio_hash=audio_hash,
                clarity_score=clarity_score,
                transcript_score=transcript_score,
                transcript_text=transcript_text,
                consistency_score=consistency_score,
                temperature_used=anneal_temp,
                mos_estimate=clarity_score,  # Legacy compatibility
                cpu_percent=cpu_percent,
                memory_mb=memory_mb
            )

            write_test_result(
                test_id=test_id, status=status, latency_ms=latency_ms,
                cpu_pct=cpu_percent, mem_mb=memory_mb, epoch_id=epoch_id,
                artifact_bytes=audio_bytes[:1000]
            )

            self.results.append(result)
            self.record_telemetry("test_complete", {"test_id": test_id, "status": status})
            return result

        except Exception as e:
            result = TTSTestResult(
                test_id=test_id, backend=backend, voice=voice,
                text_hash=self._hash_text(text), status="fail",
                latency_ms=0.0, first_token_ms=None, audio_duration_sec=0.0,
                audio_hash="",
                clarity_score=0.0, transcript_score=0.0, transcript_text="",
                consistency_score=0.0, temperature_used=anneal_temp,
                mos_estimate=None, cpu_percent=0.0, memory_mb=0.0
            )

            write_test_result(test_id=test_id, status="fail", epoch_id=epoch_id)

            self.results.append(result)
            self.record_telemetry("test_failed", {"test_id": test_id, "error": str(e)})
            raise RuntimeError(f"TTS test failed: {e}") from e

    def run_all_tests(self, epoch_id: str) -> List[TTSTestResult]:
        """Execute all TTS tests for configured backends and texts."""
        for backend in self.test_config.backends:
            for voice in self.test_config.target_voices:
                for text in self.test_config.test_texts:
                    try:
                        self.run_test(backend, voice, text, epoch_id)
                    except RuntimeError:
                        continue
        return self.results

    def get_summary(self) -> Dict:
        """Generate summary statistics from test results."""
        if not self.results:
            return {"pass_rate": 0.0, "total_tests": 0}

        passed = sum(1 for r in self.results if r.status == "pass")
        latencies = [r.latency_ms for r in self.results if r.status == "pass"]
        mos_scores = [r.mos_estimate for r in self.results if r.mos_estimate is not None]

        latencies_sorted = sorted(latencies) if latencies else [0]

        return {
            "pass_rate": passed / len(self.results),
            "total_tests": len(self.results),
            "latency_p50": latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0,
            "latency_p95": latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0,
            "avg_mos": sum(mos_scores) / len(mos_scores) if mos_scores else 0.0
        }
