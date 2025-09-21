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
    audio: np.ndarray,           # mono float32 [-1,1]
    sample_rate: int,
    threshold_dbfs: float,
    frame_ms: int = 30,
    hop_ms: int = 10,
    attack_ms: int = 50,
    release_ms: int = 200,
    min_active_ms: int = 200,
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


def select_primary_segment(
    segments: List[Tuple[int, int]]
) -> Tuple[int, int] | None:
    """Select the primary voiced segment.

    Args:
        segments: List of (start_idx, end_idx) segment pairs

    Returns:
        The first segment, or None if no segments
    """
    if not segments:
        return None
    return segments[0]
