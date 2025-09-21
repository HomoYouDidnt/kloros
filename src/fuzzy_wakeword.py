"""Fuzzy wake-word matching using Levenshtein distance and difflib similarity."""

from __future__ import annotations

import difflib
import os
import unicodedata
from typing import List, Tuple


def _ascii_fold(text: str) -> str:
    """Fold unicode text to ASCII, removing accents and diacritics."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def _simple_soundex(text: str) -> str:
    """Simple Soundex implementation (US variant) as fallback."""
    if not text:
        return ""

    text = text.upper()
    # Keep first letter
    soundex = text[0]

    # Convert letters to digits
    mapping = {
        'BFPV': '1',
        'CGJKQSXZ': '2',
        'DT': '3',
        'L': '4',
        'MN': '5',
        'R': '6'
    }

    for char in text[1:]:
        for letters, digit in mapping.items():
            if char in letters:
                # Avoid consecutive duplicates
                if len(soundex) == 1 or soundex[-1] != digit:
                    soundex += digit
                break

    # Pad with zeros or truncate to 4 characters
    soundex = soundex[:4].ljust(4, '0')
    return soundex


def phonetic_similarity(s1: str, s2: str) -> float:
    """Return phonetic similarity (0.0-1.0) using jellyfish or Soundex fallback."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Try jellyfish first (optional dependency)
    try:
        import jellyfish
        # Use metaphone if available, otherwise soundex
        if hasattr(jellyfish, 'metaphone'):
            m1, m2 = jellyfish.metaphone(s1), jellyfish.metaphone(s2)
            if m1 and m2:
                return 1.0 if m1 == m2 else 0.0
        # Fall back to jellyfish soundex
        s1_code, s2_code = jellyfish.soundex(s1), jellyfish.soundex(s2)
    except (ImportError, AttributeError):
        # Use built-in simple soundex
        s1_code, s2_code = _simple_soundex(s1), _simple_soundex(s2)

    if not s1_code or not s2_code:
        return 0.0

    return 1.0 if s1_code == s2_code else 0.0


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Return normalized Levenshtein similarity (0.0-1.0)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Convert to lowercase for case-insensitive comparison
    s1, s2 = s1.lower(), s2.lower()

    # Calculate Levenshtein distance
    len1, len2 = len(s1), len(s2)
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    # Initialize first row and column
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j

    # Fill the matrix
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,      # deletion
                matrix[i][j - 1] + 1,      # insertion
                matrix[i - 1][j - 1] + cost # substitution
            )

    # Convert distance to similarity (0.0-1.0)
    distance = matrix[len1][len2]
    max_len = max(len1, len2)
    similarity = 1.0 - (distance / max_len) if max_len > 0 else 1.0

    # Apply length penalty for very different lengths to reduce false positives
    length_ratio = min(len1, len2) / max(len1, len2) if max(len1, len2) > 0 else 1.0
    if length_ratio < 0.7:  # Significant length difference
        similarity *= length_ratio

    return similarity


def token_similarity(s1: str, s2: str) -> float:
    """Return difflib sequence similarity (0.0-1.0)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Convert to lowercase for case-insensitive comparison
    s1, s2 = s1.lower(), s2.lower()
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def fuzzy_wake_match(
    transcript: str,
    wake_phrases: List[str],
    threshold: float = 0.8,
) -> Tuple[bool, float, str]:
    """Return (is_match, similarity_score, matched_phrase).

    Args:
        transcript: The recognized text to check
        wake_phrases: List of valid wake phrases to match against
        threshold: Minimum similarity score to consider a match (0.0-1.0)

    Returns:
        Tuple of (is_match, best_score, best_phrase)
    """
    if not transcript or not wake_phrases:
        return False, 0.0, ""

    # Parse environment variables
    use_phonetic = int(os.getenv("KLR_USE_PHONETIC", "0"))
    phonetic_weight = max(0.0, min(1.0, float(os.getenv("KLR_PHONETIC_WEIGHT", "0.25"))))
    use_ascii_fold = int(os.getenv("KLR_ASCII_FOLD", "1"))
    denylist_raw = os.getenv("KLR_DENYLIST", "colors,chloros")
    denylist = {s.strip().lower() for s in denylist_raw.split(",") if s.strip()}

    # Clean up transcript
    transcript = transcript.strip().lower()
    if not transcript:
        return False, 0.0, ""

    # Apply ASCII folding if enabled
    if use_ascii_fold:
        transcript = _ascii_fold(transcript)

    best_score = 0.0
    best_phrase = ""

    for phrase in wake_phrases:
        if not phrase:
            continue

        phrase = phrase.strip().lower()
        if not phrase:
            continue

        # Apply ASCII folding to phrase if enabled
        phrase_processed = _ascii_fold(phrase) if use_ascii_fold else phrase

        # Calculate baseline similarities
        lev_score = levenshtein_similarity(transcript, phrase_processed)
        token_score = token_similarity(transcript, phrase_processed)
        base_score = max(lev_score, token_score)

        # Calculate phonetic similarity if enabled
        phonetic_score = 0.0
        if use_phonetic:
            phonetic_score = phonetic_similarity(transcript, phrase_processed)

        # Combine scores
        if use_phonetic and phonetic_weight > 0:
            # Blend phonetic with baseline
            blended_score = (1 - phonetic_weight) * base_score + phonetic_weight * phonetic_score
            # Take the maximum of baseline and blended (never worse than baseline)
            score = max(base_score, blended_score)
        else:
            score = base_score

        # Apply slight boost for very close matches to improve precision
        if score > 0.8:
            score = min(1.0, score * 1.1)

        if score > best_score:
            best_score = score
            best_phrase = phrase  # Return original phrase, not processed

    # Apply denylist clamp - check if transcript is in denylist
    transcript_clean = transcript.lower().strip()
    if transcript_clean in denylist and best_score < threshold + 0.05:
        best_score = 0.0

    is_match = best_score >= threshold
    return is_match, best_score, best_phrase
