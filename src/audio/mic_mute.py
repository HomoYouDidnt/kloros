"""Microphone muting utility for TTS playback (quick AEC workaround)."""

import os
import subprocess
import time
from typing import Optional


def _mute_source(mute: bool, source: Optional[str] = None) -> bool:
    """Mute or unmute a PulseAudio source.

    Args:
        mute: True to mute, False to unmute
        source: Source name (default: @DEFAULT_SOURCE@)

    Returns:
        True if command succeeded, False otherwise
    """
    if source is None:
        source = os.getenv("KLR_MUTE_SOURCE", "@DEFAULT_SOURCE@")

    mute_value = "1" if mute else "0"
    action = "Muting" if mute else "Unmuting"

    try:
        result = subprocess.run(
            ["pactl", "set-source-mute", source, mute_value],
            capture_output=True,
            text=True,
            timeout=2
        )
        success = result.returncode == 0
        if not success:
            print(f"[mic_mute] {action} FAILED: returncode={result.returncode}, stderr={result.stderr.strip()}")
        return success
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[mic_mute] {action} FAILED: {type(e).__name__}: {e}")
        return False


def with_mic_muted(enabled: bool = True):
    """Decorator to mute microphone during function execution.

    Args:
        enabled: Whether muting is enabled (reads KLR_TTS_MUTE if None)

    Usage:
        @with_mic_muted()
        def synthesize_speech(text):
            # Mic will be muted during this function
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Check if muting is enabled
            mute_enabled = os.getenv("KLR_TTS_MUTE", "1") == "1" if enabled else False

            if not mute_enabled:
                return func(*args, **kwargs)

            # Mute microphone
            _mute_source(True)

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Wait for TTS audio to finish playing + buffer
                mute_duration_ms = int(os.getenv("KLR_TTS_MUTE_DURATION_MS", "1200"))
                time.sleep(mute_duration_ms / 1000.0)

                return result
            finally:
                # Always unmute, even if function raises exception
                _mute_source(False)

        return wrapper
    return decorator


def mute_during_playback(audio_duration_s: float, buffer_ms: int = 500, audio_backend=None):
    """Context manager to pause audio capture during TTS playback.

    Args:
        audio_duration_s: Duration of audio playback in seconds (informational only)
        buffer_ms: Additional buffer time after playback (milliseconds)
        audio_backend: Audio backend to pause (if None, uses hardware mute fallback)

    Usage:
        with mute_during_playback(audio_duration_s=2.5, audio_backend=backend):
            subprocess.run(["play", "audio.wav"])  # Blocks until playback finishes
    """
    class MuteContext:
        def __enter__(self):
            if os.getenv("KLR_TTS_MUTE", "1") == "1":
                if audio_backend and hasattr(audio_backend, 'pause'):
                    # Pause audio capture thread (preferred method)
                    audio_backend.pause()
                else:
                    # Fallback to hardware mute
                    _mute_source(True)
                    print(f"[mic_mute] Microphone muted for playback (hardware)")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if os.getenv("KLR_TTS_MUTE", "1") == "1":
                # Small buffer before resuming
                time.sleep(buffer_ms / 1000.0)

                if audio_backend and hasattr(audio_backend, 'resume'):
                    # Resume audio capture thread
                    audio_backend.resume()
                    # CRITICAL: Flush ring buffer to discard residual TTS audio still in pipeline
                    # Audio continues flowing from PulseAudio->pacat->thread for ~500ms after resume
                    time.sleep(0.5)  # Let pipeline drain
                    if hasattr(audio_backend, 'flush'):
                        flushed = audio_backend.flush()
                        if flushed > 0:
                            print(f"[mic_mute] Flushed {flushed} samples of residual TTS audio from ring buffer")
                else:
                    # Fallback to hardware unmute
                    _mute_source(False)
                    print(f"[mic_mute] Microphone unmuted (hardware, buffer={buffer_ms}ms)")
            return False  # Don't suppress exceptions

    return MuteContext()
