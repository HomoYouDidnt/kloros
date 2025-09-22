"""Turn orchestrator for KLoROS voice interactions."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Protocol

import numpy as np

from src.audio.vad import VADMetrics, detect_voiced_segments, select_primary_segment
from src.stt.base import SttBackend, SttResult
from src.tts.base import TtsBackend, TtsResult


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
    frame_ms: int = 30,
    hop_ms: int = 10,
    attack_ms: int = 50,
    release_ms: int = 200,
    min_active_ms: int = 200,
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
        vad_threshold_dbfs: VAD threshold in dBFS
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
            thr=vad_threshold_dbfs,
            frames_active=metrics.frames_active,
            frames_total=metrics.frames_total,
            dbfs_mean=metrics.dbfs_mean,
            dbfs_peak=metrics.dbfs_peak,
        )
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="no_voice", total_ms=timings["total_ms"])
        return TurnSummary(
            trace_id=tid, ok=False, reason="no_voice", vad=metrics, timings_ms=timings
        )

    # Select primary voiced segment
    primary_segment = select_primary_segment(segments)
    start, end = primary_segment if primary_segment else segments[0]
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
        dbfs_mean=metrics.dbfs_mean,
        dbfs_peak=metrics.dbfs_peak,
    )

    # Timeout check after VAD
    if (time.perf_counter() - t0) > max_turn_seconds:
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="timeout_after_vad", total_ms=timings["total_ms"])
        return TurnSummary(
            trace_id=tid, ok=False, reason="timeout", vad=metrics, timings_ms=timings
        )

    # STT Stage
    s0 = time.perf_counter()
    stt_res: SttResult = stt.transcribe(voiced, sample_rate)
    timings["stt_ms"] = (time.perf_counter() - s0) * 1000.0

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
        emit("turn_done", ok=False, reason="timeout_after_stt", total_ms=timings["total_ms"])
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
    reply_text = reason_fn(stt_res.transcript or "")
    timings["reason_ms"] = (time.perf_counter() - r0) * 1000.0

    emit(
        "reason_done",
        tokens_in=len(stt_res.transcript or ""),
        tokens_out=len(reply_text),
        reply_text=reply_text,
    )

    # Timeout check after reasoning
    if (time.perf_counter() - t0) > max_turn_seconds:
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0
        emit("turn_done", ok=False, reason="timeout_after_reason", total_ms=timings["total_ms"])
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
    emit("turn_done", ok=True, reason="ok", total_ms=timings["total_ms"])

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
