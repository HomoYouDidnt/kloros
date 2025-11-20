"""
SPICA Derivative: Turn Management & VAD Quality

SPICA-based turn management testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- VAD boundary accuracy (segmentation quality)
- Echo suppression effectiveness (prevents self-triggering)
- Barge-in responsiveness (user can interrupt TTS)
- End-to-end latency (speech-end → TTS start)
- Buffer integrity (no premature truncation)
- False trigger rate (noise rejection)

KPIs: boundary_f1, echo_leakage_db, barge_in_ms, e2e_latency_ms, integrity_rate, false_triggers_per_min
"""
import time
import uuid
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result


@dataclass
class TurnVariant:
    """Evolvable turn management parameters for D-REAM optimization."""
    attack_ms: int = 80          # Voice detection onset (50-200ms)
    release_ms: int = 600         # Silence before turn-end (200-1500ms)
    min_active_ms: int = 300      # Minimum voice duration (100-800ms)
    quiet_end_ms: int = 800       # Extended silence for definite end (400-2000ms)
    max_cmd_ms: int = 15000       # Safety cap (5000-20000ms)
    threshold_dbfs: float = -40.0 # RMS threshold (-60.0 to -25.0 dBFS)

    # STT stage confidence (for cascaded VAD+STT gating)
    stage_b_conf: float = 0.7     # Whisper confidence threshold (0.5-0.95)

    # Echo cancellation ratio (0.0=off, 1.0=full gate)
    aec_gate_ratio: float = 0.85  # Gate input during TTS (0.0-1.0)

    # Barge-in detection
    barge_in_enabled: bool = True
    barge_in_threshold_dbfs: float = -35.0  # Higher than threshold_dbfs

    # Annealing temperature for exploration
    anneal_temp: float = 1.0      # 0.0=exploit, 1.0=explore


@dataclass
class TurnTestConfig:
    """Configuration for turn management domain tests."""
    test_fixtures: List[Dict] = None
    max_e2e_latency_ms: int = 2000
    max_false_triggers_per_min: float = 0.5
    min_boundary_f1: float = 0.85
    max_echo_leakage_db: float = -30.0  # Lower is better (more suppression)

    # D-REAM evolvable fitness weights (must sum to ~1.0)
    fitness_weight_segmentation: float = 0.30   # Boundary F1 vs ground truth
    fitness_weight_echo: float = 0.25           # Echo suppression effectiveness
    fitness_weight_barge_in: float = 0.15       # Interrupt detection speed
    fitness_weight_latency: float = 0.15        # E2E response time
    fitness_weight_integrity: float = 0.10      # No premature truncation
    fitness_weight_false_trigger: float = 0.05  # Noise rejection

    def __post_init__(self):
        if self.test_fixtures is None:
            self.test_fixtures = [
                {
                    "name": "multi_clause_pauses",
                    "audio": "synthetic_multi_clause",  # 300-500ms pauses between clauses
                    "expected_turns": 1,
                    "expected_boundaries": [(0.0, 5.2)],  # Single long turn
                    "ground_truth_pauses_ms": [350, 420, 380]
                },
                {
                    "name": "long_utterance",
                    "audio": "synthetic_long_10s",  # 10 second continuous speech
                    "expected_turns": 1,
                    "expected_boundaries": [(0.0, 10.0)],
                    "should_not_truncate": True
                },
                {
                    "name": "echo_loop_test",
                    "audio": "tts_playback_with_mic_feed",  # TTS output fed back to mic
                    "expected_turns": 0,  # Should NOT trigger on own voice
                    "echo_present": True
                },
                {
                    "name": "barge_in",
                    "audio": "user_over_tts",  # User speaks while TTS playing
                    "expected_turns": 1,
                    "barge_in_expected_at_ms": 1200,
                    "tts_playing": True
                },
                {
                    "name": "noise_only",
                    "audio": "ambient_noise",  # Background noise without speech
                    "expected_turns": 0,
                    "noise_type": "ambient"
                }
            ]


@dataclass
class TurnTestResult:
    """Results from a single turn management test."""
    test_id: str
    fixture_name: str
    status: str

    # Segmentation metrics
    boundary_f1: float            # F1 score for turn boundaries
    boundary_precision: float
    boundary_recall: float
    detected_turns: int
    expected_turns: int

    # Echo suppression
    echo_leakage_db: float        # dB of echo that leaked through (lower=better)
    echo_suppression_active: bool

    # Barge-in
    barge_in_detected: bool
    barge_in_latency_ms: float    # Time from user speech start to detection

    # Latency
    e2e_latency_ms: float         # Speech-end to TTS start

    # Integrity
    utterances_truncated: int
    utterances_complete: int
    integrity_rate: float         # % not truncated

    # False triggers
    false_triggers: int
    false_triggers_per_min: float

    # Resources
    cpu_percent: float
    memory_mb: float


def _sanitize_turn_variant(v: TurnVariant) -> TurnVariant:
    """Clamp turn variant parameters to safe ranges."""
    v.attack_ms = int(np.clip(v.attack_ms, 50, 200))
    v.release_ms = int(np.clip(v.release_ms, 200, 1500))
    v.min_active_ms = int(np.clip(v.min_active_ms, 100, 800))
    v.quiet_end_ms = int(np.clip(v.quiet_end_ms, 400, 2000))
    v.max_cmd_ms = int(np.clip(v.max_cmd_ms, 5000, 20000))
    v.threshold_dbfs = float(np.clip(v.threshold_dbfs, -60.0, -25.0))
    v.stage_b_conf = float(np.clip(v.stage_b_conf, 0.5, 0.95))
    v.aec_gate_ratio = float(np.clip(v.aec_gate_ratio, 0.0, 1.0))
    v.barge_in_threshold_dbfs = float(np.clip(v.barge_in_threshold_dbfs, -50.0, -20.0))
    v.anneal_temp = float(np.clip(v.anneal_temp, 0.0, 1.0))
    return v


class TurnEvaluator:
    """Multi-objective turn management evaluator with 6-component fitness."""

    def __init__(self, config: TurnTestConfig):
        self.config = config
        self.telemetry = []

    def _generate_synthetic_audio(self, fixture: Dict) -> Tuple[np.ndarray, int, Dict]:
        """Generate synthetic test audio based on fixture specification."""
        sr = 16000

        if fixture["audio"] == "synthetic_multi_clause":
            # Generate speech with pauses (simulated as tone bursts with gaps)
            segments = []
            metadata = {"clause_boundaries": []}
            t = 0.0

            for i, pause_ms in enumerate(fixture["ground_truth_pauses_ms"]):
                # Speech segment (1 second of 440Hz tone)
                duration = 1.0
                speech_samples = int(duration * sr)
                t_seg = np.linspace(0, duration, speech_samples)
                speech = np.sin(2 * np.pi * 440 * t_seg) * 0.3
                segments.append(speech)

                # Pause
                pause_samples = int((pause_ms / 1000.0) * sr)
                pause = np.zeros(pause_samples)
                segments.append(pause)

                metadata["clause_boundaries"].append((t, t + duration))
                t += duration + (pause_ms / 1000.0)

            # Final speech segment
            speech_samples = int(1.0 * sr)
            speech = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, speech_samples)) * 0.3
            segments.append(speech)

            audio = np.concatenate(segments)
            return audio.astype(np.float32), sr, metadata

        elif fixture["audio"] == "synthetic_long_10s":
            # 10 seconds of continuous tone
            t = np.linspace(0, 10.0, 10 * sr)
            audio = np.sin(2 * np.pi * 440 * t) * 0.3
            return audio.astype(np.float32), sr, {"duration": 10.0}

        elif fixture["audio"] == "tts_playback_with_mic_feed":
            # Simulate TTS output at lower frequency
            t = np.linspace(0, 3.0, 3 * sr)
            audio = np.sin(2 * np.pi * 220 * t) * 0.2  # Lower freq, lower amplitude
            return audio.astype(np.float32), sr, {"is_echo": True}

        elif fixture["audio"] == "user_over_tts":
            # TTS playing (220Hz) then user speaks over it (440Hz)
            t1 = np.linspace(0, 1.2, int(1.2 * sr))
            tts = np.sin(2 * np.pi * 220 * t1) * 0.15

            t2 = np.linspace(0, 2.0, int(2.0 * sr))
            user = np.sin(2 * np.pi * 440 * t2) * 0.35  # Louder

            # Overlap starting at 1.2s
            combined = np.zeros(len(tts) + len(user))
            combined[:len(tts)] = tts
            combined[len(tts):len(tts)+len(user)] += user

            return combined.astype(np.float32), sr, {"barge_in_at_ms": 1200}

        elif fixture["audio"] == "ambient_noise":
            # White noise at low level (well below -40dBFS threshold)
            # RMS of 0.003 → ~-50 dBFS (should NOT trigger at -40dBFS threshold)
            audio = np.random.randn(3 * sr) * 0.003
            return audio.astype(np.float32), sr, {"is_noise": True}

        else:
            raise ValueError(f"Unknown fixture audio: {fixture['audio']}")

    def _compute_rms_dbfs(self, audio: np.ndarray) -> float:
        """Compute RMS level in dBFS."""
        rms = np.sqrt(np.mean(audio**2) + 1e-12)
        return 20 * np.log10(rms + 1e-12)

    def _detect_boundaries(self, audio: np.ndarray, sr: int, variant: TurnVariant) -> List[Tuple[float, float]]:
        """Simulate VAD boundary detection using variant parameters."""
        frame_ms = 20
        frame_samples = int(sr * frame_ms / 1000)
        hop = frame_samples // 2

        # Frame-based RMS
        rms_frames = []
        for i in range(0, len(audio) - frame_samples + 1, hop):
            frame = audio[i:i+frame_samples]
            rms_db = self._compute_rms_dbfs(frame)
            rms_frames.append(rms_db)

        rms_frames = np.array(rms_frames)

        # Hysteresis VAD
        active = rms_frames > variant.threshold_dbfs

        # Find boundaries
        boundaries = []
        in_speech = False
        speech_start = 0
        silence_count = 0

        for i, is_active in enumerate(active):
            if is_active:
                if not in_speech:
                    # Attack phase: accumulate attack_ms frames
                    attack_frames = variant.attack_ms // frame_ms
                    if i >= attack_frames and np.sum(active[i-attack_frames:i]) >= attack_frames * 0.8:
                        in_speech = True
                        speech_start = (i - attack_frames) * hop / sr
                        silence_count = 0
                else:
                    silence_count = 0  # Reset silence counter
            else:
                if in_speech:
                    silence_count += frame_ms
                    # Release phase: release_ms of silence ends turn
                    if silence_count >= variant.release_ms:
                        speech_end = i * hop / sr
                        duration_ms = (speech_end - speech_start) * 1000

                        # Only accept if meets min_active_ms
                        if duration_ms >= variant.min_active_ms:
                            boundaries.append((speech_start, speech_end))

                        in_speech = False
                        silence_count = 0

        # Close final boundary if still in speech
        if in_speech:
            speech_end = len(audio) / sr
            duration_ms = (speech_end - speech_start) * 1000
            if duration_ms >= variant.min_active_ms:
                boundaries.append((speech_start, speech_end))

        return boundaries

    def _compute_boundary_f1(self, detected: List[Tuple[float, float]],
                             expected: List[Tuple[float, float]],
                             tolerance_s: float = 0.3) -> Tuple[float, float, float]:
        """Compute F1, precision, recall for boundary detection."""
        if len(expected) == 0:
            if len(detected) == 0:
                return 1.0, 1.0, 1.0  # Perfect: no speech, nothing detected
            else:
                return 0.0, 0.0, 1.0  # False positives

        if len(detected) == 0:
            return 0.0, 1.0, 0.0  # Missed everything

        # Match detected boundaries to expected (within tolerance)
        tp = 0
        for exp_start, exp_end in expected:
            for det_start, det_end in detected:
                if (abs(det_start - exp_start) <= tolerance_s and
                    abs(det_end - exp_end) <= tolerance_s):
                    tp += 1
                    break

        fp = len(detected) - tp
        fn = len(expected) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return f1, precision, recall

    def _evaluate_echo_suppression(self, audio: np.ndarray, metadata: Dict, variant: TurnVariant) -> Tuple[float, bool]:
        """Evaluate echo suppression effectiveness."""
        if not metadata.get("is_echo", False):
            return -60.0, False  # No echo present, perfect score

        # Simulate AEC gating
        if variant.aec_gate_ratio > 0.5:
            # AEC active: reduce echo by gate ratio
            suppression_db = -20.0 * variant.aec_gate_ratio  # Higher ratio = more suppression
            return suppression_db, True
        else:
            # No AEC: echo leaks through
            echo_level_db = self._compute_rms_dbfs(audio)
            return echo_level_db, False

    def _evaluate_barge_in(self, audio: np.ndarray, sr: int, metadata: Dict,
                           variant: TurnVariant, boundaries: List[Tuple[float, float]]) -> Tuple[bool, float]:
        """Evaluate barge-in detection speed."""
        if "barge_in_at_ms" not in metadata:
            return False, 0.0  # Not a barge-in test

        expected_ms = metadata["barge_in_at_ms"]
        expected_s = expected_ms / 1000.0

        # Check if we detected a boundary near the barge-in point
        for start, end in boundaries:
            if abs(start - expected_s) < 0.5:  # Within 500ms
                latency_ms = abs(start - expected_s) * 1000
                return True, latency_ms

        # Not detected
        return False, 99999.0

    def _check_truncation(self, boundaries: List[Tuple[float, float]], variant: TurnVariant) -> Tuple[int, int]:
        """Check if any utterances were prematurely truncated."""
        truncated = 0
        complete = len(boundaries)

        for start, end in boundaries:
            duration_ms = (end - start) * 1000
            # If duration hits max_cmd_ms exactly, it was likely truncated
            if abs(duration_ms - variant.max_cmd_ms) < 50:  # Within 50ms of cap
                truncated += 1

        return truncated, complete

    def evaluate(self, fixture: Dict, variant: TurnVariant, epoch: int = 0) -> TurnTestResult:
        """
        Evaluate turn management on a single fixture.

        Returns TurnTestResult with 6-component fitness metrics.
        """
        test_id = f"turn::{fixture['name']}"
        variant = _sanitize_turn_variant(variant)

        try:
            # Generate test audio
            audio, sr, metadata = self._generate_synthetic_audio(fixture)

            # Detect boundaries
            boundaries = self._detect_boundaries(audio, sr, variant)

            # Compute boundary F1
            expected_boundaries = fixture.get("expected_boundaries", [])
            boundary_f1, boundary_precision, boundary_recall = self._compute_boundary_f1(
                boundaries, expected_boundaries
            )

            # Echo suppression
            echo_leakage_db, echo_active = self._evaluate_echo_suppression(audio, metadata, variant)

            # Barge-in
            barge_in_detected, barge_in_latency = self._evaluate_barge_in(
                audio, sr, metadata, variant, boundaries
            )

            # Truncation check
            truncated, complete = self._check_truncation(boundaries, variant)
            integrity_rate = (complete - truncated) / complete if complete > 0 else 1.0

            # False triggers
            expected_turns = fixture.get("expected_turns", 1)
            detected_turns = len(boundaries)
            false_triggers = max(0, detected_turns - expected_turns)
            audio_duration_min = len(audio) / sr / 60.0
            false_triggers_per_min = false_triggers / audio_duration_min if audio_duration_min > 0 else 0.0

            # E2E latency (simulated as release_ms + processing overhead)
            e2e_latency_ms = float(variant.release_ms + 150)  # 150ms processing overhead

            # Pass/fail determination
            status = "pass"
            if (boundary_f1 < self.config.min_boundary_f1 or
                echo_leakage_db > self.config.max_echo_leakage_db or
                e2e_latency_ms > self.config.max_e2e_latency_ms or
                false_triggers_per_min > self.config.max_false_triggers_per_min):
                status = "fail"

            result = TurnTestResult(
                test_id=test_id,
                fixture_name=fixture["name"],
                status=status,
                boundary_f1=boundary_f1,
                boundary_precision=boundary_precision,
                boundary_recall=boundary_recall,
                detected_turns=detected_turns,
                expected_turns=expected_turns,
                echo_leakage_db=echo_leakage_db,
                echo_suppression_active=echo_active,
                barge_in_detected=barge_in_detected,
                barge_in_latency_ms=barge_in_latency,
                e2e_latency_ms=e2e_latency_ms,
                utterances_truncated=truncated,
                utterances_complete=complete,
                integrity_rate=integrity_rate,
                false_triggers=false_triggers,
                false_triggers_per_min=false_triggers_per_min,
                cpu_percent=35.0,
                memory_mb=256.0
            )

            return result

        except Exception as e:
            # Return failed result
            return TurnTestResult(
                test_id=test_id,
                fixture_name=fixture["name"],
                status="fail",
                boundary_f1=0.0,
                boundary_precision=0.0,
                boundary_recall=0.0,
                detected_turns=0,
                expected_turns=fixture.get("expected_turns", 1),
                echo_leakage_db=0.0,
                echo_suppression_active=False,
                barge_in_detected=False,
                barge_in_latency_ms=0.0,
                e2e_latency_ms=0.0,
                utterances_truncated=0,
                utterances_complete=0,
                integrity_rate=0.0,
                false_triggers=0,
                false_triggers_per_min=0.0,
                cpu_percent=0.0,
                memory_mb=0.0
            )


class SpicaTurns(SpicaBase):
    """SPICA derivative for turn management quality testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[TurnTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-turns-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'test_fixtures': test_config.test_fixtures,
                'max_e2e_latency_ms': test_config.max_e2e_latency_ms,
                'max_false_triggers_per_min': test_config.max_false_triggers_per_min,
                'min_boundary_f1': test_config.min_boundary_f1,
                'max_echo_leakage_db': test_config.max_echo_leakage_db,
                # Fitness weights (evolvable by D-REAM)
                'fitness_weight_segmentation': test_config.fitness_weight_segmentation,
                'fitness_weight_echo': test_config.fitness_weight_echo,
                'fitness_weight_barge_in': test_config.fitness_weight_barge_in,
                'fitness_weight_latency': test_config.fitness_weight_latency,
                'fitness_weight_integrity': test_config.fitness_weight_integrity,
                'fitness_weight_false_trigger': test_config.fitness_weight_false_trigger
            })

        super().__init__(spica_id=spica_id, domain="turns", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or TurnTestConfig()
        self.evaluator = TurnEvaluator(self.test_config)
        self.results: List[TurnTestResult] = []
        self.record_telemetry("spica_turns_init", {
            "fixtures_count": len(self.test_config.test_fixtures)
        })

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """
        SPICA evaluate() with multi-objective fitness calculation.

        Fitness components:
        - Segmentation (30%): Boundary F1 vs ground truth
        - Echo (25%): Echo suppression effectiveness
        - Barge-in (15%): Interrupt detection speed
        - Latency (15%): E2E response time
        - Integrity (10%): No premature truncation
        - False trigger (5%): Noise rejection
        """
        fixture = test_input.get("fixture")
        variant_dict = test_input.get("variant", {})
        epoch_id = (context or {}).get("epoch_id", "unknown")
        epoch = (context or {}).get("epoch", 0)

        if not fixture:
            raise ValueError("test_input must contain 'fixture' key")

        # Create TurnVariant from dict
        variant = TurnVariant(**variant_dict) if variant_dict else TurnVariant()

        # Run evaluation
        result = self.evaluator.evaluate(fixture, variant, epoch)

        # Multi-objective fitness calculation
        segmentation_component = (
            self.test_config.fitness_weight_segmentation * result.boundary_f1
        )

        # Echo: normalize leakage_db to [0,1] (lower dB = better = higher score)
        # -60dB = perfect (1.0), -20dB = poor (0.0)
        echo_normalized = np.clip((result.echo_leakage_db - (-20.0)) / (-60.0 - (-20.0)), 0.0, 1.0)
        echo_component = (
            self.test_config.fitness_weight_echo * echo_normalized
        )

        # Barge-in: normalize latency to [0,1] (lower = better)
        barge_in_normalized = 1.0 if not result.barge_in_detected else (
            1.0 - min(1.0, result.barge_in_latency_ms / 1000.0)
        )
        barge_in_component = (
            self.test_config.fitness_weight_barge_in * barge_in_normalized
        )

        # Latency: normalize to [0,1]
        latency_normalized = 1.0 - min(
            1.0,
            result.e2e_latency_ms / self.test_config.max_e2e_latency_ms
        )
        latency_component = (
            self.test_config.fitness_weight_latency * latency_normalized
        )

        # Integrity: already in [0,1]
        integrity_component = (
            self.test_config.fitness_weight_integrity * result.integrity_rate
        )

        # False trigger: normalize to [0,1]
        false_trigger_normalized = 1.0 - min(
            1.0,
            result.false_triggers_per_min / self.config.max_false_triggers_per_min
        )
        false_trigger_component = (
            self.test_config.fitness_weight_false_trigger * false_trigger_normalized
        )

        # Combine components
        fitness = (
            segmentation_component +
            echo_component +
            barge_in_component +
            latency_component +
            integrity_component +
            false_trigger_component
        )

        # Clamp to [0, 1]
        fitness = max(0.0, min(1.0, fitness))

        # Record detailed fitness breakdown
        self.record_telemetry("fitness_calculated", {
            "fitness": fitness,
            "segmentation_component": segmentation_component,
            "echo_component": echo_component,
            "barge_in_component": barge_in_component,
            "latency_component": latency_component,
            "integrity_component": integrity_component,
            "false_trigger_component": false_trigger_component,
            "test_id": result.test_id
        })

        # Write test result
        write_test_result(
            test_id=result.test_id,
            status=result.status,
            latency_ms=result.e2e_latency_ms,
            cpu_pct=result.cpu_percent,
            mem_mb=result.memory_mb,
            epoch_id=epoch_id
        )

        self.results.append(result)

        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id,
            # Include fitness breakdown for D-REAM analysis
            "fitness_breakdown": {
                "segmentation": segmentation_component,
                "echo": echo_component,
                "barge_in": barge_in_component,
                "latency": latency_component,
                "integrity": integrity_component,
                "false_trigger": false_trigger_component
            }
        }

    def run_all_tests(self, epoch_id: str, variant: Optional[TurnVariant] = None) -> List[TurnTestResult]:
        """Run all fixtures with given variant."""
        if variant is None:
            variant = TurnVariant()

        for fixture in self.test_config.test_fixtures:
            try:
                result = self.evaluator.evaluate(fixture, variant)
                self.results.append(result)
                write_test_result(
                    test_id=result.test_id,
                    status=result.status,
                    latency_ms=result.e2e_latency_ms,
                    cpu_pct=result.cpu_percent,
                    mem_mb=result.memory_mb,
                    epoch_id=epoch_id
                )
            except Exception as e:
                self.record_telemetry("test_failed", {"fixture": fixture["name"], "error": str(e)})
                continue

        return self.results

    def get_summary(self) -> Dict:
        """Get summary statistics across all test results."""
        if not self.results:
            return {"pass_rate": 0.0, "total_tests": 0}

        passed = sum(1 for r in self.results if r.status == "pass")
        boundary_f1s = [r.boundary_f1 for r in self.results]
        echo_dbs = [r.echo_leakage_db for r in self.results]
        latencies = [r.e2e_latency_ms for r in self.results]

        return {
            "pass_rate": passed / len(self.results),
            "total_tests": len(self.results),
            "avg_boundary_f1": sum(boundary_f1s) / len(boundary_f1s) if boundary_f1s else 0.0,
            "avg_echo_leakage_db": sum(echo_dbs) / len(echo_dbs) if echo_dbs else 0.0,
            "avg_e2e_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "avg_integrity_rate": sum(r.integrity_rate for r in self.results) / len(self.results)
        }
