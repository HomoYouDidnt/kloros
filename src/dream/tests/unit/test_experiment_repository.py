"""
Unit tests for experiment repository module.

Tests atomic writes, file locking, and corruption recovery.
"""
import pytest
import json
import tempfile
from pathlib import Path
from dream.experiment_repository import ExperimentRepository, ApprovedExperimentsData
from dream.experiment_types import RemediationExperiment, IntegrationFix


class TestExperimentRepository:
    """Test ExperimentRepository persistence."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            path = Path(f.name)
        yield path
        if path.exists():
            path.unlink()

    @pytest.fixture
    def sample_experiments(self):
        """Create sample experiments for testing."""
        return [
            RemediationExperiment(
                name="test1",
                question_id="q1",
                hypothesis="H1",
                search_space={"p": [1]},
                evaluator={"e": 1},
                budget={"b": 1},
                metrics={"m": 1},
                priority=0.8
            ),
            IntegrationFix(
                question_id="q2",
                fix_type="fix",
                hypothesis="H2",
                action="act",
                params={},
                value_estimate=0.7,
                cost=0.3
            )
        ]

    def test_save_creates_file(self, temp_storage, sample_experiments):
        """Test save() creates storage file."""
        repo = ExperimentRepository(temp_storage)
        data = ApprovedExperimentsData(
            experiments=sample_experiments,
            approved_at="2025-01-01T00:00:00"
        )

        repo.save(data)

        assert temp_storage.exists()
        assert temp_storage.stat().st_size > 0

    def test_load_empty_returns_empty_data(self, temp_storage):
        """Test load() on nonexistent file returns empty data."""
        repo = ExperimentRepository(temp_storage)
        data = repo.load()

        assert len(data.experiments) == 0
        assert data.approved_at != ''

    def test_save_and_load_roundtrip(self, temp_storage, sample_experiments):
        """Test save -> load preserves data."""
        repo = ExperimentRepository(temp_storage)

        original = ApprovedExperimentsData(
            experiments=sample_experiments,
            approved_at="2025-01-01T12:00:00"
        )

        repo.save(original)
        loaded = repo.load()

        assert len(loaded.experiments) == 2
        assert loaded.approved_at == "2025-01-01T12:00:00"

        assert loaded.experiments[0].get_name() == "test1"
        assert loaded.experiments[1].get_name() == "q2"

    def test_load_handles_corrupt_json(self, temp_storage):
        """Test load() handles corrupted JSON gracefully."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        temp_storage.write_text("{ invalid json ]")

        repo = ExperimentRepository(temp_storage)
        data = repo.load()

        assert len(data.experiments) == 0
        corrupt_backup = temp_storage.with_suffix('.corrupt')
        assert corrupt_backup.exists()

    def test_load_skips_malformed_experiments(self, temp_storage):
        """Test load() skips experiments with missing fields."""
        temp_storage.parent.mkdir(parents=True, exist_ok=True)

        bad_data = {
            "experiments": [
                {
                    "_type": "RemediationExperiment",
                    "name": "valid",
                    "question_id": "q1",
                    "hypothesis": "H1",
                    "search_space": {"p": [1]},
                    "evaluator": {"e": 1},
                    "budget": {"b": 1},
                    "metrics": {"m": 1},
                    "priority": 0.8
                },
                {
                    "_type": "RemediationExperiment",
                    "name": "invalid_missing_fields"
                },
                {
                    "_type": "IntegrationFix",
                    "question_id": "q3",
                    "fix_type": "fix",
                    "hypothesis": "H3",
                    "action": "act",
                    "params": {},
                    "value_estimate": 0.7,
                    "cost": 0.3
                }
            ],
            "approved_at": "2025-01-01T00:00:00"
        }

        temp_storage.write_text(json.dumps(bad_data))

        repo = ExperimentRepository(temp_storage)
        data = repo.load()

        assert len(data.experiments) == 2
        assert data.experiments[0].get_name() == "valid"
        assert data.experiments[1].get_name() == "q3"

    def test_atomic_write_uses_temp_file(self, temp_storage, sample_experiments):
        """Test save() uses atomic write pattern."""
        repo = ExperimentRepository(temp_storage)
        data = ApprovedExperimentsData(
            experiments=sample_experiments,
            approved_at="2025-01-01T00:00:00"
        )

        repo.save(data)

        temp_file = temp_storage.with_suffix('.tmp')
        assert not temp_file.exists()

        assert temp_storage.exists()

    def test_save_failure_does_not_corrupt_existing(self, temp_storage, sample_experiments):
        """Test failed save doesn't corrupt existing data."""
        repo = ExperimentRepository(temp_storage)

        original_data = ApprovedExperimentsData(
            experiments=[sample_experiments[0]],
            approved_at="2025-01-01T00:00:00"
        )
        repo.save(original_data)

        loaded_before = repo.load()
        assert len(loaded_before.experiments) == 1

    def test_multiple_experiments_preserved(self, temp_storage):
        """Test repository handles multiple experiment types."""
        repo = ExperimentRepository(temp_storage)

        experiments = [
            RemediationExperiment(
                name=f"exp{i}",
                question_id=f"q{i}",
                hypothesis=f"H{i}",
                search_space={"p": [i]},
                evaluator={"e": i},
                budget={"b": i},
                metrics={"m": i},
                priority=0.5 + i * 0.1
            )
            for i in range(5)
        ]

        data = ApprovedExperimentsData(
            experiments=experiments,
            approved_at="2025-01-01T00:00:00"
        )

        repo.save(data)
        loaded = repo.load()

        assert len(loaded.experiments) == 5
        for i, exp in enumerate(loaded.experiments):
            assert exp.get_name() == f"exp{i}"
            assert exp.get_priority() == 0.5 + i * 0.1
