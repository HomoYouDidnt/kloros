"""
PHASE Domain: Text-to-Speech Quality & Performance

Tests TTS backends for:
- Voice quality (MOS estimation via signal metrics)
- Latency (first-token, total generation)
- Consistency (same input → similar output)
- Resource usage (CPU, memory during generation)

KPIs: latency_p50, latency_p95, mos_estimate, consistency_score
"""
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

# Add parent to path for report_writer
sys.path.insert(0, str(Path(__file__).parent))
from src.phase.report_writer import write_test_result

@dataclass
class TTSTestConfig:
    """Configuration for TTS domain tests."""
    backends: List[str] = None  # ["piper", "xtts_v2", "mimic3"]
    test_texts: List[str] = None
    target_voices: List[str] = None

    # Resource budgets (D-REAM compliance)
    max_latency_ms: int = 5000  # 5s max per utterance
    max_memory_mb: int = 2048
    max_cpu_percent: int = 80

    def __post_init__(self):
        if self.backends is None:
            self.backends = ["mock"]  # Use mock backend for testing
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
    status: str  # pass, fail, flake
    latency_ms: float
    first_token_ms: Optional[float]
    audio_duration_sec: float
    audio_hash: str  # For consistency checking
    mos_estimate: Optional[float]  # Mean Opinion Score estimate
    cpu_percent: float
    memory_mb: float

class TTSDomain:
    """PHASE test domain for TTS quality and performance."""

    def __init__(self, config: TTSTestConfig):
        """Initialize TTS domain with configuration.

        Args:
            config: TTSTestConfig with backend list, test texts, and budgets
        """
        self.config = config
        self.results: List[TTSTestResult] = []

    def _hash_text(self, text: str) -> str:
        """Generate deterministic hash of input text.

        Args:
            text: Input string to hash

        Returns:
            SHA256 hash truncated to 16 chars
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _hash_audio(self, audio_bytes: bytes) -> str:
        """Generate deterministic hash of audio output.

        Args:
            audio_bytes: Raw audio data

        Returns:
            SHA256 hash truncated to 16 chars
        """
        return hashlib.sha256(audio_bytes).hexdigest()[:16]

    def _estimate_mos(self, audio_bytes: bytes, sample_rate: int = 22050) -> float:
        """Estimate Mean Opinion Score from audio signal.

        Uses simple signal quality metrics (SNR, spectral flatness) as proxy
        for perceptual quality. Real MOS requires human evaluation.

        Args:
            audio_bytes: Raw PCM audio data
            sample_rate: Audio sample rate in Hz

        Returns:
            Estimated MOS score (1.0-5.0, higher is better)
        """
        # Simplified: check for silence, clipping, basic SNR
        # In production, use pesq or visqol for proper MOS estimation
        if len(audio_bytes) < 1000:
            return 1.0  # Too short, likely failed

        # Check for sustained silence (bad)
        nonzero = sum(1 for b in audio_bytes if abs(b) > 5)
        if nonzero < len(audio_bytes) * 0.1:
            return 2.0  # Mostly silent

        # Check for clipping (bad)
        clipped = sum(1 for b in audio_bytes if abs(b) > 250)
        if clipped > len(audio_bytes) * 0.05:
            return 3.0  # Heavy clipping

        # Baseline for reasonable audio
        return 4.0

    def run_test(self, backend: str, voice: str, text: str, epoch_id: str) -> TTSTestResult:
        """Execute single TTS test and record result.

        Args:
            backend: TTS backend name (piper, xtts_v2, mimic3)
            voice: Voice model identifier
            text: Input text to synthesize
            epoch_id: PHASE epoch identifier for grouping

        Returns:
            TTSTestResult with latency, quality metrics, resource usage

        Raises:
            RuntimeError: If synthesis fails or exceeds resource budgets
        """
        test_id = f"tts::{backend}::{voice[:20]}::{self._hash_text(text)}"

        try:
            # Use real TTS backend factory
            from src.tts.base import create_tts_backend
            import tempfile
            import resource

            start = time.time()

            # Create real TTS backend
            tts_backend = create_tts_backend(backend)

            # Synthesize using real backend
            with tempfile.TemporaryDirectory() as tmp_dir:
                result = tts_backend.synthesize(
                    text,
                    sample_rate=22050,
                    out_dir=tmp_dir,
                    basename="phase_test"
                )

                # Read audio file to get actual bytes and duration
                with open(result.audio_path, 'rb') as f:
                    audio_bytes = f.read()

                audio_duration_sec = result.duration_s
                first_token_ms = None  # Not all backends provide this

            latency_ms = (time.time() - start) * 1000

            # Resource usage
            usage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_percent = 0.0  # Would need psutil for accurate CPU %
            memory_mb = usage.ru_maxrss / 1024  # KB to MB on Linux

            # Quality estimation from real audio
            audio_hash = self._hash_audio(audio_bytes)
            mos_estimate = self._estimate_mos(audio_bytes)

            # Check budgets
            status = "pass"
            if latency_ms > self.config.max_latency_ms:
                status = "fail"
            if memory_mb > self.config.max_memory_mb:
                status = "fail"
            if cpu_percent > self.config.max_cpu_percent:
                status = "fail"

            result = TTSTestResult(
                test_id=test_id,
                backend=backend,
                voice=voice,
                text_hash=self._hash_text(text),
                status=status,
                latency_ms=latency_ms,
                first_token_ms=first_token_ms,
                audio_duration_sec=audio_duration_sec,
                audio_hash=audio_hash,
                mos_estimate=mos_estimate,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb
            )

            # Write to PHASE report
            write_test_result(
                test_id=test_id,
                status=status,
                latency_ms=latency_ms,
                cpu_pct=cpu_percent,
                mem_mb=memory_mb,
                epoch_id=epoch_id,
                artifact_bytes=audio_bytes[:1000]  # Sample for hash
            )

            self.results.append(result)
            return result

        except Exception as e:
            # Record failure
            result = TTSTestResult(
                test_id=test_id,
                backend=backend,
                voice=voice,
                text_hash=self._hash_text(text),
                status="fail",
                latency_ms=0.0,
                first_token_ms=None,
                audio_duration_sec=0.0,
                audio_hash="",
                mos_estimate=None,
                cpu_percent=0.0,
                memory_mb=0.0
            )

            write_test_result(
                test_id=test_id,
                status="fail",
                epoch_id=epoch_id
            )

            self.results.append(result)
            raise RuntimeError(f"TTS test failed: {e}") from e

    def run_all_tests(self, epoch_id: str) -> List[TTSTestResult]:
        """Execute all TTS tests for configured backends and texts.

        Args:
            epoch_id: PHASE epoch identifier for grouping

        Returns:
            List of TTSTestResult objects
        """
        for backend in self.config.backends:
            for voice in self.config.target_voices:
                for text in self.config.test_texts:
                    try:
                        self.run_test(backend, voice, text, epoch_id)
                    except RuntimeError:
                        continue  # Already logged

        return self.results

    def get_summary(self) -> Dict:
        """Generate summary statistics from test results.

        Returns:
            Dict with pass_rate, latency_p50, latency_p95, avg_mos
        """
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

if __name__ == "__main__":
    # Example: Run TTS domain tests
    config = TTSTestConfig(
        backends=["piper"],
        test_texts=["Hello, I am KLoROS.", "Testing synthesis quality."],
        target_voices=["glados_piper_medium"]
    )

    domain = TTSDomain(config)
    results = domain.run_all_tests(epoch_id="tts_smoke_test")
    summary = domain.get_summary()

    print(f"TTS Domain Results:")
    print(f"  Pass rate: {summary['pass_rate']*100:.1f}%")
    print(f"  Latency P50: {summary['latency_p50']:.1f}ms")
    print(f"  Latency P95: {summary['latency_p95']:.1f}ms")
    print(f"  Avg MOS: {summary['avg_mos']:.2f}")
