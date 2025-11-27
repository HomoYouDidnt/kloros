#!/usr/bin/env python3
"""Generate test audio fixtures for voice zooid testing."""
import wave
import numpy as np
from pathlib import Path


def generate_test_audio(
    output_path: Path,
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
    channels: int = 1
) -> Path:
    """Generate a simple sine wave test audio file.

    Args:
        output_path: Path to output WAV file
        duration_s: Duration in seconds
        sample_rate: Sample rate in Hz
        frequency: Tone frequency in Hz
        channels: Number of audio channels

    Returns:
        Path to generated WAV file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), dtype=np.float32)
    audio = np.sin(2 * np.pi * frequency * t)

    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return output_path


def generate_silent_audio(
    output_path: Path,
    duration_s: float = 0.5,
    sample_rate: int = 16000,
    channels: int = 1
) -> Path:
    """Generate silent audio file for testing.

    Args:
        output_path: Path to output WAV file
        duration_s: Duration in seconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Returns:
        Path to generated WAV file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio = np.zeros(int(sample_rate * duration_s), dtype=np.int16)

    with wave.open(str(output_path), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    return output_path


if __name__ == "__main__":
    fixtures_dir = Path(__file__).parent

    generate_test_audio(fixtures_dir / "test_audio_1s.wav", duration_s=1.0)
    generate_test_audio(fixtures_dir / "test_audio_short.wav", duration_s=0.3)
    generate_silent_audio(fixtures_dir / "test_audio_silent.wav")

    print(f"Generated test audio fixtures in {fixtures_dir}")
