#!/usr/bin/env python3
"""
KLoROS Voice Gateway - Thin coordinator for voice services.

This is NOT an orchestrator or brain - it's a simple router that:
1. Coordinates voice services (audio_io, STT, TTS)
2. Routes user speech to MetaAgentKLoROS for reasoning
3. Routes responses back to TTS for speech output
4. Handles half-duplex coordination (don't listen while speaking)

The actual reasoning happens in MetaAgentKLoROS, not here.
This gateway just pipes speech in and responses out.

UMN Signals:
    Subscribes:
        - VOICE.STT.TRANSCRIPTION (user said something)
        - VOICE.TTS.AUDIO.READY (TTS finished generating audio)
        - VOICE.AUDIO.PLAYBACK.COMPLETE (audio finished playing)

    Emits:
        - VOICE.STT.RECORD.START (tell audio_io to start recording)
        - VOICE.STT.RECORD.STOP (tell audio_io to stop recording)
        - VOICE.ORCHESTRATOR.SPEAK (tell TTS to synthesize)
        - VOICE.USER.INPUT (send transcription to MetaAgentKLoROS)

Future Work:
    - Add wake word detection
    - Add streaming support for lower latency
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from src.orchestration.core.umn_bus import UMNPub, UMNSub

logger = logging.getLogger(__name__)


class VoiceGateway:
    """
    Thin voice gateway - coordinates services, routes to meta-agent.

    This is infrastructure, not a brain. All reasoning happens elsewhere.
    """

    def __init__(self):
        self.gateway_name = "kloros-voice-gateway"
        self.niche = "voice.gateway"

        self.chem_pub = UMNPub()
        self.running = True

        self.is_speaking = False
        self.is_listening = False
        self.last_speech_end = 0.0

        self.cooldown_after_speech_s = float(os.getenv("KLR_SPEECH_COOLDOWN", "0.5"))

        self.meta_agent_connected = True  # MetaAgentKLoROS handles VOICE.USER.INPUT

        self.stats = {
            "transcriptions_received": 0,
            "responses_spoken": 0,
            "start_time": time.time(),
        }

        logger.info(f"[gateway] VoiceGateway initialized")

    def start(self):
        """Start the voice gateway and subscribe to UMN signals."""
        logger.info(f"[gateway] Starting {self.gateway_name}")

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.GATEWAY.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "gateway": self.gateway_name,
                "meta_agent_connected": self.meta_agent_connected,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(f"[gateway] {self.gateway_name} ready")
        logger.info("[gateway] ✓ MetaAgentKLoROS handles VOICE.USER.INPUT for reasoning")

    def _subscribe_to_signals(self):
        """Subscribe to UMN signals from voice services."""

        self.stt_sub = UMNSub(
            topic="VOICE.STT.TRANSCRIPTION",
            on_json=self._on_transcription,
            zooid_name=self.gateway_name,
            niche=self.niche
        )

        self.tts_ready_sub = UMNSub(
            topic="VOICE.TTS.AUDIO.READY",
            on_json=self._on_tts_ready,
            zooid_name=self.gateway_name,
            niche=self.niche
        )

        self.playback_complete_sub = UMNSub(
            topic="VOICE.AUDIO.PLAYBACK.COMPLETE",
            on_json=self._on_playback_complete,
            zooid_name=self.gateway_name,
            niche=self.niche
        )

        logger.info("[gateway] Subscribed to voice service signals")

    def _on_transcription(self, msg: dict):
        """
        Handle user speech transcription.

        Emits VOICE.USER.INPUT for MetaAgentKLoROS to process.
        MetaAgentKLoROS handles query classification, RAG retrieval, and LLM response.
        """
        if not self.running:
            return

        facts = msg.get("facts", {})
        text = facts.get("text", "").strip()
        confidence = facts.get("confidence", 0.0)
        incident_id = msg.get("incident_id")

        if not text:
            logger.debug("[gateway] Empty transcription, ignoring")
            return

        self.stats["transcriptions_received"] += 1
        logger.info(f"[gateway] Received transcription: '{text[:100]}...' (conf={confidence:.2f})")

        if self.meta_agent_connected:
            self.chem_pub.emit(
                "VOICE.USER.INPUT",
                ecosystem="voice",
                intensity=confidence,
                facts={
                    "text": text,
                    "confidence": confidence,
                    "source": "voice",
                    "timestamp": datetime.now().isoformat(),
                },
                incident_id=incident_id
            )
            logger.debug("[gateway] Routed to meta-agent")
        else:
            logger.warning("[gateway] Meta-agent not connected, using stub response")
            self._stub_response(text, incident_id)

    def _stub_response(self, user_text: str, incident_id: Optional[str] = None):
        """
        Temporary stub response when meta-agent not connected.

        This will be removed once gateway is wired to MetaAgentKLoROS.
        """
        stub_text = (
            "Voice gateway received your message, but the meta-agent connection "
            "is not yet implemented. This is a stub response."
        )

        self._emit_speak(stub_text, incident_id)

    def _on_tts_ready(self, msg: dict):
        """Handle TTS audio ready signal - playback coordination."""
        facts = msg.get("facts", {})
        audio_file = facts.get("audio_file")

        if audio_file:
            logger.debug(f"[gateway] TTS ready: {audio_file}")
            self.is_speaking = True

    def _on_playback_complete(self, msg: dict):
        """Handle audio playback complete - re-enable listening."""
        self.is_speaking = False
        self.last_speech_end = time.time()

        logger.debug("[gateway] Playback complete, ready to listen")

        time.sleep(self.cooldown_after_speech_s)

        self._emit_record_start()

    def _emit_speak(self, text: str, incident_id: Optional[str] = None):
        """Emit speak request to TTS service."""
        self.chem_pub.emit(
            "VOICE.ORCHESTRATOR.SPEAK",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "text": text,
                "affective_state": {},
                "urgency": 0.5,
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

        self.stats["responses_spoken"] += 1
        logger.info(f"[gateway] Emitted speak request: '{text[:50]}...'")

    def _emit_record_start(self, incident_id: Optional[str] = None):
        """Tell audio_io to start recording."""
        self.chem_pub.emit(
            "VOICE.STT.RECORD.START",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

        self.is_listening = True
        logger.debug("[gateway] Emitted record start")

    def _emit_record_stop(self, incident_id: Optional[str] = None):
        """Tell audio_io to stop recording."""
        self.chem_pub.emit(
            "VOICE.STT.RECORD.STOP",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

        self.is_listening = False
        logger.debug("[gateway] Emitted record stop")

    def get_stats(self) -> dict:
        """Get gateway statistics."""
        uptime = time.time() - self.stats["start_time"]
        return {
            **self.stats,
            "uptime_s": uptime,
            "is_speaking": self.is_speaking,
            "is_listening": self.is_listening,
            "meta_agent_connected": self.meta_agent_connected,
        }

    def shutdown(self):
        """Graceful shutdown."""
        logger.info(f"[gateway] Shutting down {self.gateway_name}")
        self.running = False

        final_stats = self.get_stats()
        logger.info(f"[gateway] Final stats: {final_stats}")

        self.chem_pub.emit(
            "VOICE.GATEWAY.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "gateway": self.gateway_name,
                "stats": final_stats,
            }
        )


def main():
    """Main entry point for voice gateway daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    logger.info("[gateway] Starting KLoROS Voice Gateway")

    gateway = VoiceGateway()

    def signal_handler(signum, frame):
        logger.info(f"[gateway] Received signal {signum}, shutting down...")
        gateway.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    gateway.start()

    try:
        while gateway.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[gateway] Interrupted by user")
    finally:
        gateway.shutdown()


if __name__ == "__main__":
    main()
