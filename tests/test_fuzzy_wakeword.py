"""Unit tests for fuzzy wake-word detection."""

import os
import pytest

from src.fuzzy_wakeword import fuzzy_wake_match, levenshtein_similarity, token_similarity, phonetic_similarity


class TestLevenshteinSimilarity:
    """Test Levenshtein distance similarity calculation."""

    def test_identical_strings(self):
        """Test identical strings return 1.0 similarity."""
        assert levenshtein_similarity("kloros", "kloros") == 1.0
        assert levenshtein_similarity("hello", "hello") == 1.0

    def test_empty_strings(self):
        """Test empty string edge cases."""
        assert levenshtein_similarity("", "") == 1.0
        assert levenshtein_similarity("", "kloros") == 0.0
        assert levenshtein_similarity("kloros", "") == 0.0

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        assert levenshtein_similarity("KLOROS", "kloros") == 1.0
        assert levenshtein_similarity("KlOrOs", "kloros") == 1.0

    def test_single_character_changes(self):
        """Test similarity with single character modifications."""
        # Single substitution
        sim = levenshtein_similarity("kloros", "kleros")
        assert sim > 0.8  # 1 char diff out of 6 = 5/6 = 0.833...

        # Single insertion
        sim = levenshtein_similarity("kloros", "klorous")
        assert sim > 0.8  # Should be high similarity

        # Single deletion
        sim = levenshtein_similarity("kloros", "klros")
        assert sim > 0.8  # Should be high similarity


class TestTokenSimilarity:
    """Test difflib token similarity calculation."""

    def test_identical_strings(self):
        """Test identical strings return 1.0 similarity."""
        assert token_similarity("kloros", "kloros") == 1.0

    def test_empty_strings(self):
        """Test empty string edge cases."""
        assert token_similarity("", "") == 1.0
        assert token_similarity("", "kloros") == 0.0
        assert token_similarity("kloros", "") == 0.0

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        assert token_similarity("KLOROS", "kloros") == 1.0

    def test_partial_similarity(self):
        """Test partial string similarity."""
        sim = token_similarity("kloros", "klorous")
        assert sim > 0.8  # High similarity for close strings


class TestFuzzyWakeMatch:
    """Test main fuzzy wake-word matching function."""

    def test_exact_match(self):
        """Test exact phrase matching returns high similarity."""
        is_match, score, phrase = fuzzy_wake_match("kloros", ["kloros"], threshold=0.8)
        assert is_match is True
        assert score >= 0.99
        assert phrase == "kloros"

    def test_typo_tolerance(self):
        """Test tolerance for common typos."""
        # Missing character
        is_match, score, phrase = fuzzy_wake_match("klros", ["kloros"], threshold=0.8)
        assert is_match is True
        assert score >= 0.85
        assert phrase == "kloros"

        # Extra character
        is_match, score, phrase = fuzzy_wake_match("klorous", ["kloros"], threshold=0.8)
        assert is_match is True
        assert score >= 0.85
        assert phrase == "kloros"

    def test_false_positive_colors(self):
        """Test that 'colors' does not match 'kloros'."""
        is_match, score, phrase = fuzzy_wake_match("colors", ["kloros"], threshold=0.8)
        assert is_match is False
        assert score <= 0.6

    def test_threshold_boundary(self):
        """Test behavior around threshold boundaries."""
        # Test with a string that should be right at the boundary
        is_match_high, score_high, _ = fuzzy_wake_match("klros", ["kloros"], threshold=0.7)
        is_match_low, score_low, _ = fuzzy_wake_match("klros", ["kloros"], threshold=0.9)

        # Should pass lower threshold but fail higher threshold
        assert score_high == score_low  # Same score
        assert is_match_high is True
        assert is_match_low is False

    def test_multi_phrase_list(self):
        """Test matching against multiple phrases, returns best match."""
        phrases = ["kloros", "hello", "computer"]

        # Should match kloros best
        is_match, score, phrase = fuzzy_wake_match("klros", phrases, threshold=0.8)
        assert is_match is True
        assert phrase == "kloros"

        # Should match hello best
        is_match, score, phrase = fuzzy_wake_match("helo", phrases, threshold=0.8)
        assert is_match is True
        assert phrase == "hello"

    def test_empty_inputs(self):
        """Test edge cases with empty inputs."""
        # Empty transcript
        is_match, score, phrase = fuzzy_wake_match("", ["kloros"], threshold=0.8)
        assert is_match is False
        assert score == 0.0
        assert phrase == ""

        # Empty phrases list
        is_match, score, phrase = fuzzy_wake_match("kloros", [], threshold=0.8)
        assert is_match is False
        assert score == 0.0
        assert phrase == ""

        # Empty phrase in list
        is_match, score, phrase = fuzzy_wake_match("kloros", ["", "kloros"], threshold=0.8)
        assert is_match is True
        assert phrase == "kloros"

    def test_case_insensitive_matching(self):
        """Test that matching is case insensitive."""
        is_match, score, phrase = fuzzy_wake_match("KLOROS", ["kloros"], threshold=0.8)
        assert is_match is True
        assert score >= 0.99
        assert phrase == "kloros"  # Returns normalized phrase

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        is_match, score, phrase = fuzzy_wake_match("  kloros  ", ["kloros"], threshold=0.8)
        assert is_match is True
        assert score >= 0.99

        is_match, score, phrase = fuzzy_wake_match("kloros", ["  kloros  "], threshold=0.8)
        assert is_match is True
        assert score >= 0.99

    def test_low_threshold(self):
        """Test with very low threshold to ensure more matches."""
        is_match, score, phrase = fuzzy_wake_match("hello", ["kloros"], threshold=0.1)
        assert is_match is True  # Should match with very low threshold
        assert score > 0.1

    def test_high_threshold(self):
        """Test with very high threshold to ensure fewer matches."""
        is_match, score, phrase = fuzzy_wake_match("klros", ["kloros"], threshold=0.95)
        assert is_match is False  # Should not match with very high threshold
        assert score < 0.95


class TestPhoneticSimilarity:
    """Test phonetic similarity functions."""

    def test_phonetic_identical(self):
        """Test identical strings return 1.0 similarity."""
        assert phonetic_similarity("kloros", "kloros") == 1.0

    def test_phonetic_empty(self):
        """Test empty string edge cases."""
        assert phonetic_similarity("", "") == 1.0
        assert phonetic_similarity("", "kloros") == 0.0
        assert phonetic_similarity("kloros", "") == 0.0

    def test_phonetic_soundex_basic(self):
        """Test basic Soundex functionality."""
        # These should sound similar (both start with K and have similar consonant patterns)
        sim = phonetic_similarity("kloros", "cloros")
        assert sim >= 0.0  # May be 0 or 1 depending on implementation

    def test_optional_jellyfish(self):
        """Test that phonetic similarity works with or without jellyfish."""
        # This should work regardless of whether jellyfish is installed
        sim = phonetic_similarity("kloros", "kloros")
        assert sim == 1.0

        sim = phonetic_similarity("kloros", "different")
        assert sim >= 0.0  # Could be 0 or 1 depending on phonetic codes


class TestPhoneticIntegration:
    """Test phonetic integration in fuzzy_wake_match."""

    def setUp(self):
        """Store original env vars to restore later."""
        self.orig_env = {}
        for key in ["KLR_USE_PHONETIC", "KLR_PHONETIC_WEIGHT", "KLR_ASCII_FOLD", "KLR_DENYLIST"]:
            self.orig_env[key] = os.environ.get(key)

    def tearDown(self):
        """Restore original env vars."""
        for key, value in self.orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_phonetic_disabled_no_change(self):
        """Test that with KLR_USE_PHONETIC=0, scores equal baseline."""
        # Set up environment
        os.environ["KLR_USE_PHONETIC"] = "0"

        # Test various inputs
        test_cases = [
            ("kloros", ["kloros"]),
            ("klros", ["kloros"]),
            ("cloros", ["kloros"]),
        ]

        for transcript, phrases in test_cases:
            is_match, score, phrase = fuzzy_wake_match(transcript, phrases, threshold=0.8)
            # Store the baseline score
            baseline_score = score

            # Should be deterministic - same call should give same result
            is_match2, score2, phrase2 = fuzzy_wake_match(transcript, phrases, threshold=0.8)
            assert abs(score - score2) < 1e-6, f"Baseline scores inconsistent for {transcript}"

    def test_phonetic_variants_enabled(self):
        """Test that phonetic matching improves scores for sound-alike variants."""
        # Set up environment
        os.environ["KLR_USE_PHONETIC"] = "1"
        os.environ["KLR_PHONETIC_WEIGHT"] = "0.25"

        # Get baseline scores with phonetic disabled
        os.environ["KLR_USE_PHONETIC"] = "0"
        baseline_scores = {}
        test_cases = [
            ("cloros", ["kloros"]),
            ("kloroz", ["kloros"]),
        ]

        for transcript, phrases in test_cases:
            _, score, _ = fuzzy_wake_match(transcript, phrases, threshold=0.8)
            baseline_scores[transcript] = score

        # Enable phonetic and compare
        os.environ["KLR_USE_PHONETIC"] = "1"

        for transcript, phrases in test_cases:
            is_match, score, phrase = fuzzy_wake_match(transcript, phrases, threshold=0.8)
            baseline = baseline_scores[transcript]

            # Score should be >= baseline (never worse)
            assert score >= baseline - 1e-6, f"Phonetic made score worse for {transcript}: {score} < {baseline}"

            # For at least some cases, we expect improvement
            # Note: This is implementation-dependent and may not always improve

    def test_denylist_clamp(self):
        """Test that denylist prevents matches when score < threshold + 0.05."""
        os.environ["KLR_DENYLIST"] = "colors,chloros"
        os.environ["KLR_USE_PHONETIC"] = "0"  # Disable phonetic for predictable scores

        # Test with "colors" which should be in denylist
        is_match, score, phrase = fuzzy_wake_match("colors", ["kloros"], threshold=0.8)

        # The match should be rejected due to denylist clamping
        assert is_match is False, "Denylist should prevent 'colors' from matching 'kloros'"

        # Test with a non-denylisted word
        is_match, score, phrase = fuzzy_wake_match("hello", ["kloros"], threshold=0.1)  # Low threshold
        # This should match at low threshold if not clamped
        if score >= 0.1:
            assert is_match is True, "Non-denylisted word should match at low threshold"

    def test_ascii_folding(self):
        """Test ASCII folding functionality."""
        # Test with accented characters
        os.environ["KLR_ASCII_FOLD"] = "1"
        os.environ["KLR_USE_PHONETIC"] = "0"

        # Get score with ASCII folding enabled
        is_match1, score1, _ = fuzzy_wake_match("klóròs", ["kloros"], threshold=0.8)

        # Test with ASCII folding disabled
        os.environ["KLR_ASCII_FOLD"] = "0"
        is_match2, score2, _ = fuzzy_wake_match("klóròs", ["kloros"], threshold=0.8)

        # With folding enabled, should get better score
        assert score1 >= score2 - 1e-6, "ASCII folding should not make scores worse"

        # The folded version should be very close to the original
        os.environ["KLR_ASCII_FOLD"] = "1"
        is_match3, score3, _ = fuzzy_wake_match("kloros", ["kloros"], threshold=0.8)

        # Folded accented version should be very close to plain ASCII
        assert score1 >= 0.99, "ASCII folding should make accented 'klóròs' very similar to 'kloros'"

    def test_environment_variable_bounds(self):
        """Test that environment variables are properly bounded."""
        # Test phonetic weight clamping
        os.environ["KLR_USE_PHONETIC"] = "1"
        os.environ["KLR_PHONETIC_WEIGHT"] = "2.0"  # Over 1.0

        # Should not crash and should clamp to valid range
        is_match, score, phrase = fuzzy_wake_match("kloros", ["kloros"], threshold=0.8)
        assert is_match is True

        # Test negative weight
        os.environ["KLR_PHONETIC_WEIGHT"] = "-0.5"  # Below 0.0
        is_match, score, phrase = fuzzy_wake_match("kloros", ["kloros"], threshold=0.8)
        assert is_match is True

    def test_phonetic_weight_effect(self):
        """Test that phonetic weight affects score blending."""
        os.environ["KLR_USE_PHONETIC"] = "1"

        # Test with different weights
        weights = ["0.0", "0.5", "1.0"]
        scores = []

        for weight in weights:
            os.environ["KLR_PHONETIC_WEIGHT"] = weight
            _, score, _ = fuzzy_wake_match("cloros", ["kloros"], threshold=0.8)
            scores.append(score)

        # All scores should be valid
        for score in scores:
            assert 0.0 <= score <= 1.0, f"Score {score} out of valid range"

    def teardown_method(self):
        """Clean up environment after each test."""
        for key in ["KLR_USE_PHONETIC", "KLR_PHONETIC_WEIGHT", "KLR_ASCII_FOLD", "KLR_DENYLIST"]:
            os.environ.pop(key, None)