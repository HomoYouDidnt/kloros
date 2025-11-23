#!/usr/bin/env python3
"""KLoROS Voice TTS Zooid - Text-to-speech synthesis.

This zooid handles:
- Convert text to speech using Piper/Coqui TTS
- Voice profile management
- Prosody and affective modulation (emotion-aware speech)
- ChemBus signal coordination for TTS events

ChemBus Signals:
- Emits: VOICE.TTS.AUDIO.READY (file path, duration, affective markers)
- Emits: VOICE.TTS.PLAY.AUDIO (file path to trigger playback via Audio I/O zooid)
- Listens: VOICE.ORCHESTRATOR.SPEAK (text, affective state, urgency)
"""
from __future__ import annotations

import os
import sys
import re
import time
import signal
import traceback
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub


class TTSZooid:
    """Text-to-speech zooid for speech synthesis."""

    def __init__(self):
        self.zooid_name = "kloros-voice-tts"
        self.niche = "voice.tts"

        self.chem_pub = ChemPub()

        self.tts_backend: Optional[Any] = None
        self.running = True

        self.enable_tts = int(os.getenv("KLR_ENABLE_TTS", "1"))
        self.tts_backend_name = os.getenv("KLR_TTS_BACKEND", "piper")
        self.tts_sample_rate = int(os.getenv("KLR_TTS_SAMPLE_RATE", "22050"))
        self.tts_out_dir = os.getenv("KLR_TTS_OUT_DIR") or os.path.expanduser("~/.kloros/tts/out")
        self.fail_open_tts = int(os.getenv("KLR_FAIL_OPEN_TTS", "1"))

        Path(self.tts_out_dir).mkdir(parents=True, exist_ok=True)

        self.stats = {
            "total_syntheses": 0,
            "successful_syntheses": 0,
            "failed_syntheses": 0,
            "average_duration": 0.0,
            "synthesis_times": [],
        }

        print(f"[tts] Initialized: backend={self.tts_backend_name}, sample_rate={self.tts_sample_rate}")

    def start(self):
        """Start the TTS zooid and subscribe to ChemBus signals."""
        print(f"[tts] Starting {self.zooid_name}")

        if not self.enable_tts:
            print("[tts] TTS disabled via KLR_ENABLE_TTS=0")
            return

        if self.tts_backend is None:
            self._init_tts_backend()

        if self.tts_backend is None:
            print("[tts] ERROR: Failed to initialize TTS backend, cannot start")
            if not self.fail_open_tts:
                return

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.TTS.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "backend": self.tts_backend_name,
                "sample_rate": self.tts_sample_rate,
                "fail_open": self.fail_open_tts,
            }
        )

        print(f"[tts] {self.zooid_name} ready and listening")

    def _init_tts_backend(self) -> None:
        """Initialize TTS backend based on configuration."""
        try:
            from src.tts.base import create_tts_backend

            self.tts_backend = create_tts_backend(
                self.tts_backend_name,
                out_dir=self.tts_out_dir
            )
            print(f"[tts] ✅ Initialized {self.tts_backend_name} backend")

        except Exception as e:
            print(f"[tts] ❌ Failed to initialize {self.tts_backend_name} backend: {e}")
            print(f"[tts] Error details: {traceback.format_exc()}")

            if self.tts_backend_name != "mock":
                try:
                    from src.tts.base import create_tts_backend
                    self.tts_backend = create_tts_backend("mock", out_dir=self.tts_out_dir)
                    print("[tts] 🔄 Falling back to mock backend")
                except Exception as fallback_e:
                    print(f"[tts] Fallback to mock backend also failed: {fallback_e}")
                    self.tts_backend = None

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for TTS synthesis requests."""
        self.speak_sub = ChemSub(
            "VOICE.ORCHESTRATOR.SPEAK",
            self._on_speak_request,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

        print("[tts] Subscribed to ChemBus signals")

    def _on_speak_request(self, event: dict):
        """Handle VOICE.ORCHESTRATOR.SPEAK signal and synthesize speech.

        Args:
            event: ChemBus event with synthesis parameters
                - facts.text: Text to synthesize
                - facts.affective_state: Optional emotion/affect parameters
                - facts.urgency: Optional urgency level (0.0-1.0)
                - facts.voice: Optional voice override
                - incident_id: Event correlation ID
        """
        if not self.running:
            return

        try:
            facts = event.get("facts", {})
            text = facts.get("text")
            incident_id = event.get("incident_id")

            if not text:
                print("[tts] ERROR: No text in VOICE.ORCHESTRATOR.SPEAK event")
                self._emit_error("missing_text", incident_id)
                return

            affective_state = facts.get("affective_state", {})
            urgency = facts.get("urgency", 0.5)
            voice = facts.get("voice")

            start_time = time.time()

            text_normalized = self._normalize_tts_text(text)

            if self.tts_backend is None:
                if self.fail_open_tts:
                    print(f"[tts] Backend unavailable (fail-open); emitting text-only: {text_normalized}")
                    self._emit_text_only(text_normalized, incident_id)
                    return
                else:
                    print(f"[tts] Backend unavailable and fail_open disabled")
                    self._emit_error("backend_unavailable", incident_id)
                    return

            result = self.tts_backend.synthesize(
                text_normalized,
                sample_rate=self.tts_sample_rate,
                voice=voice or os.getenv("KLR_PIPER_VOICE"),
                out_dir=self.tts_out_dir,
            )

            synthesis_time = time.time() - start_time
            self.stats["synthesis_times"].append(synthesis_time)
            if len(self.stats["synthesis_times"]) > 100:
                self.stats["synthesis_times"] = self.stats["synthesis_times"][-100:]

            self.stats["total_syntheses"] += 1
            self.stats["successful_syntheses"] += 1

            old_avg = self.stats["average_duration"]
            total = self.stats["successful_syntheses"]
            self.stats["average_duration"] = (old_avg * (total - 1) + result.duration_s) / total

            print(f"[tts] Synthesized ({synthesis_time:.2f}s): {result.audio_path} ({result.duration_s:.2f}s)")

            self._save_last_tts_output(result.audio_path)

            self.chem_pub.emit(
                "VOICE.TTS.AUDIO.READY",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "file_path": result.audio_path,
                    "duration_s": result.duration_s,
                    "sample_rate": result.sample_rate,
                    "voice": result.voice,
                    "text": text_normalized,
                    "affective_state": affective_state,
                    "synthesis_time": synthesis_time,
                    "timestamp": datetime.now().isoformat(),
                },
                incident_id=incident_id
            )

            self.chem_pub.emit(
                "VOICE.TTS.PLAY.AUDIO",
                ecosystem="voice",
                intensity=urgency,
                facts={
                    "file_path": result.audio_path,
                    "duration_s": result.duration_s,
                    "timestamp": time.time(),
                },
                incident_id=incident_id
            )

            print(f"[tts] Emitted PLAY.AUDIO signal for {result.audio_path}")

        except Exception as e:
            print(f"[tts] ERROR during synthesis: {e}")
            print(f"[tts] Traceback: {traceback.format_exc()}")
            self.stats["failed_syntheses"] += 1
            self._emit_error(str(e), event.get("incident_id"))

    def _normalize_tts_text(self, text: str) -> str:
        """Normalize text for TTS synthesis.

        Force 'KLoROS' to be pronounced as a word, not spelled out.
        Piper TTS needs phonetic hints to avoid treating it as an acronym.

        Args:
            text: Raw text to normalize

        Returns:
            Normalized text suitable for TTS
        """
        text = re.sub(
            r"\b([kK])\.?\s*([lL])\.?\s*([oO])\.?\s*([rR])\.?\s*([oO])\.?\s*([sS])\.?",
            r"Kloros",
            text
        )
        text = re.sub(r"\bkloros\b", "Kloros", text, flags=re.IGNORECASE)
        text = re.sub(r"\bKLoROS\b", "Kloros", text)
        text = re.sub(r"\bKloros\.\s+", "Kloros ", text)

        return text

    def _save_last_tts_output(self, audio_path: str):
        """Save last TTS output for E2E testing and debugging.

        Args:
            audio_path: Path to synthesized audio file
        """
        try:
            import shutil
            last_tts_path = Path.home() / ".kloros" / "tts" / "last.wav"
            last_tts_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio_path, last_tts_path)
            print(f"[tts] Saved to {last_tts_path} for E2E testing")
        except Exception as e:
            print(f"[tts] Failed to save last output: {e}")

    def _emit_text_only(self, text: str, incident_id: Optional[str]):
        """Emit text-only response when TTS backend unavailable.

        Args:
            text: Text that would have been synthesized
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.TTS.TEXT.ONLY",
            ecosystem="voice",
            intensity=0.5,
            facts={
                "text": text,
                "reason": "backend_unavailable",
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def _emit_error(self, error: str, incident_id: Optional[str]):
        """Emit TTS error signal.

        Args:
            error: Error message or type
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.TTS.ERROR",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "error": error,
                "backend": self.tts_backend_name,
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def get_stats(self) -> dict:
        """Get TTS zooid statistics.

        Returns:
            Dictionary with synthesis statistics
        """
        avg_synthesis_time = (
            sum(self.stats["synthesis_times"]) / len(self.stats["synthesis_times"])
            if self.stats["synthesis_times"] else 0.0
        )

        return {
            **self.stats,
            "average_synthesis_time": avg_synthesis_time,
        }

    def shutdown(self):
        """Graceful shutdown of TTS zooid."""
        print(f"[tts] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[tts] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.TTS.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "stats": final_stats,
            }
        )

        try:
            if hasattr(self, 'speak_sub'):
                self.speak_sub.close()
            self.chem_pub.close()
        except Exception as e:
            print(f"[tts] Error closing ChemBus connections: {e}")

        print(f"[tts] {self.zooid_name} shutdown complete")


def main():
    """Main entry point for TTS zooid daemon."""
    print("[tts] Starting KLoROS Voice TTS Zooid")

    zooid = TTSZooid()

    def signal_handler(signum, frame):
        print(f"[tts] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[tts] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
