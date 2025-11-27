#!/usr/bin/env python3
"""KLoROS Voice Intent Classification Zooid - Command and intent detection.

This zooid handles:
- Command detection (enrollment, identity, system queries)
- Intent classification (command vs. question vs. conversation)
- Skill routing preparation
- Context-aware classification

ChemBus Signals:
- Emits: VOICE.INTENT.CLASSIFIED (intent_type, confidence, command_type, parameters)
- Listens: VOICE.STT.TRANSCRIPTION (classify user utterance)
"""
from __future__ import annotations

import os
import sys
import time
import signal
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.core.umn_bus import UMNPub as ChemPub, UMNSub as ChemSub


class IntentZooid:
    """Intent classification zooid for command detection and routing."""

    def __init__(self):
        self.zooid_name = "kloros-voice-intent"
        self.niche = "voice.intent"

        self.chem_pub = ChemPub()

        self.running = True
        self.enable_intent = int(os.getenv("KLR_ENABLE_INTENT", "1"))

        # Intent classification patterns
        self.command_patterns = {
            "enrollment": [
                r"\benroll\s+me\b",
                r"\badd\s+my\s+voice\b",
                r"\bremember\s+my\s+voice\b",
                r"\blearn\s+my\s+voice\b",
                r"\bcancel\s+enrollment\b",
                r"\blist\s+users\b",
                r"\bwho\s+do\s+you\s+know\b",
                r"\bdelete\s+user\b",
                r"\bremove\s+user\b"
            ],
            "identity": [
                r"\bwhat('?s|\s+is)\s+my\s+name\b",
                r"\bwho\s+am\s+i\b",
                r"\bmy\s+name\s+is\b",
                r"\bdo\s+you\s+know\s+my\s+name\b",
                r"\bremember\s+my\s+name\b"
            ],
            "system_query": [
                r"\bwhat('?s|\s+is)\s+your\s+name\b",
                r"\bwho\s+are\s+you\b",
                r"\bwhat\s+can\s+you\s+do\b",
                r"\bhelp\b",
                r"\bstatus\b",
                r"\bsystem\s+status\b"
            ],
            "exit": [
                r"\bexit\b",
                r"\bquit\b",
                r"\bstop\b",
                r"\bgoodbye\b",
                r"\bbye\b"
            ]
        }

        # Question detection patterns
        self.question_patterns = [
            r"\bwhat\b",
            r"\bwhen\b",
            r"\bwhere\b",
            r"\bwho\b",
            r"\bwhy\b",
            r"\bhow\b",
            r"\bcan\s+you\b",
            r"\bdo\s+you\b",
            r"\bis\s+it\b",
            r"\bshould\s+i\b",
            r"\?$"  # Ends with question mark
        ]

        self.stats = {
            "total_classifications": 0,
            "commands_detected": 0,
            "questions_detected": 0,
            "conversations_detected": 0,
            "classification_times": [],
        }

        print(f"[intent] Initialized: enable={self.enable_intent}")

    def start(self):
        """Start the Intent zooid and subscribe to ChemBus signals."""
        print(f"[intent] Starting {self.zooid_name}")

        if not self.enable_intent:
            print("[intent] Intent classification disabled via KLR_ENABLE_INTENT=0")
            return

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.INTENT.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "command_types": list(self.command_patterns.keys()),
                "patterns_count": sum(len(patterns) for patterns in self.command_patterns.values()),
            }
        )

        print(f"[intent] {self.zooid_name} ready and listening")

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for intent classification."""
        self.transcription_sub = ChemSub(
            "VOICE.STT.TRANSCRIPTION",
            self._on_transcription,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

        print("[intent] Subscribed to ChemBus signals")

    def _on_transcription(self, event: dict):
        """Handle VOICE.STT.TRANSCRIPTION signal and classify intent.

        Args:
            event: ChemBus event with transcription
                - facts.text: Transcribed text
                - facts.confidence: STT confidence
                - incident_id: Event correlation ID
        """
        if not self.running:
            return

        try:
            facts = event.get("facts", {})
            text = facts.get("text", "")
            incident_id = event.get("incident_id")

            if not text:
                print("[intent] ERROR: No text in VOICE.STT.TRANSCRIPTION event")
                return

            start_time = time.time()

            # Classify intent
            intent_type, confidence, command_type, parameters = self._classify_intent(text)

            classification_time = time.time() - start_time
            self.stats["classification_times"].append(classification_time)
            if len(self.stats["classification_times"]) > 100:
                self.stats["classification_times"] = self.stats["classification_times"][-100:]

            self.stats["total_classifications"] += 1
            if intent_type == "command":
                self.stats["commands_detected"] += 1
            elif intent_type == "question":
                self.stats["questions_detected"] += 1
            else:
                self.stats["conversations_detected"] += 1

            self.chem_pub.emit(
                "VOICE.INTENT.CLASSIFIED",
                ecosystem="voice",
                intensity=confidence,
                facts={
                    "text": text,
                    "intent_type": intent_type,
                    "confidence": confidence,
                    "command_type": command_type,
                    "parameters": parameters,
                    "classification_time": classification_time,
                    "timestamp": datetime.now().isoformat(),
                },
                incident_id=incident_id
            )

            print(f"[intent] Classified ({classification_time:.3f}s, conf={confidence:.2f}): {intent_type}/{command_type} - {text[:60]}")

        except Exception as e:
            print(f"[intent] ERROR during classification: {e}")
            print(f"[intent] Traceback: {traceback.format_exc()}")

    def _classify_intent(self, text: str) -> Tuple[str, float, Optional[str], Dict[str, Any]]:
        """Classify intent of user utterance.

        Args:
            text: User utterance to classify

        Returns:
            Tuple of (intent_type, confidence, command_type, parameters)
            - intent_type: "command", "question", or "conversation"
            - confidence: 0.0-1.0 classification confidence
            - command_type: Specific command type if intent_type is "command"
            - parameters: Extracted parameters from the utterance
        """
        text_lower = text.lower().strip()

        # Check for commands first (highest priority)
        for command_type, patterns in self.command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    parameters = self._extract_parameters(text, command_type)
                    return ("command", 0.95, command_type, parameters)

        # Check for questions (medium priority)
        for pattern in self.question_patterns:
            if re.search(pattern, text_lower):
                return ("question", 0.85, None, {})

        # Default to conversation (lowest priority)
        return ("conversation", 0.70, None, {})

    def _extract_parameters(self, text: str, command_type: str) -> Dict[str, Any]:
        """Extract parameters from command text.

        Args:
            text: Command text
            command_type: Type of command

        Returns:
            Dictionary of extracted parameters
        """
        parameters = {}

        if command_type == "identity":
            # Extract name from "my name is X"
            match = re.search(r"my\s+name\s+is\s+(\w+)", text.lower())
            if match:
                parameters["name"] = match.group(1).title()

        elif command_type == "enrollment":
            # Extract user name from enrollment commands
            if "delete user" in text.lower() or "remove user" in text.lower():
                words = text.split()
                for i, word in enumerate(words):
                    if word.lower() == "user":
                        if i + 1 < len(words):
                            parameters["target_user"] = words[i + 1]
                            break

        return parameters

    def get_stats(self) -> dict:
        """Get intent classification statistics.

        Returns:
            Dictionary with classification statistics
        """
        avg_classification_time = (
            sum(self.stats["classification_times"]) / len(self.stats["classification_times"])
            if self.stats["classification_times"] else 0.0
        )

        return {
            **self.stats,
            "average_classification_time": avg_classification_time,
        }

    def shutdown(self):
        """Graceful shutdown of Intent zooid."""
        print(f"[intent] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[intent] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.INTENT.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "stats": final_stats,
            }
        )

        if hasattr(self, 'transcription_sub'):
            self.transcription_sub.close()
        self.chem_pub.close()

        print(f"[intent] {self.zooid_name} shutdown complete")


def main():
    """Main entry point for Intent zooid daemon."""
    print("[intent] Starting KLoROS Voice Intent Classification Zooid")

    zooid = IntentZooid()

    def signal_handler(signum, frame):
        print(f"[intent] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[intent] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
