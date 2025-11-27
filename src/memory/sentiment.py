"""
Sentiment and emotional analysis for KLoROS memory.

Tracks emotional context of conversations using:
- Sentiment polarity (-1.0 to 1.0)
- Emotion classification (joy, sadness, anger, etc.)
- Emotional intensity
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Optional, Tuple

try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    TextBlob = None
    HAS_TEXTBLOB = False

logger = logging.getLogger(__name__)


class EmotionType(str, Enum):
    """Primary emotion types for memory classification."""

    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"
    ANTICIPATION = "anticipation"
    TRUST = "trust"


class SentimentAnalyzer:
    """
    Sentiment and emotion analyzer for memory events.

    Features:
    - Sentiment polarity scoring (-1.0 to 1.0)
    - Subjectivity scoring (0.0 to 1.0)
    - Emotion type classification
    - Intensity detection
    """

    def __init__(self):
        """Initialize the sentiment analyzer."""
        if not HAS_TEXTBLOB:
            raise ImportError(
                "textblob is not installed. "
                "Install it with: pip install textblob"
            )

        # Emotion keywords for classification
        self.emotion_keywords = {
            EmotionType.JOY: [
                "happy", "joy", "excited", "great", "wonderful", "love", "excellent",
                "amazing", "fantastic", "delighted", "pleased", "glad", "cheerful"
            ],
            EmotionType.SADNESS: [
                "sad", "unhappy", "depressed", "down", "disappointed", "miserable",
                "sorry", "unfortunate", "regret", "melancholy", "gloomy"
            ],
            EmotionType.ANGER: [
                "angry", "mad", "furious", "annoyed", "irritated", "frustrated",
                "outraged", "enraged", "livid", "upset", "hostile"
            ],
            EmotionType.FEAR: [
                "afraid", "scared", "fear", "worried", "anxious", "nervous",
                "terrified", "frightened", "panic", "dread", "alarmed"
            ],
            EmotionType.SURPRISE: [
                "surprised", "shocked", "astonished", "amazed", "stunned",
                "unexpected", "startled", "wow", "incredible"
            ],
            EmotionType.DISGUST: [
                "disgusted", "revolted", "repulsed", "gross", "horrible",
                "awful", "terrible", "nasty", "sickening"
            ],
            EmotionType.ANTICIPATION: [
                "hope", "expect", "anticipate", "looking forward", "eager",
                "excited about", "can't wait", "upcoming"
            ],
            EmotionType.TRUST: [
                "trust", "confident", "reliable", "believe", "faith",
                "sure", "certain", "depend on"
            ]
        }

    def analyze(self, text: str) -> Dict[str, any]:
        """
        Analyze sentiment and emotion of text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with sentiment analysis results
        """
        if not text or not text.strip():
            return {
                "sentiment_score": 0.0,
                "subjectivity": 0.0,
                "emotion_type": EmotionType.NEUTRAL.value,
                "intensity": 0.0
            }

        # Use TextBlob for sentiment analysis
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1.0 to 1.0
            subjectivity = blob.sentiment.subjectivity  # 0.0 to 1.0

            # Classify emotion based on keywords and polarity
            emotion = self._classify_emotion(text.lower(), polarity)

            # Calculate intensity (how strong the emotion is)
            intensity = self._calculate_intensity(polarity, subjectivity)

            return {
                "sentiment_score": polarity,
                "subjectivity": subjectivity,
                "emotion_type": emotion.value,
                "intensity": intensity
            }

        except Exception as e:
            logger.error(f"[sentiment] Failed to analyze text: {e}")
            return {
                "sentiment_score": 0.0,
                "subjectivity": 0.0,
                "emotion_type": EmotionType.NEUTRAL.value,
                "intensity": 0.0
            }

    def _classify_emotion(self, text: str, polarity: float) -> EmotionType:
        """
        Classify emotion based on keywords and sentiment polarity.

        Args:
            text: Lowercased text
            polarity: Sentiment polarity score

        Returns:
            Detected emotion type
        """
        # Count keyword matches for each emotion
        emotion_scores = {}

        for emotion, keywords in self.emotion_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                emotion_scores[emotion] = score

        # If keyword matches found, return highest scoring emotion
        if emotion_scores:
            return max(emotion_scores.items(), key=lambda x: x[1])[0]

        # Fallback to polarity-based classification
        if polarity > 0.3:
            return EmotionType.JOY
        elif polarity < -0.3:
            return EmotionType.SADNESS
        elif polarity < -0.5:
            return EmotionType.ANGER
        else:
            return EmotionType.NEUTRAL

    def _calculate_intensity(self, polarity: float, subjectivity: float) -> float:
        """
        Calculate emotional intensity.

        Args:
            polarity: Sentiment polarity
            subjectivity: Subjectivity score

        Returns:
            Intensity score (0.0 to 1.0)
        """
        # Intensity is combination of absolute polarity and subjectivity
        # High intensity = strong polarity + high subjectivity
        polarity_component = abs(polarity)
        intensity = (polarity_component * 0.6) + (subjectivity * 0.4)

        return min(1.0, intensity)

    def analyze_emotional_arc(self, texts: list[str]) -> Dict[str, any]:
        """
        Analyze emotional progression over a sequence of texts.

        Args:
            texts: List of texts in chronological order

        Returns:
            Dictionary with emotional arc analysis
        """
        if not texts:
            return {
                "start_emotion": EmotionType.NEUTRAL.value,
                "end_emotion": EmotionType.NEUTRAL.value,
                "avg_sentiment": 0.0,
                "sentiment_trend": "neutral",
                "emotional_volatility": 0.0
            }

        # Analyze each text
        analyses = [self.analyze(text) for text in texts]

        # Extract sentiment scores
        sentiments = [a["sentiment_score"] for a in analyses]

        # Calculate statistics
        avg_sentiment = sum(sentiments) / len(sentiments)

        # Detect trend
        if len(sentiments) >= 2:
            first_half_avg = sum(sentiments[:len(sentiments)//2]) / (len(sentiments)//2)
            second_half_avg = sum(sentiments[len(sentiments)//2:]) / (len(sentiments) - len(sentiments)//2)

            if second_half_avg > first_half_avg + 0.2:
                trend = "improving"
            elif second_half_avg < first_half_avg - 0.2:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "neutral"

        # Calculate emotional volatility (standard deviation)
        if len(sentiments) > 1:
            variance = sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)
            volatility = variance ** 0.5
        else:
            volatility = 0.0

        return {
            "start_emotion": analyses[0]["emotion_type"],
            "end_emotion": analyses[-1]["emotion_type"],
            "avg_sentiment": avg_sentiment,
            "sentiment_trend": trend,
            "emotional_volatility": volatility,
            "sentiment_history": sentiments
        }


# Global singleton instance
_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> Optional[SentimentAnalyzer]:
    """Get global sentiment analyzer instance or None if textblob is not available."""
    global _analyzer
    if not HAS_TEXTBLOB:
        logger.warning("[sentiment] textblob not installed, sentiment analysis disabled")
        return None
    if _analyzer is None:
        try:
            _analyzer = SentimentAnalyzer()
        except Exception as e:
            logger.error(f"[sentiment] Failed to create sentiment analyzer: {e}")
            return None
    return _analyzer
