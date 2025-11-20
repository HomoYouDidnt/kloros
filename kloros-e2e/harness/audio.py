"""Audio synthesis and testing utilities for E2E harness."""
import io
import subprocess
import tempfile
from pathlib import Path

import requests


def text_to_wav(text: str, output_path: Path | str | None = None) -> Path:
    """
    Convert text to WAV audio using espeak (simple, no dependencies).

    Args:
        text: Text to synthesize
        output_path: Optional output path. If None, creates temp file.

    Returns:
        Path to generated WAV file
    """
    if output_path is None:
        # Create temp file
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        import os
        os.close(fd)

    output_path = Path(output_path)

    # Use espeak to generate WAV (16kHz, mono)
    try:
        subprocess.run(
            [
                "espeak",
                "-w", str(output_path),
                "-s", "150",  # Speed: 150 wpm
                "--stdout",
                text
            ],
            capture_output=True,
            check=True,
            stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        raise RuntimeError("espeak not installed. Install with: sudo apt-get install espeak")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"espeak failed: {e.stderr.decode()}")

    if not output_path.exists():
        raise RuntimeError(f"espeak did not create output file: {output_path}")

    return output_path


def send_audio_prompt(
    audio_path: Path | str,
    url: str = "http://127.0.0.1:8124/ingest-audio"
) -> dict:
    """
    Send audio file to KLoROS via HTTP ingress.

    Args:
        audio_path: Path to WAV file
        url: Ingress endpoint URL

    Returns:
        Response JSON dict
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        response = requests.post(url, files=files, timeout=30)

    response.raise_for_status()
    return response.json()


def get_last_tts_output() -> Path | None:
    """
    Get path to last TTS output saved by KLoROS.

    Returns:
        Path to ~/.kloros/tts/last.wav if it exists, else None
    """
    tts_path = Path.home() / ".kloros" / "tts" / "last.wav"
    return tts_path if tts_path.exists() else None


def verify_tts_output_exists() -> bool:
    """
    Verify that KLoROS generated TTS output.

    Returns:
        True if ~/.kloros/tts/last.wav exists
    """
    return get_last_tts_output() is not None
