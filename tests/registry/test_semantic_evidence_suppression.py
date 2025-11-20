"""
Tests for suppression tracking functionality in semantic_evidence.py

Tests the defense-in-depth suppression mechanism to prevent investigation loops.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import time

from src.registry.semantic_evidence import SemanticEvidenceStore


@pytest.fixture
def temp_evidence_file():
    """Create a temporary evidence file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        temp_path = f.name
    yield Path(temp_path)
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def store(temp_evidence_file):
    """Create a fresh SemanticEvidenceStore for testing."""
    return SemanticEvidenceStore(evidence_path=temp_evidence_file)


class TestSuppressionDataStructure:
    """Test the suppression data structure is properly initialized."""

    def test_new_capability_has_no_suppression_by_default(self, store):
        """New capabilities should not have suppression data."""
        store.record_failure("test_cap", reason="Test failure")
        assert "suppression" in store.evidence["test_cap"]
        assert store.evidence["test_cap"]["suppression"]["suppressed"] is False

    def test_suppression_structure_has_required_fields(self, store):
        """Suppression data should have all required fields."""
        store.record_failure("test_cap", reason="Test failure")
        suppression = store.evidence["test_cap"]["suppression"]

        assert "suppressed" in suppression
        assert "reason" in suppression
        assert "first_attempt" in suppression
        assert "last_attempt" in suppression
        assert "failure_count" in suppression
        assert "suppress_until" in suppression
        assert "user_can_override" in suppression

    def test_suppression_timestamp_format(self, store):
        """Suppression timestamps should be ISO format."""
        store.record_failure("test_cap", reason="Test")
        suppression = store.evidence["test_cap"]["suppression"]

        first = datetime.fromisoformat(suppression["first_attempt"])
        last = datetime.fromisoformat(suppression["last_attempt"])

        assert first <= last


class TestRecordFailure:
    """Test the record_failure method."""

    def test_record_failure_increments_count(self, store):
        """Each failure should increment the counter."""
        cap_key = "test_capability"

        store.record_failure(cap_key, reason="Failure 1")
        assert store.evidence[cap_key]["suppression"]["failure_count"] == 1

        store.record_failure(cap_key, reason="Failure 2")
        assert store.evidence[cap_key]["suppression"]["failure_count"] == 2

        store.record_failure(cap_key, reason="Failure 3")
        assert store.evidence[cap_key]["suppression"]["failure_count"] == 3

    def test_record_failure_updates_last_attempt(self, store):
        """Each failure should update last_attempt timestamp."""
        cap_key = "test_capability"

        store.record_failure(cap_key, reason="First")
        first_time = store.evidence[cap_key]["suppression"]["last_attempt"]

        time.sleep(0.01)
        store.record_failure(cap_key, reason="Second")
        second_time = store.evidence[cap_key]["suppression"]["last_attempt"]

        assert first_time < second_time

    def test_record_failure_preserves_first_attempt(self, store):
        """First attempt timestamp should never change."""
        cap_key = "test_capability"

        store.record_failure(cap_key, reason="First")
        first_attempt = store.evidence[cap_key]["suppression"]["first_attempt"]

        time.sleep(0.01)
        store.record_failure(cap_key, reason="Second")

        assert store.evidence[cap_key]["suppression"]["first_attempt"] == first_attempt

    def test_record_failure_stores_reason(self, store):
        """Failure reason should be stored."""
        cap_key = "test_capability"
        reason_text = "Custom failure reason"

        store.record_failure(cap_key, reason=reason_text)
        assert store.evidence[cap_key]["suppression"]["reason"] == reason_text

    def test_record_failure_creates_new_entry_if_missing(self, store):
        """record_failure should initialize entry if capability doesn't exist."""
        cap_key = "new_capability"
        assert cap_key not in store.evidence

        store.record_failure(cap_key, reason="Test")

        assert cap_key in store.evidence
        assert "suppression" in store.evidence[cap_key]


class TestAutoSuppression:
    """Test automatic suppression at 5 failures."""

    def test_auto_suppresses_at_5_failures(self, store):
        """Capability should auto-suppress after 5 failures."""
        cap_key = "test_capability"

        for i in range(4):
            store.record_failure(cap_key, reason=f"Failure {i+1}")
            assert store.evidence[cap_key]["suppression"]["suppressed"] is False

        store.record_failure(cap_key, reason="Failure 5")
        assert store.evidence[cap_key]["suppression"]["suppressed"] is True

    def test_auto_suppression_reason_format(self, store):
        """Auto-suppression reason should include failure count."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        suppression = store.evidence[cap_key]["suppression"]
        reason = suppression["reason"]

        assert "Repeated investigation failures" in reason
        assert "5" in reason

    def test_continues_tracking_after_auto_suppression(self, store):
        """Failure count should continue incrementing after auto-suppression."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        assert store.evidence[cap_key]["suppression"]["failure_count"] == 5

        store.record_failure(cap_key, reason="Failure 6")
        assert store.evidence[cap_key]["suppression"]["failure_count"] == 6
        assert store.evidence[cap_key]["suppression"]["suppressed"] is True


class TestIsSuppressed:
    """Test the is_suppressed method."""

    def test_returns_false_for_unsuppressed_capability(self, store):
        """is_suppressed should return False for unsuppressed capabilities."""
        cap_key = "test_capability"
        store.record_failure(cap_key, reason="Test")

        assert store.is_suppressed(cap_key) is False

    def test_returns_true_for_suppressed_capability(self, store):
        """is_suppressed should return True for suppressed capabilities."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        assert store.is_suppressed(cap_key) is True

    def test_returns_false_for_nonexistent_capability(self, store):
        """is_suppressed should conservatively return False for missing capabilities."""
        assert store.is_suppressed("nonexistent_capability") is False

    def test_respects_manual_suppression(self, store):
        """is_suppressed should return True for manually suppressed capabilities."""
        cap_key = "test_capability"
        store.suppress(cap_key, reason="Manual suppression")

        assert store.is_suppressed(cap_key) is True


class TestSuppressUnsuppress:
    """Test manual suppression control."""

    def test_suppress_sets_suppressed_flag(self, store):
        """suppress should set suppressed=True."""
        cap_key = "test_capability"

        store.suppress(cap_key, reason="Admin command")

        assert store.evidence[cap_key]["suppression"]["suppressed"] is True

    def test_suppress_sets_reason(self, store):
        """suppress should set the reason."""
        cap_key = "test_capability"
        reason = "Service intentionally disabled"

        store.suppress(cap_key, reason=reason)

        assert store.evidence[cap_key]["suppression"]["reason"] == reason

    def test_suppress_initializes_if_missing(self, store):
        """suppress should initialize suppression if it doesn't exist."""
        cap_key = "test_capability"

        store.suppress(cap_key, reason="Manual")

        assert "suppression" in store.evidence[cap_key]
        assert store.evidence[cap_key]["suppression"]["suppressed"] is True

    def test_unsuppress_clears_suppression_flag(self, store):
        """unsuppress should set suppressed=False."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        assert store.is_suppressed(cap_key) is True

        store.unsuppress(cap_key)

        assert store.evidence[cap_key]["suppression"]["suppressed"] is False

    def test_unsuppress_preserves_history(self, store):
        """unsuppress should preserve failure history."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        original_count = store.evidence[cap_key]["suppression"]["failure_count"]
        original_first = store.evidence[cap_key]["suppression"]["first_attempt"]

        store.unsuppress(cap_key)

        assert store.evidence[cap_key]["suppression"]["failure_count"] == original_count
        assert store.evidence[cap_key]["suppression"]["first_attempt"] == original_first

    def test_unsuppress_nonexistent_capability_is_safe(self, store):
        """unsuppress on nonexistent capability should not raise."""
        store.unsuppress("nonexistent_capability")


class TestGetSuppressionInfo:
    """Test the get_suppression_info method."""

    def test_returns_suppression_metadata(self, store):
        """get_suppression_info should return all suppression fields."""
        cap_key = "test_capability"
        store.record_failure(cap_key, reason="Test failure")

        info = store.get_suppression_info(cap_key)

        assert "suppressed" in info
        assert "reason" in info
        assert "first_attempt" in info
        assert "last_attempt" in info
        assert "failure_count" in info
        assert "suppress_until" in info
        assert "user_can_override" in info

    def test_returns_empty_dict_for_nonexistent_capability(self, store):
        """get_suppression_info should return empty dict for missing capabilities."""
        info = store.get_suppression_info("nonexistent_capability")
        assert info == {}

    def test_info_reflects_current_state(self, store):
        """get_suppression_info should reflect current suppression state."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        info = store.get_suppression_info(cap_key)

        assert info["suppressed"] is True
        assert info["failure_count"] == 5
        assert "Repeated investigation failures" in info["reason"]

    def test_info_for_manually_suppressed_capability(self, store):
        """get_suppression_info should reflect manual suppression."""
        cap_key = "test_capability"
        reason = "Service intentionally disabled by admin"

        store.suppress(cap_key, reason=reason)

        info = store.get_suppression_info(cap_key)

        assert info["suppressed"] is True
        assert info["reason"] == reason


class TestPersistence:
    """Test loading and saving suppression data."""

    def test_saves_suppression_data(self, store, temp_evidence_file):
        """Suppression data should be persisted to disk."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        with open(temp_evidence_file, 'r') as f:
            saved_data = json.load(f)

        assert cap_key in saved_data
        assert "suppression" in saved_data[cap_key]
        assert saved_data[cap_key]["suppression"]["suppressed"] is True

    def test_loads_existing_suppression_data(self, temp_evidence_file):
        """Loading should restore suppression data from disk."""
        original_data = {
            "test_cap": {
                "purpose": "Test capability",
                "integrates_with": [],
                "provides_capabilities": [],
                "used_by": [],
                "key_abstractions": [],
                "discovered_at": datetime.now().isoformat(),
                "suppression": {
                    "suppressed": True,
                    "reason": "Test suppression",
                    "first_attempt": datetime.now().isoformat(),
                    "last_attempt": datetime.now().isoformat(),
                    "failure_count": 5,
                    "suppress_until": None,
                    "user_can_override": True
                }
            }
        }

        with open(temp_evidence_file, 'w') as f:
            json.dump(original_data, f)

        store = SemanticEvidenceStore(evidence_path=temp_evidence_file)

        assert "test_cap" in store.evidence
        assert store.is_suppressed("test_cap") is True
        assert store.evidence["test_cap"]["suppression"]["reason"] == "Test suppression"

    def test_backward_compatibility_with_old_entries(self, temp_evidence_file):
        """Should handle old entries without suppression metadata."""
        old_data = {
            "old_capability": {
                "purpose": "Old capability",
                "integrates_with": [],
                "provides_capabilities": [],
                "used_by": [],
                "key_abstractions": [],
                "discovered_at": datetime.now().isoformat()
            }
        }

        with open(temp_evidence_file, 'w') as f:
            json.dump(old_data, f)

        store = SemanticEvidenceStore(evidence_path=temp_evidence_file)

        assert "old_capability" in store.evidence
        assert store.is_suppressed("old_capability") is False

    def test_adding_failure_to_old_entry_creates_suppression(self, temp_evidence_file):
        """Adding failure to old entry without suppression should create it."""
        old_data = {
            "old_capability": {
                "purpose": "Old capability",
                "integrates_with": [],
                "provides_capabilities": [],
                "used_by": [],
                "key_abstractions": [],
                "discovered_at": datetime.now().isoformat()
            }
        }

        with open(temp_evidence_file, 'w') as f:
            json.dump(old_data, f)

        store = SemanticEvidenceStore(evidence_path=temp_evidence_file)
        store.record_failure("old_capability", reason="First failure")

        assert "suppression" in store.evidence["old_capability"]
        assert store.evidence["old_capability"]["suppression"]["failure_count"] == 1

    def test_atomic_persistence(self, store, temp_evidence_file):
        """Persistence should be atomic (temp file + rename)."""
        cap_key = "test_capability"

        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        with open(temp_evidence_file, 'r') as f:
            data = json.load(f)

        assert data[cap_key]["suppression"]["suppressed"] is True


class TestSuppressionLogging:
    """Test that suppression changes are logged."""

    def test_auto_suppression_logs_at_warning_level(self, store, caplog):
        """Auto-suppression should log at WARNING level."""
        import logging
        caplog.set_level(logging.WARNING)

        cap_key = "test_capability"
        for i in range(5):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        assert any("WARNING" in record.levelname for record in caplog.records)

    def test_manual_suppression_logs_at_info_level(self, store, caplog):
        """Manual suppression should log at INFO level."""
        import logging
        caplog.set_level(logging.INFO)

        cap_key = "test_capability"
        store.suppress(cap_key, reason="Admin command")

        assert any("suppressed" in record.message.lower() for record in caplog.records)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_reason_handled(self, store):
        """Empty reason should be handled gracefully."""
        store.record_failure("test_cap", reason="")
        assert store.evidence["test_cap"]["suppression"]["reason"] == ""

    def test_multiple_capabilities_independent(self, store):
        """Suppression of one capability should not affect others."""
        for i in range(5):
            store.record_failure("cap_1", reason=f"Failure {i+1}")

        store.record_failure("cap_2", reason="One failure")

        assert store.is_suppressed("cap_1") is True
        assert store.is_suppressed("cap_2") is False

    def test_user_override_flag_persistent(self, store):
        """user_can_override flag should persist."""
        cap_key = "test_capability"
        store.suppress(cap_key, reason="Test")

        assert store.evidence[cap_key]["suppression"]["user_can_override"] is True

    def test_suppress_until_initialized_to_none(self, store):
        """suppress_until should be initialized to None."""
        cap_key = "test_capability"
        store.record_failure(cap_key, reason="Test")

        assert store.evidence[cap_key]["suppression"]["suppress_until"] is None

    def test_large_failure_counts_handled(self, store):
        """Should handle capabilities with many failures."""
        cap_key = "test_capability"

        for i in range(100):
            store.record_failure(cap_key, reason=f"Failure {i+1}")

        assert store.evidence[cap_key]["suppression"]["failure_count"] == 100
        assert store.is_suppressed(cap_key) is True
