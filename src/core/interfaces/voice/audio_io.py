#!/usr/bin/env python3
"""KLoROS Voice Audio I/O Service - Raw audio capture and playback via PulseAudio.

This service handles:
- Raw audio capture via PulseAudio (pacat subprocess)
- Audio file playback via PulseAudio (paplay)
- Audio file persistence (WAV writing to /home/kloros/audio_recordings/)
- UMN signal coordination for audio I/O events

UMN Signals:
- Emits: VOICE.AUDIO.CAPTURED (raw PCM data, timestamp, duration)
- Emits: VOICE.AUDIO.PLAYBACK.COMPLETE (file path, duration)
- Listens: VOICE.TTS.PLAY.AUDIO (file path to play)
- Listens: VOICE.STT.RECORD.START (begin capture)
- Listens: VOICE.STT.RECORD.STOP (end capture)
"""
from __future__ import annotations

import os
import sys
import time
import wave
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.core.umn_bus import UMNPub, UMNSub
from src.voice.audio.capture import PulseAudioBackend

try:
    from src.voice.audio.calibration import load_profile
except ImportError:
    load_profile = None


class AudioIOService:
    """Audio I/O service for PulseAudio capture and playback."""

    def __init__(self):
        self.service_name = "kloros-voice-audio-io"
        self.niche = "voice.audio_io"

        self.chem_pub = UMNPub()

        self.audio_backend: Optional[PulseAudioBackend] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.capturing = False
        self.running = True

        self.sample_rate = int(os.getenv("KLR_AUDIO_SAMPLE_RATE", "16000"))
        self.channels = 1

        self.recordings_dir = Path(os.getenv("KLR_AUDIO_RECORDINGS_DIR", "/home/kloros/audio_recordings"))
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

        self.paplay_path = shutil.which("paplay")
        if not self.paplay_path:
            print("[audio-io] WARNING: paplay not found, playback will fail")

        self.playback_runtime = os.getenv("KLR_PLAYBACK_USER_RUNTIME")

        self.vad_threshold_dbfs: Optional[float] = None
        self.agc_gain_db: float = 0.0
        self._load_calibration_profile()

        print(f"[audio-io] Initialized: sample_rate={self.sample_rate}, recordings_dir={self.recordings_dir}")

    def _load_calibration_profile(self) -> None:
        """Load microphone calibration profile if available."""
        if load_profile is None:
            return

        try:
            profile = load_profile()
            if profile is not None:
                self.vad_threshold_dbfs = profile.vad_threshold_dbfs
                self.agc_gain_db = profile.agc_gain_db
                print(
                    f"[audio-io] Loaded calibration: VAD={profile.vad_threshold_dbfs:.1f}dBFS, "
                    f"AGC={profile.agc_gain_db:.1f}dB"
                )
        except Exception as e:
            print(f"[audio-io] Calibration profile not loaded: {e}")

    def start(self):
        """Start the audio I/O service and subscribe to UMN signals."""
        print(f"[audio-io] Starting {self.service_name}")

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.AUDIO.IO.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "service": self.service_name,
                "sample_rate": self.sample_rate,
                "paplay_available": self.paplay_path is not None
            }
        )

        print(f"[audio-io] {self.service_name} ready and listening")

    def _subscribe_to_signals(self):
        """Subscribe to UMN signals for audio I/O control."""
        self.play_sub = UMNSub(
            "VOICE.TTS.PLAY.AUDIO",
            self._on_play_audio,
            zooid_name=self.service_name,
            niche=self.niche
        )

        self.record_start_sub = UMNSub(
            "VOICE.STT.RECORD.START",
            self._on_record_start,
            zooid_name=self.service_name,
            niche=self.niche
        )

        self.record_stop_sub = UMNSub(
            "VOICE.STT.RECORD.STOP",
            self._on_record_stop,
            zooid_name=self.service_name,
            niche=self.niche
        )

        print("[audio-io] Subscribed to UMN signals")

    def _on_play_audio(self, msg: dict):
        """Handle VOICE.TTS.PLAY.AUDIO signal - play an audio file."""
        try:
            file_path = msg.get("facts", {}).get("file_path")
            if not file_path:
                print("[audio-io] ERROR: PLAY.AUDIO signal missing file_path")
                return

            if not os.path.exists(file_path):
                print(f"[audio-io] ERROR: Audio file not found: {file_path}")
                return

            print(f"[audio-io] Playing audio file: {file_path}")

            start_time = time.time()
            success = self._play_audio_file(file_path)
            duration = time.time() - start_time

            if success:
                self.chem_pub.emit(
                    "VOICE.AUDIO.PLAYBACK.COMPLETE",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "file_path": file_path,
                        "duration_s": duration,
                        "timestamp": time.time()
                    },
                    incident_id=msg.get("incident_id")
                )
                print(f"[audio-io] Playback complete: {duration:.2f}s")
            else:
                print("[audio-io] Playback failed")

        except Exception as e:
            print(f"[audio-io] ERROR in _on_play_audio: {e}")

    def _play_audio_file(self, file_path: str) -> bool:
        """Play an audio file using paplay.

        Args:
            file_path: Path to audio file to play

        Returns:
            True if playback succeeded, False otherwise
        """
        if not self.paplay_path:
            print("[audio-io] ERROR: paplay not available")
            return False

        try:
            env = os.environ.copy()

            if self.playback_runtime:
                env["XDG_RUNTIME_DIR"] = self.playback_runtime
                env["PULSE_RUNTIME_PATH"] = f"{self.playback_runtime}/pulse"
            elif "XDG_RUNTIME_DIR" not in env:
                env["XDG_RUNTIME_DIR"] = "/run/user/1001"
                env["PULSE_RUNTIME_PATH"] = "/run/user/1001/pulse"

            result = subprocess.run(
                [self.paplay_path, file_path],
                env=env,
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                return True
            else:
                stderr = result.stderr.decode() if result.stderr else ""
                print(f"[audio-io] paplay failed: {stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("[audio-io] ERROR: Playback timeout")
            return False
        except Exception as e:
            print(f"[audio-io] ERROR: Playback exception: {e}")
            return False

    def _on_record_start(self, msg: dict):
        """Handle VOICE.STT.RECORD.START signal - begin audio capture."""
        try:
            if self.capturing:
                print("[audio-io] WARNING: Already capturing, ignoring START signal")
                return

            print("[audio-io] Starting audio capture")

            if not self.audio_backend:
                self.audio_backend = PulseAudioBackend()
                self.audio_backend.open(self.sample_rate, self.channels)

            self.capturing = True

            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                args=(msg.get("incident_id"),),
                daemon=True
            )
            self.capture_thread.start()

            print("[audio-io] Audio capture started")

        except Exception as e:
            print(f"[audio-io] ERROR in _on_record_start: {e}")
            self.capturing = False

    def _on_record_stop(self, msg: dict):
        """Handle VOICE.STT.RECORD.STOP signal - end audio capture."""
        try:
            if not self.capturing:
                print("[audio-io] WARNING: Not capturing, ignoring STOP signal")
                return

            print("[audio-io] Stopping audio capture")
            self.capturing = False

            if self.capture_thread:
                self.capture_thread.join(timeout=2.0)
                self.capture_thread = None

            print("[audio-io] Audio capture stopped")

        except Exception as e:
            print(f"[audio-io] ERROR in _on_record_stop: {e}")

    def _capture_loop(self, incident_id: Optional[str] = None):
        """Capture audio and emit UMN signals with captured data."""
        try:
            captured_chunks = []
            capture_start = time.time()

            print("[audio-io] Capture loop started")

            for chunk in self.audio_backend.chunks(block_ms=100):
                if not self.capturing:
                    break

                captured_chunks.append(chunk)

                if len(captured_chunks) * 0.1 >= 0.5:
                    audio_data = np.concatenate(captured_chunks)
                    duration = len(audio_data) / self.sample_rate

                    wav_path = self._save_audio_chunk(audio_data, capture_start)

                    self.chem_pub.emit(
                        "VOICE.AUDIO.CAPTURED",
                        ecosystem="voice",
                        intensity=1.0,
                        facts={
                            "audio_file": str(wav_path),
                            "duration_s": duration,
                            "sample_rate": self.sample_rate,
                            "samples": len(audio_data),
                            "timestamp": time.time()
                        },
                        incident_id=incident_id
                    )

                    captured_chunks = []
                    capture_start = time.time()

            if captured_chunks:
                audio_data = np.concatenate(captured_chunks)
                duration = len(audio_data) / self.sample_rate

                if duration > 0.1:
                    wav_path = self._save_audio_chunk(audio_data, capture_start)

                    self.chem_pub.emit(
                        "VOICE.AUDIO.CAPTURED",
                        ecosystem="voice",
                        intensity=1.0,
                        facts={
                            "audio_file": str(wav_path),
                            "duration_s": duration,
                            "sample_rate": self.sample_rate,
                            "samples": len(audio_data),
                            "timestamp": time.time()
                        },
                        incident_id=incident_id
                    )

            print("[audio-io] Capture loop finished")

        except Exception as e:
            print(f"[audio-io] ERROR in capture loop: {e}")

    def _save_audio_chunk(self, audio_data: np.ndarray, timestamp: float) -> Path:
        """Save audio chunk to WAV file.

        Args:
            audio_data: Audio samples as float32 array
            timestamp: Timestamp for filename

        Returns:
            Path to saved WAV file
        """
        dt = datetime.fromtimestamp(timestamp)
        filename = f"capture_{dt.strftime('%Y%m%d_%H%M%S_%f')}.wav"
        wav_path = self.recordings_dir / filename

        audio_int16 = (audio_data * 32767).astype(np.int16)

        with wave.open(str(wav_path), 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        print(f"[audio-io] Saved audio chunk: {wav_path} ({len(audio_data)} samples)")

        return wav_path

    def shutdown(self):
        """Shutdown the audio I/O service cleanly."""
        print(f"[audio-io] Shutting down {self.service_name}")

        self.running = False
        self.capturing = False

        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)

        if self.audio_backend:
            try:
                self.audio_backend.close()
            except Exception as e:
                print(f"[audio-io] Error closing audio backend: {e}")

        try:
            self.play_sub.close()
            self.record_start_sub.close()
            self.record_stop_sub.close()
            self.chem_pub.close()
        except Exception as e:
            print(f"[audio-io] Error closing UMN connections: {e}")

        print(f"[audio-io] {self.service_name} shutdown complete")


def main():
    """Main entry point for audio I/O service daemon."""
    print("[audio-io] KLoROS Voice Audio I/O Service starting...")

    service = AudioIOService()

    def signal_handler(signum, frame):
        print(f"[audio-io] Received signal {signum}, shutting down...")
        service.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()

        while service.running:
            time.sleep(1)

    except Exception as e:
        print(f"[audio-io] FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        service.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
