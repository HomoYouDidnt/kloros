"""Text complexity analyzer for intelligent TTS routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class TextAnalysis:
    """Result of text complexity analysis."""

    needs_normalization: bool
    complexity_score: float
    features: List[str]


class TextComplexityAnalyzer:
    """Analyzes text to determine if it needs normalization.

    Routes to Supertonic when text contains elements that require
    normalization (numbers, dates, abbreviations, etc.), otherwise
    routes to Piper for clean prose.
    """

    CURRENCY_PATTERN = re.compile(r'[$€£¥]\s*[\d,.]+[KMBkmb]?|\d+\s*(?:dollars?|euros?|pounds?|cents?)', re.I)
    NUMBER_PATTERN = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b')
    PERCENTAGE_PATTERN = re.compile(r'\d+(?:\.\d+)?%')
    DATE_PATTERN = re.compile(
        r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b|'
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b',
        re.I
    )
    TIME_PATTERN = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b')
    PHONE_PATTERN = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
    ABBREVIATION_PATTERN = re.compile(r'\b(?:Dr|Mr|Mrs|Ms|Prof|Jr|Sr|Inc|Ltd|Corp|Co|St|Ave|Blvd|vs|etc|e\.g|i\.e)\.')
    TECHNICAL_UNIT_PATTERN = re.compile(r'\b\d+(?:\.\d+)?\s*(?:kg|lb|oz|km|mi|m|ft|cm|mm|°[CF]|mph|kph|GB|MB|KB|TB|Hz|kHz|MHz|GHz|ms|ns|μs)\b', re.I)
    URL_EMAIL_PATTERN = re.compile(r'https?://\S+|www\.\S+|\S+@\S+\.\S+')
    ORDINAL_PATTERN = re.compile(r'\b\d+(?:st|nd|rd|th)\b', re.I)
    FRACTION_PATTERN = re.compile(r'\b\d+/\d+\b')
    ALPHANUMERIC_PATTERN = re.compile(r'\b[A-Z]{2,}\d+|\d+[A-Z]{2,}\b')

    PATTERNS = [
        ("currency", CURRENCY_PATTERN, 0.3),
        ("number", NUMBER_PATTERN, 0.15),
        ("percentage", PERCENTAGE_PATTERN, 0.2),
        ("date", DATE_PATTERN, 0.25),
        ("time", TIME_PATTERN, 0.2),
        ("phone", PHONE_PATTERN, 0.25),
        ("abbreviation", ABBREVIATION_PATTERN, 0.15),
        ("technical_unit", TECHNICAL_UNIT_PATTERN, 0.2),
        ("url_email", URL_EMAIL_PATTERN, 0.3),
        ("ordinal", ORDINAL_PATTERN, 0.1),
        ("fraction", FRACTION_PATTERN, 0.15),
        ("alphanumeric", ALPHANUMERIC_PATTERN, 0.2),
    ]

    NORMALIZATION_THRESHOLD = 0.2

    def analyze(self, text: str) -> TextAnalysis:
        """Analyze text for normalization complexity.

        Args:
            text: Input text to analyze

        Returns:
            TextAnalysis with normalization need, score, and detected features
        """
        features = []
        score = 0.0

        for name, pattern, weight in self.PATTERNS:
            matches = pattern.findall(text)
            if matches:
                features.append(name)
                match_count = len(matches)
                text_length = max(len(text), 1)
                density = min(match_count * 10 / text_length, 1.0)
                score += weight * (0.5 + 0.5 * density)

        score = min(score, 1.0)
        needs_normalization = score >= self.NORMALIZATION_THRESHOLD

        return TextAnalysis(
            needs_normalization=needs_normalization,
            complexity_score=score,
            features=features,
        )

    def should_use_supertonic(self, text: str) -> bool:
        """Quick check if Supertonic should be used.

        Args:
            text: Input text

        Returns:
            True if Supertonic recommended, False for Piper
        """
        return self.analyze(text).needs_normalization
