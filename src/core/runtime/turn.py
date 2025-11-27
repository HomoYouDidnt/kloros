"""Turn orchestrator for KLoROS voice interactions."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Protocol

import numpy as np

from src.voice.audio.vad import VADMetrics, detect_voiced_segments, select_primary_segment, detect_segments_two_stage
from src.voice.stt.base import SttBackend, SttResult
from src.voice.tts.base import TtsBackend, TtsResult

# Import reasoning trace for XAI
try:
    from src.cognition.reasoning.reasoning_trace import start_trace, get_trace, complete_trace, ReasoningStepType
    TRACE_AVAILABLE = True
except ImportError:
    TRACE_AVAILABLE = False


@dataclass
class TurnSummary:
    """Summary of a complete turn interaction."""

    trace_id: str
    ok: bool
    reason: str
    transcript: str = ""
    reply_text: str = ""
    tts: Optional[TtsResult] = None
    vad: Optional[VADMetrics] = None
    timings_ms: Dict[str, float] = field(default_factory=dict)


ReasonFn = Callable[[str], str]  # Simple stub for reasoning function


def new_trace_id() -> str:
    """Generate a new unique trace ID for a turn."""
    return uuid.uuid4().hex


class JsonLogger(Protocol):
    """Protocol for JSON event logging."""

    def log_event(self, name: str, **payload) -> None:
        """Log a named event with payload data."""
        ...


def run_turn(
    audio: np.ndarray,
    sample_rate: int,
    *,
    stt: SttBackend,
    reason_fn: ReasonFn,
    tts: Optional[TtsBackend] = None,
    vad_threshold_dbfs: float,
    silero_vad=None,  # SileroVAD instance or None
    use_two_stage: bool = False,
    stage_a_threshold_dbfs: float = -28.0,
    stage_b_threshold: float = 0.60,
    max_cmd_ms: int = 5500,
    prefer_first: bool = True,
    frame_ms: int = 30,
    hop_ms: int = 10,
    attack_ms: int = 80,     # Increased: less prone to noise triggers
    release_ms: int = 600,   # Increased: tolerates natural pauses (was cutting off user)
    min_active_ms: int = 300, # Increased: filters spurious segments
    margin_db: float = 2.0,
    max_turn_seconds: float = 30.0,
    logger: Optional[JsonLogger] = None,
    trace_id: Optional[str] = None,
) -> TurnSummary:
    """Orchestrate VAD → STT → Reason → TTS pipeline.

    Args:
        audio: Input audio samples as float32 mono array
        sample_rate: Sample rate in Hz
        stt: STT backend for transcription
        reason_fn: Function to generate response from transcript
        tts: Optional TTS backend for synthesis
        vad_threshold_dbfs: VAD threshold in dBFS (legacy/fallback)
        silero_vad: SileroVAD instance for two-stage VAD (or None)
        use_two_stage: Enable two-stage VAD (dBFS pre-gate + Silero refinement)
        stage_a_threshold_dbfs: Stage A dBFS threshold (stricter, e.g., -28)
        stage_b_threshold: Stage B Silero probability threshold (e.g., 0.60)
        max_cmd_ms: Hard cap on segment duration in milliseconds (e.g., 5500)
        prefer_first: If True, prefer first segment; if False, prefer longest
        frame_ms: VAD frame size in milliseconds
        hop_ms: VAD hop size in milliseconds
        attack_ms: VAD attack time in milliseconds
        release_ms: VAD release time in milliseconds
        min_active_ms: Minimum active segment duration in milliseconds
        margin_db: VAD hysteresis margin in dB
        max_turn_seconds: Maximum turn duration before timeout
        logger: Optional logger for events
        trace_id: Optional trace ID (generated if not provided)

    Returns:
        TurnSummary with results and timing information
    """
    tid = trace_id or new_trace_id()
    t0 = time.perf_counter()
    timings: Dict[str, float] = {}

    def emit(name: str, **payload):
        """Emit a log event with trace_id."""
        if logger:
            payload["trace_id"] = tid
            logger.log_event(name, **payload)

    emit("turn_start", len_samples=len(audio), sample_rate=sample_rate)

    # VAD Stage
    v0 = time.perf_counter()

    if use_two_stage and silero_vad is not None:
        # Two-stage VAD: dBFS pre-gate → Silero refinement
        segments_time, vad_metadata = detect_segments_two_stage(
            audio=audio,
            sample_rate=sample_rate,
            silero_vad=silero_vad,
            stage_a_threshold_dbfs=stage_a_threshold_dbfs,
            stage_b_threshold=stage_b_threshold,
            min_speech_ms=min_active_ms,
            max_speech_s=max_turn_seconds,
            prefer_first=prefer_first,
        )

        # Convert time-based segments to sample indices
        segments = []
        for start_time, end_time in segments_time:
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            segments.append((start_sample, end_sample))

        # Create metrics placeholder (two-stage doesn't use VADMetrics)
        metrics = VADMetrics(dbfs_mean=-40.0, dbfs_peak=-30.0, frames_total=0, frames_active=0)

        emit(
            "vad_two_stage",
            stage_a_candidates=vad_metadata["stage_a_candidates"],
            stage_b_refined=vad_metadata["stage_b_refined"],
            selected_segment=vad_metadata["selected_segment"],
        )
    else:
        # Legacy single-stage dBFS VAD
        segments, metrics = detect_voiced_segments(
            audio,
            sample_rate,
            vad_threshold_dbfs,
            frame_ms=frame_ms,
            hop_ms=hop_ms,
            attack_ms=attack_ms,
            release_ms=release_ms,
            min_active_ms=min_active_ms,
            margin_db=margin_db,
        )

    timings["vad_ms"] = (time.perf_counter() - v0) * 1000.0

    if not segments:
        emit(
            "vad_gate",
            open=False,
            thr=vad_threshold_dbfs if not use_two_stage else stage_a_threshold_dbfs,
            frames_active=metrics.frames_active if hasattr(metrics, 'frames_active') else 0,
            frames_total=metrics.frames_total if hasattr(metrics, 'frames_total') else 0,
            dbfs_mean=float(metrics.dbfs_mean) if hasattr(metrics, 'dbfs_mean') else -120.0,
            dbfs_peak=float(metrics.dbfs_peak) if hasattr(metrics, 'dbfs_peak') else -120.0,
        )
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="no_voice", total_ms=timings["total_ms"], duration_sec=timings["total_ms"]/1000.0)
        return TurnSummary(
            trace_id=tid, ok=False, reason="no_voice", vad=metrics, timings_ms=timings
        )

    # Select primary voiced segment
    primary_segment = select_primary_segment(segments)
    start, end = primary_segment if primary_segment else segments[0]

    # Adaptive max_cmd_ms: warn if exceeding old limit, but allow up to 20s safety cap
    segment_duration_ms = (end - start) / sample_rate * 1000
    SAFETY_CAP_MS = 20000  # 20 second absolute safety limit

    if segment_duration_ms > max_cmd_ms:
        # Emit warning but DO NOT truncate unless hitting safety cap
        emit("vad_segment_extended",
             original_ms=segment_duration_ms,
             old_limit_ms=max_cmd_ms,
             warning="exceeds legacy limit but allowed")

        # Only enforce safety cap (prevents runaway recording)
        if segment_duration_ms > SAFETY_CAP_MS:
            end = start + int(SAFETY_CAP_MS * sample_rate / 1000)
            emit("vad_segment_safety_capped",
                 original_ms=segment_duration_ms,
                 safety_cap_ms=SAFETY_CAP_MS)

    voiced = audio[start:end]

    emit(
        "vad_gate",
        open=True,
        thr=vad_threshold_dbfs,
        start=start,
        end=end,
        len_samples=len(voiced),
        frames_active=metrics.frames_active,
        frames_total=metrics.frames_total,
        dbfs_mean=float(metrics.dbfs_mean),
        dbfs_peak=float(metrics.dbfs_peak),
    )

    # Timeout check after VAD
    if (time.perf_counter() - t0) > max_turn_seconds:
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="timeout_after_vad", total_ms=timings["total_ms"], duration_sec=timings["total_ms"]/1000.0)
        return TurnSummary(
            trace_id=tid, ok=False, reason="timeout", vad=metrics, timings_ms=timings
        )

    # STT Stage
    s0 = time.perf_counter()

    # DEBUG: Analyze audio before STT
    voiced_rms = np.sqrt(np.mean(voiced**2)) if len(voiced) > 0 else 0.0
    voiced_peak = np.max(np.abs(voiced)) if len(voiced) > 0 else 0.0
    voiced_dbfs = 20 * np.log10(voiced_rms) if voiced_rms > 0 else -120.0
    voiced_samples = len(voiced)
    voiced_duration = voiced_samples / sample_rate if sample_rate > 0 else 0.0

    emit("stt_audio_debug",
         samples=int(voiced_samples),
         duration_ms=float(voiced_duration*1000),
         rms=float(voiced_rms),
         peak=float(voiced_peak),
         dbfs=float(voiced_dbfs),
         first_10_samples=[float(x) for x in (voiced[:10] if len(voiced) >= 10 else voiced)],
         sample_rate=int(sample_rate))

    stt_res: SttResult = stt.transcribe(voiced, sample_rate, lang="en")
    timings["stt_ms"] = (time.perf_counter() - s0) * 1000.0

    # STT SANITY CHECKS: Detect Whisper hallucinations
    # Validates transcription plausibility against audio characteristics
    # This prevents hallucinations like "approach" from 11.95s of echo/noise
    transcript_suspicious = False
    suspicion_reason = ""

    if stt_res.transcript:
        word_count = len(stt_res.transcript.split())

        # Check 1: Word count vs duration (expect ~2-4 words/sec for natural speech)
        # Very few words from long audio suggests hallucination
        if voiced_duration > 3.0 and word_count < 2:
            transcript_suspicious = True
            suspicion_reason = f"too_few_words ({word_count} words in {voiced_duration:.1f}s)"

        # Check 2: Audio energy level (dBFS) should be reasonable for speech
        # Very low energy (< -45 dBFS) with transcription suggests hallucinating from noise
        if voiced_dbfs < -45.0 and word_count > 0:
            transcript_suspicious = True
            suspicion_reason = f"low_energy_hallucination (dbFS={voiced_dbfs:.1f}, words={word_count})"

        # Check 3: Extremely long audio with minimal words (>10s with <3 words)
        if voiced_duration > 10.0 and word_count < 3:
            transcript_suspicious = True
            suspicion_reason = f"long_audio_few_words ({word_count} words in {voiced_duration:.1f}s)"

    if transcript_suspicious:
        emit(
            "stt_rejected_suspicious",
            transcript=stt_res.transcript,
            duration_s=voiced_duration,
            dbfs=voiced_dbfs,
            word_count=len(stt_res.transcript.split()) if stt_res.transcript else 0,
            reason=suspicion_reason
        )
        print(f"[STT] REJECTED suspicious transcription: '{stt_res.transcript}' ({suspicion_reason})")

        # Return early with rejection status
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        return TurnSummary(
            trace_id=tid,
            ok=False,
            reason=f"stt_hallucination_{suspicion_reason}",
            transcript="",
            vad=metrics,
            timings_ms=timings,
        )

    emit(
        "stt_done",
        len_samples=len(voiced),
        sample_rate=sample_rate,
        confidence=stt_res.confidence,
        lang=stt_res.lang,
        transcript=stt_res.transcript,
    )

    # Timeout check after STT
    if (time.perf_counter() - t0) > max_turn_seconds:
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="timeout_after_stt", total_ms=timings["total_ms"], duration_sec=timings["total_ms"]/1000.0)
        return TurnSummary(
            trace_id=tid,
            ok=False,
            reason="timeout",
            transcript=stt_res.transcript,
            vad=metrics,
            timings_ms=timings,
        )

    # Reasoning Stage
    r0 = time.perf_counter()

    # Start XAI reasoning trace
    transcript = stt_res.transcript or ""
    if TRACE_AVAILABLE:
        try:
            trace = start_trace(tid, transcript)
            trace.add_step(
                ReasoningStepType.CONTEXT_RETRIEVAL,
                f"Received transcribed query: {transcript[:80]}...",
                data={'transcript_length': len(transcript)}
            )
        except Exception as e:
            print(f"[turn] Failed to start XAI trace: {e}")

    # Execute reasoning function
    reply_text = reason_fn(transcript)
    timings["reason_ms"] = (time.perf_counter() - r0) * 1000.0

    # Complete XAI reasoning trace
    if TRACE_AVAILABLE:
        try:
            trace = get_trace(tid)
            if trace:
                trace.add_step(
                    ReasoningStepType.LLM_GENERATION,
                    f"Generated response ({len(reply_text)} chars)",
                    data={
                        'response_length': len(reply_text),
                        'reasoning_duration_ms': timings["reason_ms"]
                    },
                    duration_ms=timings["reason_ms"]
                )
                complete_trace(tid, reply_text[:500], success=True)  # Truncate long responses
        except Exception as e:
            print(f"[turn] Failed to complete XAI trace: {e}")

    emit(
        "reason_done",
        tokens_in=len(transcript),
        tokens_out=len(reply_text),
        reply_text=reply_text,
    )

    # Timeout check after reasoning
    if (time.perf_counter() - t0) > max_turn_seconds:
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="timeout_after_reason", total_ms=timings["total_ms"], duration_sec=timings["total_ms"]/1000.0)
        return TurnSummary(
            trace_id=tid,
            ok=False,
            reason="timeout",
            transcript=stt_res.transcript,
            reply_text=reply_text,
            vad=metrics,
            timings_ms=timings,
        )

    # TTS Stage (optional)
    tts_result: Optional[TtsResult] = None
    if tts and reply_text:
        tts0 = time.perf_counter()
        try:
            tts_result = tts.synthesize(reply_text)
            timings["tts_ms"] = (time.perf_counter() - tts0) * 1000.0
            emit(
                "tts_done",
                audio_path=tts_result.audio_path,
                duration_s=tts_result.duration_s,
                sample_rate=tts_result.sample_rate,
                voice=tts_result.voice,
            )
        except Exception as e:
            timings["tts_ms"] = (time.perf_counter() - tts0) * 1000.0
            emit("tts_error", error=str(e))

    # Final timing and completion
    timings["total_ms"] = (time.perf_counter() - t0) * 1000.0

    # Emit consolidated latency breakdown
    emit(
        "latency_breakdown",
        stt_ms=round(timings.get("stt_ms", 0.0), 2),
        llm_ms=round(timings.get("reason_ms", 0.0), 2),
        tts_ms=round(timings.get("tts_ms", 0.0), 2),
        vad_ms=round(timings.get("vad_ms", 0.0), 2),
        total_ms=round(timings["total_ms"], 2),
        transcript_length=len(transcript),
        response_length=len(reply_text),
        timestamp=time.time()
    )

    # Print concise latency summary
    print(
        f"[LATENCY] STT: {timings.get('stt_ms', 0.0):.0f}ms | "
        f"LLM: {timings.get('reason_ms', 0.0):.0f}ms | "
        f"TTS: {timings.get('tts_ms', 0.0):.0f}ms | "
        f"Total: {timings['total_ms']:.0f}ms",
        flush=True
    )

    emit("turn_done", ok=True, reason="ok", total_ms=timings["total_ms"], duration_sec=timings["total_ms"]/1000.0)

    return TurnSummary(
        trace_id=tid,
        ok=True,
        reason="ok",
        transcript=stt_res.transcript,
        reply_text=reply_text,
        tts=tts_result,
        vad=metrics,
        timings_ms=timings,
    )
