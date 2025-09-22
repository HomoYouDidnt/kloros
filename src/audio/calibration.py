"""Microphone calibration for KLoROS audio processing."""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Protocol

import numpy as np


@dataclass
class CalibrationProfile:
    """Microphone calibration profile with computed thresholds and gains."""

    version: int
    device: Dict[str, object]
    noise_floor_dbfs: float
    speech_rms_dbfs: float
    vad_threshold_dbfs: float
    agc_gain_db: float
    spectral_tilt: float
    recommended_wake_conf_min: float
    created_utc: str


class AudioBackend(Protocol):
    """Protocol for audio input backends used during calibration."""

    def open(self, sample_rate: int, channels: int) -> None:
        """Open the audio input stream."""
        ...

    def record(self, seconds: float) -> np.ndarray:
        """Record audio for the specified duration in seconds.

        Returns:
            numpy array of float32 samples in range [-1.0, 1.0]
        """
        ...

    def close(self) -> None:
        """Close the audio input stream."""
        ...


def _rms_to_dbfs(rms: float, reference: float = 1.0) -> float:
    """Convert RMS amplitude to dBFS (decibels relative to full scale).

    Args:
        rms: RMS amplitude value
        reference: Reference level (1.0 for full scale)

    Returns:
        dBFS value, or -120.0 for very small RMS values
    """
    if rms <= 1e-10:  # Avoid log(0)
        return -120.0
    return 20.0 * np.log10(rms / reference)


def _compute_rms(audio: np.ndarray) -> float:
    """Compute RMS (root mean square) of audio signal."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def _compute_spectral_tilt(audio: np.ndarray, sample_rate: int) -> float:
    """Compute spectral tilt as ratio of low-band to high-band energy.

    Simple two-band approach: 0-1000Hz vs 1000-8000Hz energy ratio.

    Args:
        audio: Audio samples
        sample_rate: Sample rate in Hz

    Returns:
        Spectral tilt ratio (0.0-1.0), where 0.5 is balanced
    """
    if len(audio) < 1024:  # Too short for meaningful FFT
        return 0.5

    # Compute power spectral density
    fft = np.fft.rfft(audio)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)

    # Define bands
    low_mask = freqs <= 1000.0
    high_mask = (freqs > 1000.0) & (freqs <= 8000.0)

    low_energy = np.sum(power[low_mask])
    high_energy = np.sum(power[high_mask])

    total_energy = low_energy + high_energy
    if total_energy <= 1e-10:
        return 0.5

    # Return ratio of low energy to total energy
    return float(low_energy / total_energy)


def _compute_snr_to_wake_conf(snr_db: float) -> float:
    """Heuristic mapping from SNR to recommended wake confidence threshold.

    Higher SNR → higher confidence threshold (can be more strict).
    Lower SNR → lower confidence threshold (need to be more lenient).

    Args:
        snr_db: Signal-to-noise ratio in dB

    Returns:
        Recommended wake confidence minimum (0.0-1.0)
    """
    # Heuristic mapping:
    # SNR < 10 dB → conf = 0.5 (very lenient)
    # SNR = 20 dB → conf = 0.65 (default)
    # SNR > 30 dB → conf = 0.8 (strict)
    if snr_db < 10.0:
        return 0.5
    elif snr_db > 30.0:
        return 0.8
    else:
        # Linear interpolation between 10-30 dB range
        return 0.5 + (snr_db - 10.0) / 20.0 * 0.3


def run_calibration(
    backend: AudioBackend,
    sample_rate: int = None,
    silence_secs: float = None,
    speech_secs: float = None,
    target_rms_dbfs: float = None,
    noise_margin_db: float = None,
    agc_max_gain_db: float = None,
) -> CalibrationProfile:
    """Run complete microphone calibration process.

    Args:
        backend: Audio backend for recording
        sample_rate: Sample rate in Hz
        silence_secs: Duration to record silence for noise floor
        speech_secs: Duration to record speech for RMS measurement
        target_rms_dbfs: Target speech RMS level in dBFS
        noise_margin_db: Margin above noise floor for VAD threshold
        agc_max_gain_db: Maximum AGC gain in dB

    Returns:
        CalibrationProfile with computed metrics
    """
    # Parse environment variables with defaults
    sample_rate = sample_rate or int(os.getenv("KLR_CALIB_SAMPLE_RATE", "16000"))
    silence_secs = silence_secs or float(os.getenv("KLR_CALIB_SILENCE_SECS", "4.0"))
    speech_secs = speech_secs or float(os.getenv("KLR_CALIB_SPEECH_SECS", "8.0"))
    target_rms_dbfs = target_rms_dbfs or float(os.getenv("KLR_TARGET_RMS_DBFS", "-20.0"))
    noise_margin_db = noise_margin_db or float(os.getenv("KLR_NOISE_FLOOR_DBFS_MARGIN", "10.0"))
    agc_max_gain_db = agc_max_gain_db or float(os.getenv("KLR_AGC_MAX_GAIN_DB", "12.0"))

    # Open audio backend
    backend.open(sample_rate, channels=1)

    try:
        # Record silence for noise floor measurement
        print(f"Recording {silence_secs:.1f}s of silence for noise floor measurement...")
        silence_audio = backend.record(silence_secs)

        # Record speech for RMS and spectral measurement
        print(f"Recording {speech_secs:.1f}s of speech. Please speak normally...")
        speech_audio = backend.record(speech_secs)

    finally:
        backend.close()

    # Compute noise floor
    noise_rms = _compute_rms(silence_audio)
    noise_floor_dbfs = _rms_to_dbfs(noise_rms)

    # Compute speech RMS
    speech_rms = _compute_rms(speech_audio)
    speech_rms_dbfs = _rms_to_dbfs(speech_rms)

    # Compute VAD threshold
    vad_threshold_dbfs = noise_floor_dbfs + noise_margin_db

    # Compute AGC gain
    agc_gain_needed = target_rms_dbfs - speech_rms_dbfs
    agc_gain_db = max(0.0, min(agc_gain_needed, agc_max_gain_db))

    # Compute spectral tilt
    spectral_tilt = _compute_spectral_tilt(speech_audio, sample_rate)

    # Compute recommended wake confidence
    snr_db = speech_rms_dbfs - noise_floor_dbfs
    recommended_wake_conf_min = _compute_snr_to_wake_conf(snr_db)

    # Create device info
    device_info = {
        "name": "default",  # Backend should provide this if available
        "sample_rate": sample_rate,
    }

    # Create profile
    profile = CalibrationProfile(
        version=1,
        device=device_info,
        noise_floor_dbfs=noise_floor_dbfs,
        speech_rms_dbfs=speech_rms_dbfs,
        vad_threshold_dbfs=vad_threshold_dbfs,
        agc_gain_db=agc_gain_db,
        spectral_tilt=spectral_tilt,
        recommended_wake_conf_min=recommended_wake_conf_min,
        created_utc=datetime.now(timezone.utc).isoformat(),
    )

    return profile


def default_profile_path() -> str:
    """Get the default path for calibration profile.

    Returns:
        Path to calibration.json in user's home/.kloros directory
    """
    path_override = os.getenv("KLR_CALIB_PROFILE_PATH")
    if path_override:
        return path_override

    if platform.system() == "Windows":
        base_dir = Path(os.environ.get("USERPROFILE", "~")).expanduser()
    else:
        base_dir = Path.home()

    return str(base_dir / ".kloros" / "calibration.json")


def save_profile(profile: CalibrationProfile, path: Optional[str] = None) -> str:
    """Save calibration profile to disk.

    Args:
        profile: Calibration profile to save
        path: Optional path override

    Returns:
        Path where profile was saved
    """
    if path is None:
        path = default_profile_path()

    # Ensure directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Save as JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2)

    return path


def load_profile(path: Optional[str] = None) -> Optional[CalibrationProfile]:
    """Load calibration profile from disk.

    Args:
        path: Optional path override

    Returns:
        CalibrationProfile if found and valid, None otherwise
    """
    if path is None:
        path = default_profile_path()

    try:
        if not Path(path).exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate required fields
        required_fields = {
            "version",
            "device",
            "noise_floor_dbfs",
            "speech_rms_dbfs",
            "vad_threshold_dbfs",
            "agc_gain_db",
            "spectral_tilt",
            "recommended_wake_conf_min",
            "created_utc",
        }

        if not all(field in data for field in required_fields):
            return None

        return CalibrationProfile(**data)

    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return None
