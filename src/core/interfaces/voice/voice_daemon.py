#!/usr/bin/env python3
"""
KLoROS Voice Daemon - Unified voice service coordinator.

Starts and manages voice services based on configuration:
- Core Pipeline: audio_io, stt, tts, gateway (always enabled)
- Analysis: emotion, intent, session (optional)
- Backend: llm, knowledge (optional)

Environment Variables:
    KLR_VOICE_ENABLE_ANALYSIS=1  - Enable emotion/intent/session services
    KLR_VOICE_ENABLE_BACKEND=1   - Enable llm/knowledge services
    KLR_ENABLE_STT=1            - Enable STT (default: 1)
    KLR_ENABLE_TTS=1            - Enable TTS (default: 1)
    KLR_ENABLE_EMOTION=1        - Enable emotion analysis
    KLR_ENABLE_INTENT=1         - Enable intent classification
    KLR_ENABLE_LLM=1            - Enable LLM service
    KLR_ENABLE_KNOWLEDGE=1      - Enable knowledge/RAG service

Usage:
    python -m kloros.interfaces.voice.voice_daemon

    # Or via systemd:
    systemctl start kloros-voice
"""

import os
import sys
import signal
import logging
import threading
import time
from pathlib import Path
from typing import List, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("voice-daemon")


class VoiceDaemon:
    """Unified voice service daemon."""

    def __init__(self):
        self.services: List[Any] = []
        self.threads: List[threading.Thread] = []
        self.running = True

        self.enable_analysis = int(os.getenv("KLR_VOICE_ENABLE_ANALYSIS", "0"))
        self.enable_backend = int(os.getenv("KLR_VOICE_ENABLE_BACKEND", "0"))

        logger.info("[daemon] VoiceDaemon initializing...")

    def _start_service(self, name: str, service_class: type, enabled: bool = True) -> None:
        """Start a service in its own thread."""
        if not enabled:
            logger.info(f"[daemon] {name} disabled, skipping")
            return

        try:
            service = service_class()
            self.services.append(service)

            def run_service():
                try:
                    service.start()
                    while service.running and self.running:
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"[daemon] {name} error: {e}")

            thread = threading.Thread(target=run_service, name=name, daemon=True)
            thread.start()
            self.threads.append(thread)
            logger.info(f"[daemon] Started {name}")

        except Exception as e:
            logger.error(f"[daemon] Failed to start {name}: {e}")

    def start(self):
        """Start all enabled voice services."""
        logger.info("[daemon] Starting voice services...")

        from src.core.interfaces.voice.audio_io import AudioIOService
        from src.core.interfaces.voice.stt_service import STTService
        from src.core.interfaces.voice.tts_service import TTSService
        from src.core.interfaces.voice.gateway import VoiceGateway

        self._start_service("audio-io", AudioIOService, True)
        self._start_service("stt", STTService, int(os.getenv("KLR_ENABLE_STT", "1")))
        self._start_service("tts", TTSService, int(os.getenv("KLR_ENABLE_TTS", "1")))
        self._start_service("gateway", VoiceGateway, True)

        if self.enable_analysis:
            from src.core.interfaces.voice.emotion_service import EmotionService
            from src.core.interfaces.voice.intent_service import IntentService
            from src.core.interfaces.voice.session_service import SessionService

            self._start_service("emotion", EmotionService, int(os.getenv("KLR_ENABLE_EMOTION", "1")))
            self._start_service("intent", IntentService, int(os.getenv("KLR_ENABLE_INTENT", "1")))
            self._start_service("session", SessionService, int(os.getenv("KLR_ENABLE_SESSION", "1")))

        if self.enable_backend:
            from src.core.interfaces.voice.llm_service import LLMService
            from src.core.interfaces.voice.knowledge_service import KnowledgeService

            self._start_service("llm", LLMService, int(os.getenv("KLR_ENABLE_LLM", "1")))
            self._start_service("knowledge", KnowledgeService, int(os.getenv("KLR_ENABLE_KNOWLEDGE", "1")))

        active_count = len([s for s in self.services if hasattr(s, 'running') and s.running])
        logger.info(f"[daemon] Voice daemon ready ({active_count} services active)")

    def shutdown(self):
        """Graceful shutdown of all services."""
        logger.info("[daemon] Shutting down voice services...")
        self.running = False

        for service in self.services:
            try:
                if hasattr(service, 'shutdown'):
                    service.shutdown()
                elif hasattr(service, 'running'):
                    service.running = False
            except Exception as e:
                logger.error(f"[daemon] Error shutting down service: {e}")

        for thread in self.threads:
            thread.join(timeout=5.0)

        logger.info("[daemon] Voice daemon stopped")


def main():
    """Main entry point for voice daemon."""
    logger.info("[daemon] KLoROS Voice Daemon starting...")

    daemon = VoiceDaemon()

    def signal_handler(signum, frame):
        logger.info(f"[daemon] Received signal {signum}, shutting down...")
        daemon.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon.start()

    try:
        while daemon.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[daemon] Interrupted by user")
    finally:
        daemon.shutdown()


if __name__ == "__main__":
    main()
