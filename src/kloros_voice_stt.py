#!/usr/bin/env python3
"""KLoROS Voice STT Zooid - Speech recognition and transcription.

This zooid handles:
- Convert audio to text using Whisper/VOSK/hybrid STT
- Whisper integration (local model inference)
- Speech endpoint detection (via VAD preprocessing)
- Audio preprocessing and normalization
- ChemBus signal coordination for transcription events

ChemBus Signals:
- Emits: VOICE.STT.TRANSCRIPTION (text, confidence, language, metadata)
- Listens: VOICE.AUDIO.CAPTURED (raw PCM data from Audio I/O zooid)
"""
from __future__ import annotations

import os
import sys
import time
import signal
import traceback
from pathlib import Path
from typing import Optional
from datetime import datetime

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub
from src.stt.base import SttBackend, create_stt_backend


class STTZooid:
    """Speech-to-text zooid for audio transcription."""

    def __init__(self):
        self.zooid_name = "kloros-voice-stt"
        self.niche = "voice.stt"

        self.chem_pub = ChemPub()

        self.stt_backend: Optional[SttBackend] = None
        self.running = True

        self.enable_stt = int(os.getenv("KLR_ENABLE_STT", "1"))
        self.stt_backend_name = os.getenv("KLR_STT_BACKEND", "hybrid")
        self.stt_lang = os.getenv("KLR_STT_LANG", "en-US")

        self.stats = {
            "total_transcriptions": 0,
            "successful_transcriptions": 0,
            "failed_transcriptions": 0,
            "average_confidence": 0.0,
            "processing_times": [],
        }

        print(f"[stt] Initialized: backend={self.stt_backend_name}, lang={self.stt_lang}")

    def start(self):
        """Start the STT zooid and subscribe to ChemBus signals."""
        print(f"[stt] Starting {self.zooid_name}")

        if not self.enable_stt:
            print("[stt] STT disabled via KLR_ENABLE_STT=0")
            return

        self._init_stt_backend()

        if self.stt_backend is None:
            print("[stt] ERROR: Failed to initialize STT backend, cannot start")
            return

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.STT.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "backend": self.stt_backend_name,
                "language": self.stt_lang,
            }
        )

        print(f"[stt] {self.zooid_name} ready and listening")

    def _init_stt_backend(self) -> None:
        """Initialize STT backend based on configuration."""
        if create_stt_backend is None:
            print("[stt] ERROR: create_stt_backend not available")
            return

        try:
            backend_kwargs = {}

            if self.stt_backend_name == "hybrid":
                backend_kwargs.update({
                    "vosk_model_dir": os.getenv("ASR_VOSK_MODEL"),
                    "whisper_model_size": os.getenv("ASR_WHISPER_SIZE", "medium"),
                    "whisper_device": "auto",
                    "whisper_device_index": int(os.getenv("ASR_PRIMARY_GPU", "0")),
                    "correction_threshold": float(os.getenv("ASR_CORRECTION_THRESHOLD", "0.75")),
                    "confidence_boost_threshold": float(os.getenv("ASR_CONFIDENCE_BOOST_THRESHOLD", "0.9")),
                    "enable_corrections": bool(int(os.getenv("ASR_ENABLE_CORRECTIONS", "1"))),
                })
                print(f"[stt] Configuring hybrid ASR: VOSK + Whisper-{backend_kwargs['whisper_model_size']}")
                print(f"[stt] Correction threshold: {backend_kwargs['correction_threshold']}, GPU: {backend_kwargs['whisper_device_index']}")
            elif self.stt_backend_name == "vosk":
                if os.getenv("ASR_VOSK_MODEL"):
                    backend_kwargs["model_dir"] = os.getenv("ASR_VOSK_MODEL")
            elif self.stt_backend_name == "whisper":
                backend_kwargs.update({
                    "model_size": os.getenv("ASR_WHISPER_SIZE", "medium"),
                    "device": "auto",
                    "device_index": int(os.getenv("ASR_PRIMARY_GPU", "0")),
                    "model_dir": os.getenv("ASR_WHISPER_MODEL"),
                })

            self.stt_backend = create_stt_backend(self.stt_backend_name, **backend_kwargs)
            print(f"[stt] ✅ Initialized {self.stt_backend_name} backend")

            if hasattr(self.stt_backend, 'get_info') and self.stt_backend_name == "hybrid":
                info = self.stt_backend.get_info()
                print(f"[stt] 🔀 Hybrid strategy ready - corrections: {info.get('enable_corrections', False)}")

        except Exception as e:
            print(f"[stt] ❌ Failed to initialize {self.stt_backend_name} backend: {e}")
            print(f"[stt] Error details: {traceback.format_exc()}")

            if self.stt_backend_name != "mock":
                try:
                    self.stt_backend = create_stt_backend("mock")
                    print("[stt] 🔄 Falling back to mock backend")
                except Exception as fallback_e:
                    print(f"[stt] Fallback to mock backend also failed: {fallback_e}")
                    self.stt_backend = None

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for audio transcription."""
        self.audio_sub = ChemSub(
            "VOICE.AUDIO.CAPTURED",
            self._on_audio_captured,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

    def _on_audio_captured(self, event):
        """Handle VOICE.AUDIO.CAPTURED signal and transcribe audio.

        Args:
            event: ChemBus event with audio data
                - facts.audio_file: Path to captured audio WAV file
                - facts.duration: Duration in seconds
                - facts.sample_rate: Audio sample rate
                - facts.timestamp: Capture timestamp
        """
        if not self.running or self.stt_backend is None:
            return

        try:
            facts = event.get("facts", {})
            audio_file = facts.get("audio_file")

            if not audio_file:
                print("[stt] ERROR: No audio_file in VOICE.AUDIO.CAPTURED event")
                return

            audio_file_path = Path(audio_file)
            if not audio_file_path.exists():
                print(f"[stt] ERROR: Audio file not found: {audio_file}")
                return

            start_time = time.time()

            audio_data, sample_rate = self._load_audio_file(audio_file_path)

            if audio_data is None:
                print(f"[stt] ERROR: Failed to load audio from {audio_file}")
                self.stats["failed_transcriptions"] += 1
                return

            result = self.stt_backend.transcribe(
                audio=audio_data,
                sample_rate=sample_rate,
                lang=self.stt_lang.split("-")[0] if "-" in self.stt_lang else self.stt_lang
            )

            processing_time = time.time() - start_time
            self.stats["processing_times"].append(processing_time)
            if len(self.stats["processing_times"]) > 100:
                self.stats["processing_times"] = self.stats["processing_times"][-100:]

            self.stats["total_transcriptions"] += 1
            if result.transcript:
                self.stats["successful_transcriptions"] += 1

                old_avg = self.stats["average_confidence"]
                total = self.stats["successful_transcriptions"]
                self.stats["average_confidence"] = (old_avg * (total - 1) + result.confidence) / total

            self.chem_pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=result.confidence,
                facts={
                    "text": result.transcript,
                    "confidence": result.confidence,
                    "language": result.lang,
                    "audio_file": str(audio_file),
                    "duration": facts.get("duration", 0.0),
                    "processing_time": processing_time,
                    "backend": self.stt_backend_name,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            print(f"[stt] Transcribed ({processing_time:.2f}s, conf={result.confidence:.2f}): {result.transcript[:100]}")

        except Exception as e:
            print(f"[stt] ERROR during transcription: {e}")
            print(f"[stt] Traceback: {traceback.format_exc()}")
            self.stats["failed_transcriptions"] += 1

    def _load_audio_file(self, audio_file: Path) -> tuple[Optional[np.ndarray], int]:
        """Load audio file and return normalized float32 audio data.

        Args:
            audio_file: Path to WAV audio file

        Returns:
            Tuple of (audio_data, sample_rate) or (None, 0) on error
        """
        try:
            import wave

            with wave.open(str(audio_file), 'rb') as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()

                audio_bytes = wf.readframes(n_frames)

                if sampwidth == 2:
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                elif sampwidth == 4:
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int32).astype(np.int16)
                else:
                    print(f"[stt] WARNING: Unsupported sample width {sampwidth}, assuming int16")
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)

                if n_channels > 1:
                    audio_int16 = audio_int16.reshape(-1, n_channels)
                    audio_int16 = np.mean(audio_int16, axis=1).astype(np.int16)

                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                return audio_float32, sample_rate

        except Exception as e:
            print(f"[stt] ERROR loading audio file {audio_file}: {e}")
            return None, 0

    def get_stats(self) -> dict:
        """Get STT zooid statistics.

        Returns:
            Dictionary with transcription statistics
        """
        avg_processing_time = (
            sum(self.stats["processing_times"]) / len(self.stats["processing_times"])
            if self.stats["processing_times"] else 0.0
        )

        return {
            **self.stats,
            "average_processing_time": avg_processing_time,
        }

    def shutdown(self):
        """Graceful shutdown of STT zooid."""
        print(f"[stt] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[stt] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.STT.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "stats": final_stats,
            }
        )


def main():
    """Main entry point for STT zooid daemon."""
    print("[stt] Starting KLoROS Voice STT Zooid")

    zooid = STTZooid()

    def signal_handler(signum, frame):
        print(f"[stt] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[stt] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
