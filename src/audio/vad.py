"""Voice Activity Detection (VAD) using frame-RMS dBFS gating."""

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class VADMetrics:
    """Metrics from VAD processing."""

    dbfs_mean: float
    dbfs_peak: float
    frames_total: int
    frames_active: int


def rms_dbfs(x: np.ndarray) -> float:
    """Calculate RMS level in dBFS (reference=1.0).

    Args:
        x: Audio samples as float32 array

    Returns:
        RMS level in dBFS, clamped to minimum -120 dBFS
    """
    if len(x) == 0:
        return -120.0

    rms = np.sqrt(np.mean(x**2))
    if rms <= 0.0:
        return -120.0

    dbfs = 20 * np.log10(rms)
    return max(dbfs, -120.0)


def detect_voiced_segments(
    audio: np.ndarray,  # mono float32 [-1,1]
    sample_rate: int,
    threshold_dbfs: float,
    frame_ms: int = 30,
    hop_ms: int = 10,
    attack_ms: int = 80,     # Increased from 50: less prone to noise triggers
    release_ms: int = 600,   # Increased from 200: tolerates natural pauses
    min_active_ms: int = 300, # Increased from 200: filters spurious segments
    margin_db: float = 2.0,
) -> Tuple[List[Tuple[int, int]], VADMetrics]:
    """Detect voiced segments using frame-based RMS analysis with hysteresis.

    Args:
        audio: Mono audio samples as float32 in range [-1, 1]
        sample_rate: Sample rate in Hz
        threshold_dbfs: Base threshold in dBFS
        frame_ms: Frame size in milliseconds
        hop_ms: Hop size in milliseconds
        attack_ms: Attack time in milliseconds
        release_ms: Release time in milliseconds
        min_active_ms: Minimum segment duration in milliseconds
        margin_db: Hysteresis margin around threshold

    Returns:
        Tuple of (segments, metrics) where segments are (start_idx, end_idx) pairs
        in sample indices, and metrics contain processing statistics
    """
    if len(audio) == 0:
        return [], VADMetrics(-120.0, -120.0, 0, 0)

    # Convert time parameters to samples
    frame_samples = int(frame_ms * sample_rate / 1000)
    hop_samples = int(hop_ms * sample_rate / 1000)
    attack_frames = max(1, int(attack_ms / hop_ms))
    release_frames = max(1, int(release_ms / hop_ms))
    min_active_samples = int(min_active_ms * sample_rate / 1000)

    # Frame the audio using stride tricks for efficiency
    if len(audio) < frame_samples:
        # Handle short audio
        dbfs = rms_dbfs(audio)
        metrics = VADMetrics(dbfs, dbfs, 1, 0)
        return [], metrics

    # Create frames using stride tricks
    from numpy.lib.stride_tricks import sliding_window_view

    frames = sliding_window_view(audio, frame_samples)[::hop_samples]

    # Calculate dBFS for each frame
    frame_dbfs = np.array([rms_dbfs(frame) for frame in frames])

    # Calculate metrics
    dbfs_mean = float(np.mean(frame_dbfs))
    dbfs_peak = float(np.max(frame_dbfs))

    # Apply hysteresis thresholding
    open_threshold = threshold_dbfs + margin_db
    close_threshold = threshold_dbfs - margin_db

    # State machine for gate with attack/release
    gate_state = False
    gate_counter = 0
    frame_active = np.zeros(len(frame_dbfs), dtype=bool)

    for i, dbfs in enumerate(frame_dbfs):
        if not gate_state:
            # Gate is closed, check for opening
            if dbfs >= open_threshold:
                gate_counter += 1
                if gate_counter >= attack_frames:
                    gate_state = True
                    gate_counter = 0
            else:
                gate_counter = 0
        else:
            # Gate is open, check for closing
            if dbfs < close_threshold:
                gate_counter += 1
                if gate_counter >= release_frames:
                    gate_state = False
                    gate_counter = 0
            else:
                gate_counter = 0

        frame_active[i] = gate_state

    frames_active_count = int(np.sum(frame_active))
    metrics = VADMetrics(dbfs_mean, dbfs_peak, len(frame_dbfs), frames_active_count)

    # Find continuous segments of active frames
    segments = []
    if frames_active_count > 0:
        # Find transitions
        diff = np.diff(np.concatenate(([False], frame_active, [False])).astype(int))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]

        # Convert frame indices to sample indices
        for start_frame, end_frame in zip(starts, ends, strict=False):
            start_sample = start_frame * hop_samples
            end_sample = min(len(audio), end_frame * hop_samples + frame_samples)

            # Filter out segments shorter than minimum duration
            if end_sample - start_sample >= min_active_samples:
                segments.append((int(start_sample), int(end_sample)))

    return segments, metrics


def select_primary_segment(segments: List[Tuple[int, int]]) -> Tuple[int, int] | None:
    """Select the primary voiced segment.

    Args:
        segments: List of (start_idx, end_idx) segment pairs

    Returns:
        The first segment, or None if no segments
    """
    if not segments:
        return None
    return segments[0]


def detect_candidates_dbfs(
    audio: np.ndarray,
    sample_rate: int,
    threshold_dbfs: float = -28.0,
    frame_ms: int = 30,
    hop_ms: int = 10,
    min_candidate_ms: int = 100,
) -> List[Tuple[float, float]]:
    """Stage A: Fast dBFS pre-gate to detect candidate speech segments.

    Args:
        audio: Mono audio samples as float32 in range [-1, 1]
        sample_rate: Sample rate in Hz
        threshold_dbfs: dBFS threshold for candidate detection (stricter than old -35)
        frame_ms: Frame size in milliseconds
        hop_ms: Hop size in milliseconds
        min_candidate_ms: Minimum candidate duration in milliseconds

    Returns:
        List of (start_time, end_time) candidate segments in seconds
    """
    # Use existing detect_voiced_segments for dBFS detection
    segments_samples, _ = detect_voiced_segments(
        audio=audio,
        sample_rate=sample_rate,
        threshold_dbfs=threshold_dbfs,
        frame_ms=frame_ms,
        hop_ms=hop_ms,
        attack_ms=30,  # Fast attack for pre-gate
        release_ms=100,  # Short release for pre-gate
        min_active_ms=min_candidate_ms,
        margin_db=2.0,
    )

    # Convert sample indices to time in seconds
    candidates = []
    for start_sample, end_sample in segments_samples:
        start_time = start_sample / sample_rate
        end_time = end_sample / sample_rate
        candidates.append((start_time, end_time))

    return candidates


def detect_segments_two_stage(
    audio: np.ndarray,
    sample_rate: int,
    silero_vad,  # SileroVAD instance or None
    stage_a_threshold_dbfs: float = -28.0,
    stage_b_threshold: float = 0.60,
    min_speech_ms: int = 250,
    max_speech_s: float = 30.0,
    prefer_first: bool = True,
) -> Tuple[List[Tuple[float, float]], dict]:
    """Two-stage VAD: dBFS pre-gate → Silero refinement.

    Args:
        audio: Mono audio samples as float32 in range [-1, 1]
        sample_rate: Sample rate in Hz
        silero_vad: SileroVAD instance for Stage B (or None for Stage A only)
        stage_a_threshold_dbfs: dBFS threshold for Stage A pre-gate
        stage_b_threshold: Silero probability threshold for Stage B
        min_speech_ms: Minimum speech segment duration in milliseconds
        max_speech_s: Maximum speech segment duration in seconds
        prefer_first: If True, prefer first segment; if False, prefer longest

    Returns:
        Tuple of (segments, metadata) where segments are (start_time, end_time)
        pairs in seconds, and metadata contains stage information
    """
    metadata = {
        "stage_a_candidates": 0,
        "stage_b_refined": 0,
        "selected_segment": None,
    }

    # Stage A: Fast dBFS pre-gate
    candidates = detect_candidates_dbfs(
        audio=audio,
        sample_rate=sample_rate,
        threshold_dbfs=stage_a_threshold_dbfs,
        min_candidate_ms=min_speech_ms,
    )

    metadata["stage_a_candidates"] = len(candidates)

    if not candidates:
        return [], metadata

    # Stage B: Silero refinement (if available)
    if silero_vad is not None:
        refined_segments = silero_vad.refine_segments(
            audio=audio,
            sample_rate=sample_rate,
            candidates=candidates,
            min_speech_duration_ms=min_speech_ms,
            max_speech_duration_s=max_speech_s,
        )
        metadata["stage_b_refined"] = len(refined_segments)
    else:
        # Fallback: use Stage A candidates directly
        refined_segments = candidates
        metadata["stage_b_refined"] = len(candidates)

    # Select primary segment
    if not refined_segments:
        return [], metadata

    if prefer_first:
        # Prefer first segment for natural conversation flow
        selected = refined_segments[0]
    else:
        # Prefer longest segment
        selected = max(refined_segments, key=lambda seg: seg[1] - seg[0])

    metadata["selected_segment"] = {
        "start": selected[0],
        "end": selected[1],
        "duration": selected[1] - selected[0],
    }

    return [selected], metadata
