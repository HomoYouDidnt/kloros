#!/usr/bin/env python3
"""KLoROS Voice Emotion Analysis Zooid - Sentiment and affective state detection.

This zooid handles:
- Sentiment analysis (positive/negative/neutral)
- Affective state modeling (valence, arousal, dominance)
- Emotional shift detection
- Emotional memory tracking

ChemBus Signals:
- Emits: VOICE.EMOTION.STATE (valence, arousal, dominance, sentiment, confidence)
- Emits: VOICE.EMOTION.SHIFT.DETECTED (previous_state, new_state, trigger)
- Listens: VOICE.STT.TRANSCRIPTION (analyze user sentiment)
"""
from __future__ import annotations

import os
import sys
import time
import signal
import traceback
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub


class EmotionZooid:
    """Emotion analysis zooid for sentiment and affective state detection."""

    def __init__(self):
        self.zooid_name = "kloros-voice-emotion"
        self.niche = "voice.emotion"

        self.chem_pub = ChemPub()

        self.running = True
        self.enable_emotion = int(os.getenv("KLR_ENABLE_EMOTION", "1"))

        # Sentiment lexicons (simple rule-based)
        self.positive_words = {
            "good", "great", "excellent", "wonderful", "amazing", "fantastic", "love",
            "happy", "joy", "pleased", "delighted", "awesome", "brilliant", "perfect",
            "best", "beautiful", "nice", "glad", "thanks", "thank"
        }

        self.negative_words = {
            "bad", "terrible", "awful", "horrible", "hate", "angry", "sad", "upset",
            "annoyed", "frustrated", "disappointed", "worst", "useless", "broken",
            "wrong", "error", "fail", "problem", "issue", "sorry"
        }

        self.intensifiers = {
            "very", "really", "extremely", "incredibly", "absolutely", "totally",
            "completely", "utterly", "so", "quite"
        }

        # Emotional state tracking
        self.current_state = {
            "valence": 0.0,  # -1 (negative) to +1 (positive)
            "arousal": 0.0,  # -1 (calm) to +1 (excited)
            "dominance": 0.0,  # -1 (submissive) to +1 (dominant)
        }

        self.previous_state = self.current_state.copy()
        self.emotional_history = []  # Last 10 states for shift detection

        self.stats = {
            "total_analyses": 0,
            "positive_detections": 0,
            "negative_detections": 0,
            "neutral_detections": 0,
            "emotion_shifts_detected": 0,
            "analysis_times": [],
        }

        print(f"[emotion] Initialized: enable={self.enable_emotion}")

    def start(self):
        """Start the Emotion zooid and subscribe to ChemBus signals."""
        print(f"[emotion] Starting {self.zooid_name}")

        if not self.enable_emotion:
            print("[emotion] Emotion analysis disabled via KLR_ENABLE_EMOTION=0")
            return

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.EMOTION.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "method": "rule-based",
                "current_state": self.current_state,
            }
        )

        print(f"[emotion] {self.zooid_name} ready and listening")

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for emotion analysis."""
        self.transcription_sub = ChemSub(
            "VOICE.STT.TRANSCRIPTION",
            self._on_transcription,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

        print("[emotion] Subscribed to ChemBus signals")

    def _on_transcription(self, event: dict):
        """Handle VOICE.STT.TRANSCRIPTION signal and analyze emotion.

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
                print("[emotion] ERROR: No text in VOICE.STT.TRANSCRIPTION event")
                return

            start_time = time.time()

            # Analyze sentiment and affective state
            sentiment, valence, arousal, dominance, confidence = self._analyze_emotion(text)

            analysis_time = time.time() - start_time
            self.stats["analysis_times"].append(analysis_time)
            if len(self.stats["analysis_times"]) > 100:
                self.stats["analysis_times"] = self.stats["analysis_times"][-100:]

            self.stats["total_analyses"] += 1
            if sentiment == "positive":
                self.stats["positive_detections"] += 1
            elif sentiment == "negative":
                self.stats["negative_detections"] += 1
            else:
                self.stats["neutral_detections"] += 1

            # Check for emotional shift
            shift_detected = self._detect_emotion_shift(valence, arousal, dominance)

            self.chem_pub.emit(
                "VOICE.EMOTION.STATE",
                ecosystem="voice",
                intensity=confidence,
                facts={
                    "text": text,
                    "sentiment": sentiment,
                    "valence": valence,
                    "arousal": arousal,
                    "dominance": dominance,
                    "confidence": confidence,
                    "analysis_time": analysis_time,
                    "timestamp": datetime.now().isoformat(),
                },
                incident_id=incident_id
            )

            if shift_detected:
                self.chem_pub.emit(
                    "VOICE.EMOTION.SHIFT.DETECTED",
                    ecosystem="voice",
                    intensity=0.8,
                    facts={
                        "previous_state": self.previous_state,
                        "new_state": self.current_state,
                        "trigger": text[:100],
                        "timestamp": datetime.now().isoformat(),
                    },
                    incident_id=incident_id
                )

                self.stats["emotion_shifts_detected"] += 1
                print(f"[emotion] Shift detected: {self.previous_state['valence']:.2f} → {valence:.2f}")

            print(f"[emotion] Analyzed ({analysis_time:.3f}s): {sentiment} (v={valence:.2f}, a={arousal:.2f}) - {text[:60]}")

        except Exception as e:
            print(f"[emotion] ERROR during analysis: {e}")
            print(f"[emotion] Traceback: {traceback.format_exc()}")

    def _analyze_emotion(self, text: str) -> Tuple[str, float, float, float, float]:
        """Analyze emotion and affective state of text.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (sentiment, valence, arousal, dominance, confidence)
        """
        words = re.findall(r'\w+', text.lower())

        # Count sentiment words
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)

        # Check for intensifiers (boost sentiment)
        intensifier_count = sum(1 for word in words if word in self.intensifiers)
        intensity_boost = min(0.2 * intensifier_count, 0.4)  # Max 0.4 boost

        # Determine overall sentiment
        if positive_count > negative_count:
            sentiment = "positive"
            valence = min(0.3 + (positive_count * 0.2) + intensity_boost, 1.0)
            arousal = min(0.2 + (positive_count * 0.15), 0.8)
            confidence = min(0.6 + (positive_count * 0.1), 0.95)
        elif negative_count > positive_count:
            sentiment = "negative"
            valence = max(-0.3 - (negative_count * 0.2) - intensity_boost, -1.0)
            arousal = min(0.2 + (negative_count * 0.15), 0.8)
            confidence = min(0.6 + (negative_count * 0.1), 0.95)
        else:
            sentiment = "neutral"
            valence = 0.0
            arousal = 0.0
            confidence = 0.5

        # Dominance based on question vs. statement structure
        is_question = "?" in text or any(
            text.lower().startswith(word) for word in ["what", "when", "where", "who", "why", "how", "can", "do"]
        )
        dominance = -0.2 if is_question else 0.1

        return sentiment, valence, arousal, dominance, confidence

    def _detect_emotion_shift(self, valence: float, arousal: float, dominance: float) -> bool:
        """Detect if there's a significant emotional shift.

        Args:
            valence: New valence value
            arousal: New arousal value
            dominance: New dominance value

        Returns:
            True if significant shift detected
        """
        # Update emotional history
        new_state = {
            "valence": valence,
            "arousal": arousal,
            "dominance": dominance,
        }

        self.emotional_history.append(new_state)
        if len(self.emotional_history) > 10:
            self.emotional_history.pop(0)

        # Check for shift (valence change > 0.5)
        valence_delta = abs(valence - self.current_state["valence"])
        shift_detected = valence_delta > 0.5

        if shift_detected:
            self.previous_state = self.current_state.copy()

        # Update current state
        self.current_state = new_state

        return shift_detected

    def get_stats(self) -> dict:
        """Get emotion analysis statistics.

        Returns:
            Dictionary with analysis statistics
        """
        avg_analysis_time = (
            sum(self.stats["analysis_times"]) / len(self.stats["analysis_times"])
            if self.stats["analysis_times"] else 0.0
        )

        return {
            **self.stats,
            "average_analysis_time": avg_analysis_time,
            "current_state": self.current_state,
        }

    def shutdown(self):
        """Graceful shutdown of Emotion zooid."""
        print(f"[emotion] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[emotion] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.EMOTION.SHUTDOWN",
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

        print(f"[emotion] {self.zooid_name} shutdown complete")


def main():
    """Main entry point for Emotion zooid daemon."""
    print("[emotion] Starting KLoROS Voice Emotion Analysis Zooid")

    zooid = EmotionZooid()

    def signal_handler(signum, frame):
        print(f"[emotion] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[emotion] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
