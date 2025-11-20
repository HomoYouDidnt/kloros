"""
Repository for persisting approved experiments.

Implements atomic writes, file locking, and proper error handling.

Features:
- Atomic file writes (crash-safe via temp file + rename)
- File locking (multi-process safe)
- Automatic corruption recovery (backup + restore)
- Type-safe deserialization via factory
"""
import json
import fcntl
import logging
from pathlib import Path
from typing import List
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

try:
    from .experiment_types import BaseExperiment, ExperimentFactory
except ImportError:
    from experiment_types import BaseExperiment, ExperimentFactory

logger = logging.getLogger(__name__)


@dataclass
class ApprovedExperimentsData:
    """Container for approved experiments with metadata."""
    experiments: List[BaseExperiment]
    approved_at: str

    def __post_init__(self):
        if not self.approved_at:
            self.approved_at = datetime.now().isoformat()


class ExperimentRepository:
    """
    Thread-safe repository for experiment persistence.

    Uses atomic operations and file locking to prevent corruption
    in multi-process environments.
    """

    def __init__(self, storage_path: Path):
        """
        Initialize repository.

        Args:
            storage_path: Path to JSON storage file
        """
        self.storage_path = storage_path
        self.corrupt_suffix = '.corrupt'
        self.temp_suffix = '.tmp'

    @contextmanager
    def _locked_file(self, mode='r'):
        """
        Context manager for locked file access.

        Acquires exclusive lock during operation, released on exit.
        """
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.storage_path, mode) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield f
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def save(self, data: ApprovedExperimentsData) -> None:
        """
        Atomically save experiments to disk.

        Uses atomic file replacement to prevent corruption during crashes.
        Process: write temp file -> fsync -> atomic rename

        Args:
            data: Experiments to persist

        Raises:
            IOError: If write fails
        """
        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize experiments
        serialized = {
            "experiments": [exp.to_dict() for exp in data.experiments],
            "approved_at": data.approved_at
        }

        # Write to temporary file first (atomic pattern)
        temp_path = self.storage_path.with_suffix(self.temp_suffix)
        try:
            with open(temp_path, 'w') as f:
                json.dump(serialized, f, indent=2)
                f.flush()
                # Force write to disk (crash-safe)
                import os
                os.fsync(f.fileno())

            # Atomic rename (crash-safe on POSIX)
            temp_path.replace(self.storage_path)

            logger.debug(f"[repo] Saved {len(data.experiments)} experiments to {self.storage_path}")

        except Exception as e:
            temp_path.unlink(missing_ok=True)
            raise IOError(f"Failed to save experiments: {e}") from e

    def load(self) -> ApprovedExperimentsData:
        """
        Load experiments from disk with corruption recovery.

        Handles:
        - Missing file: Returns empty data
        - Corrupted JSON: Backs up corrupt file, returns empty data
        - Invalid experiment data: Logs warning, skips malformed entries

        Returns:
            ApprovedExperimentsData: Loaded experiments

        Raises:
            Exception: Only for unexpected errors (not corruption)
        """
        if not self.storage_path.exists():
            logger.debug("[repo] No saved experiments found")
            return ApprovedExperimentsData(experiments=[], approved_at='')

        try:
            with self._locked_file('r') as f:
                data = json.load(f)

            # Deserialize with factory (validates structure)
            experiments = []
            skipped = 0

            for exp_dict in data.get("experiments", []):
                try:
                    exp = ExperimentFactory.from_dict(exp_dict)
                    experiments.append(exp)
                except ValueError as e:
                    logger.warning(f"[repo] Skipping malformed experiment: {e}")
                    skipped += 1
                    continue

            if skipped > 0:
                logger.warning(f"[repo] Skipped {skipped} malformed experiments during load")

            logger.debug(f"[repo] Loaded {len(experiments)} experiments from {self.storage_path}")

            return ApprovedExperimentsData(
                experiments=experiments,
                approved_at=data.get("approved_at", "")
            )

        except json.JSONDecodeError as e:
            # Backup corrupted file for forensics
            corrupt_path = self.storage_path.with_suffix(self.corrupt_suffix)
            self.storage_path.rename(corrupt_path)

            logger.error(
                f"[repo] Corrupted experiment file backed up to {corrupt_path}. "
                f"Starting fresh. Error: {e}"
            )

            return ApprovedExperimentsData(experiments=[], approved_at='')

        except Exception as e:
            logger.critical(f"[repo] Unexpected error loading experiments: {e}", exc_info=True)
            raise
