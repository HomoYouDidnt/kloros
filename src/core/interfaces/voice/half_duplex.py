#!/usr/bin/env python3
"""
Half-duplex audio management for KLoROS voice services.

Extracted from kloros_voice.py to keep services modular.

Handles:
- TTS suppression (don't record while speaking)
- Anti-echo cooldown and queue flushing
- Listening indicator beep
- Suppression watchdog

Usage:
    from src.core.interfaces.voice.half_duplex import HalfDuplexManager

    hdm = HalfDuplexManager(playback_cmd=["paplay"])
    hdm.pre_tts_suppress()
    # ... play TTS audio ...
    hdm.post_tts_cooldown(audio_duration_s=2.5)
    hdm.clear_tts_suppress()
"""

import os
import time
import wave
import queue
import tempfile
import threading
import subprocess
from typing import Optional, Callable

import numpy as np


class HalfDuplexManager:
    """Manages half-duplex audio state for voice services.

    Half-duplex means: don't record while speaking (prevents echo feedback).
    """

    def __init__(
        self,
        playback_cmd: Optional[list] = None,
        extra_tail_ms: int = 300,
        flush_passes: int = 3,
        flush_gap_ms: int = 50,
    ):
        """Initialize half-duplex manager.

        Args:
            playback_cmd: Command for audio playback (e.g., ["paplay"])
            extra_tail_ms: Default echo tail in milliseconds
            flush_passes: Number of queue flush passes
            flush_gap_ms: Gap between flush passes in milliseconds
        """
        self.playback_cmd = playback_cmd or ["paplay"]
        self.extra_tail_ms = extra_tail_ms
        self.flush_passes = flush_passes
        self.flush_gap_ms = flush_gap_ms

        self.tts_playing_evt = threading.Event()
        self._tts_armed_at: Optional[float] = None
        self.audio_queue: Optional[queue.Queue] = None

    def set_audio_queue(self, q: queue.Queue) -> None:
        """Set the audio queue for flushing."""
        self.audio_queue = q

    def is_suppressed(self) -> bool:
        """Check if audio capture is currently suppressed."""
        return self.tts_playing_evt.is_set()

    def pre_tts_suppress(self, asr_pause_callback: Optional[Callable] = None) -> None:
        """Arm suppression before TTS playback.

        Args:
            asr_pause_callback: Optional callback to pause ASR
        """
        self.tts_playing_evt.set()
        self._tts_armed_at = time.monotonic()

        if asr_pause_callback:
            try:
                asr_pause_callback()
            except Exception:
                pass

        print("[HALFDUPLEX] suppression enabled")

    def clear_tts_suppress(
        self,
        play_indicator: bool = True,
        asr_resume_callback: Optional[Callable] = None
    ) -> None:
        """Disarm suppression after TTS playback.

        Args:
            play_indicator: If True, play listening indicator beep
            asr_resume_callback: Optional callback to resume ASR
        """
        self.tts_playing_evt.clear()
        self._tts_armed_at = None

        if asr_resume_callback:
            try:
                asr_resume_callback()
            except Exception:
                pass

        print("[HALFDUPLEX] suppression disabled - ready to listen")

        indicator_enabled = int(os.getenv("KLR_LISTENING_INDICATOR", "1"))
        if play_indicator and indicator_enabled:
            self.play_listening_beep()

    def play_listening_beep(self, audio_backend=None) -> None:
        """Play a short beep to indicate ready to listen.

        Args:
            audio_backend: Optional audio backend for mic muting
        """
        try:
            sample_rate = 22050
            duration = 0.08
            frequency = 880
            samples = int(sample_rate * duration)

            t = np.linspace(0, duration, samples, dtype=np.float32)
            beep = np.sin(2 * np.pi * frequency * t)

            fade_samples = int(sample_rate * 0.01)
            beep[:fade_samples] *= np.linspace(0, 1, fade_samples, dtype=np.float32)
            beep[-fade_samples:] *= np.linspace(1, 0, fade_samples, dtype=np.float32)

            beep_int16 = (beep * 16384).astype(np.int16)

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                beep_path = f.name
                with wave.open(beep_path, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(beep_int16.tobytes())

            cmd = self.playback_cmd + [beep_path]
            print(f"[indicator] Playing beep: {' '.join(cmd)}")

            if audio_backend:
                try:
                    from src.voice.audio.mic_mute import mute_during_playback
                    with mute_during_playback(audio_duration_s=0.2, buffer_ms=100, audio_backend=audio_backend):
                        subprocess.run(cmd, capture_output=True, check=False, timeout=1.0)
                except ImportError:
                    subprocess.run(cmd, capture_output=True, check=False, timeout=1.0)
            else:
                subprocess.run(cmd, capture_output=True, check=False, timeout=1.0)

            try:
                os.unlink(beep_path)
            except Exception:
                pass

        except Exception as e:
            print(f"[indicator] Beep playback skipped: {e}")

    def duplex_healthcheck(self) -> None:
        """Safety watchdog: auto-clear stuck suppression after 30s."""
        if self.tts_playing_evt.is_set() and self._tts_armed_at:
            if time.monotonic() - self._tts_armed_at > 30:
                print("[HALFDUPLEX] WARNING: suppression stuck >30s, auto-clearing")
                self.tts_playing_evt.clear()
                self._tts_armed_at = None

    def drain_queue(self, max_items: int = 10000) -> int:
        """Bounded queue purge to prevent infinite loops.

        Args:
            max_items: Maximum items to drain

        Returns:
            Number of items drained
        """
        if not self.audio_queue:
            return 0

        n = 0
        while n < max_items:
            try:
                self.audio_queue.get_nowait()
                n += 1
            except queue.Empty:
                break
        return n

    def post_tts_cooldown(self, audio_duration_s: float = 0.0) -> None:
        """Wait for echo tail, then flush queued audio chunks.

        Args:
            audio_duration_s: Duration of TTS audio for dynamic tail calculation
        """
        if audio_duration_s > 0:
            if audio_duration_s < 1.0:
                tail_ms = 200
            elif audio_duration_s < 3.0:
                tail_ms = 300
            else:
                tail_ms = min(900, 300 + int((audio_duration_s - 3.0) * 100))
            print(f"[ANTI-ECHO] Dynamic tail: {tail_ms}ms (audio: {audio_duration_s:.2f}s)")
        else:
            tail_ms = self.extra_tail_ms
            print(f"[ANTI-ECHO] Static tail: {tail_ms}ms (no duration)")

        time.sleep(tail_ms / 1000.0)

        total = 0
        for p in range(self.flush_passes):
            flushed = self.drain_queue()
            total += flushed
            if flushed:
                print(f"[ANTI-ECHO] flush pass {p+1}: {flushed} chunks")
            time.sleep(self.flush_gap_ms / 1000.0)

        if total == 0:
            print("[ANTI-ECHO] queue already empty post-TTS")


def rms16(b: bytes) -> int:
    """Short-term RMS of int16 mono chunk (energy gate for wake).

    Args:
        b: Raw audio bytes (int16 mono)

    Returns:
        RMS value as integer
    """
    if not b:
        return 0
    a = np.frombuffer(b, dtype=np.int16).astype(np.int32)
    return int(np.sqrt(np.mean(a * a)) or 0)


def chunker(data: bytes, sr: int, frame_ms: int, buffer: bytes = b"") -> tuple[list[bytes], bytes]:
    """Yield fixed-size frames for VAD from arbitrary-sized input bytes.

    Args:
        data: Input audio bytes
        sr: Sample rate
        frame_ms: Frame size in milliseconds
        buffer: Leftover buffer from previous call

    Returns:
        Tuple of (list of frames, remaining buffer)
    """
    frame_bytes = int(sr * (frame_ms / 1000.0)) * 2
    buf = buffer + data
    pos = 0
    frames = []
    while pos + frame_bytes <= len(buf):
        frames.append(buf[pos : pos + frame_bytes])
        pos += frame_bytes
    return frames, buf[pos:]
