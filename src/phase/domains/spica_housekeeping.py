"""
SPICA Derivative: Housekeeping Parameter Optimization

SPICA-based optimization of KLoROS housekeeping parameters including:
- Event retention policy tuning
- Database vacuum frequency optimization
- Backup and cache cleanup aggressiveness
- Reflection log management parameters
- Condensation batch size tuning

KPIs: cleanup_time_sec, disk_space_freed_mb, db_size_mb, health_score, integrity_issues_count
"""
import time
import hashlib
import uuid
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result

logger = logging.getLogger(__name__)


@dataclass
class HousekeepingTestConfig:
    """Configuration for housekeeping optimization tests."""
    # Parameter bounds for optimization
    retention_days_min: int = 14
    retention_days_max: int = 60

    vacuum_days_min: int = 3
    vacuum_days_max: int = 14

    reflection_retention_min: int = 30
    reflection_retention_max: int = 90

    reflection_log_max_mb_min: int = 25
    reflection_log_max_mb_max: int = 100

    max_uncondensed_min: int = 50
    max_uncondensed_max: int = 200

    backup_retention_days_min: int = 14
    backup_retention_days_max: int = 60

    max_backups_per_file_min: int = 2
    max_backups_per_file_max: int = 5

    # Intelligent cleanup parameters
    deletion_confidence_min: float = 0.70  # Minimum deletion confidence threshold
    deletion_confidence_max: float = 0.95  # Maximum deletion confidence threshold

    # Signal weight ranges (must sum to 1.0)
    git_weight_min: float = 0.20
    git_weight_max: float = 0.60
    dependency_weight_min: float = 0.15
    dependency_weight_max: float = 0.45
    usage_weight_min: float = 0.10
    usage_weight_max: float = 0.35
    systemd_weight_min: float = 0.05
    systemd_weight_max: float = 0.20

    # Importance threshold ranges
    critical_threshold_min: float = 0.75  # Min score for CRITICAL
    critical_threshold_max: float = 0.90
    important_threshold_min: float = 0.55
    important_threshold_max: float = 0.75
    normal_threshold_min: float = 0.25
    normal_threshold_max: float = 0.45
    low_threshold_min: float = 0.10
    low_threshold_max: float = 0.25

    # Target KPIs
    target_cleanup_time_sec: float = 30.0  # Target cleanup under 30 seconds
    target_db_size_mb: float = 100.0  # Target database under 100MB
    target_health_score: float = 95.0  # Target health score > 95

    # Fitness weights (must sum to ~1.0)
    fitness_weight_performance: float = 0.20  # Cleanup speed
    fitness_weight_disk_efficiency: float = 0.20  # Disk space usage
    fitness_weight_health: float = 0.20  # System health
    fitness_weight_retention: float = 0.15  # Data retention balance
    fitness_weight_cleanup_accuracy: float = 0.25  # Intelligent cleanup accuracy


@dataclass
class HousekeepingTestResult:
    """Results from a single housekeeping configuration test."""
    test_id: str
    config_hash: str
    status: str

    # Configuration tested
    retention_days: int
    vacuum_days: int
    reflection_retention_days: int
    reflection_log_max_mb: int
    max_uncondensed_episodes: int
    backup_retention_days: int
    max_backups_per_file: int

    # Intelligent cleanup configuration
    deletion_confidence_threshold: float
    git_signal_weight: float
    dependency_signal_weight: float
    usage_signal_weight: float
    systemd_signal_weight: float
    critical_importance_threshold: float
    important_importance_threshold: float
    normal_importance_threshold: float
    low_importance_threshold: float

    # Performance metrics
    cleanup_time_sec: float
    tasks_completed: int
    errors: int

    # Disk metrics
    db_size_mb: float
    disk_space_freed_mb: float
    python_cache_freed_mb: float
    backup_files_deleted: int
    tts_files_deleted: int

    # Health metrics
    health_score: float
    integrity_issues: int

    # Cleanup results
    events_deleted: int
    episodes_condensed: int
    vacuum_performed: bool

    # Test metadata
    test_duration_sec: float
    test_timestamp: float

    # Intelligent cleanup metrics (with defaults, must come last)
    intelligent_cleanup_files_deleted: int = 0
    intelligent_cleanup_bytes_freed: int = 0
    files_correctly_identified: int = 0  # True positives + True negatives
    files_incorrectly_identified: int = 0  # False positives + False negatives
    classification_accuracy: float = 0.0  # files_correctly_identified / total_files


class SpicaHousekeeping(SpicaBase):
    """SPICA derivative for housekeeping parameter optimization."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[HousekeepingTestConfig] = None,
                 parent_id: Optional[str] = None, generation: int = 0,
                 mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-housekeeping-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'retention_days_min': test_config.retention_days_min,
                'retention_days_max': test_config.retention_days_max,
                'vacuum_days_min': test_config.vacuum_days_min,
                'vacuum_days_max': test_config.vacuum_days_max,
                'fitness_weight_performance': test_config.fitness_weight_performance,
                'fitness_weight_disk_efficiency': test_config.fitness_weight_disk_efficiency,
                'fitness_weight_health': test_config.fitness_weight_health,
                'fitness_weight_retention': test_config.fitness_weight_retention
            })

        super().__init__(
            spica_id=spica_id,
            domain="housekeeping",
            config=base_config,
            parent_id=parent_id,
            generation=generation,
            mutations=mutations
        )

        self.test_config = test_config or HousekeepingTestConfig()
        self.results: List[HousekeepingTestResult] = []

    def get_baseline_stats(self) -> Dict[str, Any]:
        """Get baseline system statistics before test."""
        try:
            from src.kloros_memory.housekeeping import MemoryHousekeeper
            housekeeper = MemoryHousekeeper()

            stats = housekeeper.get_comprehensive_stats()
            health = housekeeper.get_health_report()

            return {
                "db_size_bytes": stats.get("db_size_bytes", 0),
                "total_events": stats.get("total_events", 0),
                "total_episodes": stats.get("total_episodes", 0),
                "condensed_episodes": stats.get("condensed_episodes", 0),
                "health_score": health.get("health_score", 0),
                "integrity_issues": len(health.get("integrity_issues", []))
            }
        except Exception as e:
            logger.error(f"Failed to get baseline stats: {e}")
            return {
                "db_size_bytes": 0,
                "total_events": 0,
                "total_episodes": 0,
                "condensed_episodes": 0,
                "health_score": 0,
                "integrity_issues": 0
            }

    def run_test(self, candidate: Dict[str, Any]) -> HousekeepingTestResult:
        """Run single housekeeping configuration test."""
        test_id = f"housekeeping-{uuid.uuid4().hex[:8]}"
        config_hash = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]

        # Extract traditional parameters
        retention_days = candidate.get("retention_days", 30)
        vacuum_days = candidate.get("vacuum_days", 7)
        reflection_retention = candidate.get("reflection_retention_days", 60)
        reflection_log_max_mb = candidate.get("reflection_log_max_mb", 50)
        max_uncondensed = candidate.get("max_uncondensed_episodes", 100)
        backup_retention = candidate.get("backup_retention_days", 30)
        max_backups = candidate.get("max_backups_per_file", 3)

        # Extract intelligent cleanup parameters
        deletion_confidence = candidate.get("deletion_confidence_threshold", 0.85)
        git_weight = candidate.get("git_signal_weight", 0.40)
        dependency_weight = candidate.get("dependency_signal_weight", 0.30)
        usage_weight = candidate.get("usage_signal_weight", 0.20)
        systemd_weight = candidate.get("systemd_signal_weight", 0.10)
        critical_threshold = candidate.get("critical_importance_threshold", 0.80)
        important_threshold = candidate.get("important_importance_threshold", 0.60)
        normal_threshold = candidate.get("normal_importance_threshold", 0.30)
        low_threshold = candidate.get("low_importance_threshold", 0.15)

        # Validate bounds
        if not self._validate_parameters(candidate):
            logger.error(f"Parameters out of bounds for {candidate}")
            return self._create_invalid_result(test_id, config_hash, candidate)

        test_start = time.time()

        # Get baseline state
        baseline = self.get_baseline_stats()

        # Run housekeeping with test parameters
        try:
            cleanup_results = self._run_housekeeping_test(
                retention_days=retention_days,
                vacuum_days=vacuum_days,
                reflection_retention_days=reflection_retention,
                reflection_log_max_mb=reflection_log_max_mb,
                max_uncondensed_episodes=max_uncondensed,
                backup_retention_days=backup_retention,
                max_backups_per_file=max_backups
            )

            # Evaluate intelligent cleanup accuracy on test file set
            test_dir = Path("/tmp/kloros_cleanup_test")
            ground_truth = self._generate_test_file_set(test_dir)
            cleanup_eval = self._evaluate_intelligent_cleanup_accuracy(candidate, test_dir, ground_truth)

            # Get post-test stats
            post_stats = self.get_baseline_stats()

            test_duration = time.time() - test_start

            result = HousekeepingTestResult(
                test_id=test_id,
                config_hash=config_hash,
                status="pass",
                retention_days=retention_days,
                vacuum_days=vacuum_days,
                reflection_retention_days=reflection_retention,
                reflection_log_max_mb=reflection_log_max_mb,
                max_uncondensed_episodes=max_uncondensed,
                backup_retention_days=backup_retention,
                max_backups_per_file=max_backups,
                # Intelligent cleanup configuration
                deletion_confidence_threshold=deletion_confidence,
                git_signal_weight=git_weight,
                dependency_signal_weight=dependency_weight,
                usage_signal_weight=usage_weight,
                systemd_signal_weight=systemd_weight,
                critical_importance_threshold=critical_threshold,
                important_importance_threshold=important_threshold,
                normal_importance_threshold=normal_threshold,
                low_importance_threshold=low_threshold,
                # Traditional housekeeping metrics
                cleanup_time_sec=cleanup_results.get("cleanup_time", 0.0),
                tasks_completed=len(cleanup_results.get("tasks_completed", [])),
                errors=len(cleanup_results.get("errors", [])),
                db_size_mb=post_stats.get("db_size_bytes", 0) / (1024 * 1024),
                disk_space_freed_mb=cleanup_results.get("total_bytes_freed", 0) / (1024 * 1024),
                python_cache_freed_mb=cleanup_results.get("python_cache_freed_mb", 0),
                backup_files_deleted=cleanup_results.get("backup_files_deleted", 0),
                tts_files_deleted=cleanup_results.get("tts_files_deleted", 0),
                # Intelligent cleanup metrics
                intelligent_cleanup_files_deleted=cleanup_eval.get("true_positives", 0),
                intelligent_cleanup_bytes_freed=0,  # Not measured in evaluation
                files_correctly_identified=cleanup_eval.get("files_correctly_identified", 0),
                files_incorrectly_identified=cleanup_eval.get("files_incorrectly_identified", 0),
                classification_accuracy=cleanup_eval.get("classification_accuracy", 0.0),
                # Health metrics
                health_score=post_stats.get("health_score", 0),
                integrity_issues=post_stats.get("integrity_issues", 0),
                # Cleanup results
                events_deleted=cleanup_results.get("events_deleted", 0),
                episodes_condensed=cleanup_results.get("episodes_condensed", 0),
                vacuum_performed=cleanup_results.get("vacuum_performed", False),
                # Test metadata
                test_duration_sec=test_duration,
                test_timestamp=test_start
            )

            self.results.append(result)
            logger.info(f"Housekeeping test: {asdict(result)}")

            return result

        except Exception as e:
            logger.error(f"Housekeeping test failed: {e}")
            return self._create_error_result(test_id, config_hash, candidate, str(e))

    def _generate_test_file_set(self, test_dir: Path) -> Dict[str, str]:
        """
        Generate a diverse test file set with ground truth importance labels.

        Returns mapping of file_path -> expected_importance_class
        """
        import tempfile
        import shutil

        ground_truth = {}

        # Clean and recreate test directory
        if test_dir.exists():
            shutil.rmtree(test_dir)
        test_dir.mkdir(parents=True, exist_ok=True)

        # CRITICAL files: Active code in git, heavily imported
        critical_files = [
            (test_dir / "src" / "core" / "engine.py", "import sys\nimport os\nclass Engine:\n    pass"),
            (test_dir / "src" / "utils" / "helpers.py", "def helper():\n    return True"),
        ]
        for fpath, content in critical_files:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            ground_truth[str(fpath)] = "critical"

        # IMPORTANT files: Git-tracked code, some imports
        important_files = [
            (test_dir / "src" / "modules" / "processor.py", "# Processor module\ndef process():\n    pass"),
            (test_dir / "config" / "settings.json", '{"setting": "value"}'),
        ]
        for fpath, content in important_files:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            ground_truth[str(fpath)] = "important"

        # NORMAL files: Regular code, not heavily used
        normal_files = [
            (test_dir / "src" / "experimental" / "test_feature.py", "# Experimental\nprint('test')"),
            (test_dir / "docs" / "README.md", "# Documentation"),
        ]
        for fpath, content in normal_files:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            ground_truth[str(fpath)] = "normal"

        # LOW importance: Old files, rarely accessed
        low_files = [
            (test_dir / "old_scripts" / "migration.py", "# Old migration script"),
            (test_dir / "archive" / "data.txt", "archived data"),
        ]
        for fpath, content in low_files:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            ground_truth[str(fpath)] = "low"

        # OBSOLETE files: Backups, temp files, obvious candidates for deletion
        obsolete_files = [
            (test_dir / "file.backup", "backup content"),
            (test_dir / "temp_data.tmp", "temporary data"),
            (test_dir / "cache" / "old.bak", "backup"),
            (test_dir / "notes~", "temp notes"),
        ]
        for fpath, content in obsolete_files:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            ground_truth[str(fpath)] = "obsolete"

        return ground_truth

    def _evaluate_intelligent_cleanup_accuracy(
        self,
        candidate: Dict[str, Any],
        test_dir: Path,
        ground_truth: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Evaluate intelligent cleanup classification accuracy on test file set.

        Returns classification metrics: accuracy, true/false positives, etc.
        """
        from src.kloros_memory.intelligent_cleanup import IntelligentCleanup

        # Extract intelligent cleanup parameters
        cleanup = IntelligentCleanup(
            root_path=str(test_dir),
            min_deletion_confidence=candidate.get("deletion_confidence_threshold", 0.85),
            git_weight=candidate.get("git_signal_weight", 0.40),
            dependency_weight=candidate.get("dependency_signal_weight", 0.30),
            usage_weight=candidate.get("usage_signal_weight", 0.20),
            systemd_weight=candidate.get("systemd_signal_weight", 0.10),
            critical_threshold=candidate.get("critical_importance_threshold", 0.80),
            important_threshold=candidate.get("important_importance_threshold", 0.60),
            normal_threshold=candidate.get("normal_importance_threshold", 0.30),
            low_threshold=candidate.get("low_importance_threshold", 0.15),
            dry_run=True  # Always dry-run for evaluation
        )

        # Analyze each test file
        classifications = {}
        for file_path in ground_truth.keys():
            try:
                metrics = cleanup.analyze_file(Path(file_path))
                classifications[file_path] = metrics.importance_class.value
            except Exception as e:
                logger.warning(f"Failed to analyze {file_path}: {e}")
                classifications[file_path] = "unknown"

        # Calculate accuracy metrics
        total_files = len(ground_truth)
        correct = 0
        false_positives = 0  # Important files marked obsolete (BAD!)
        true_positives = 0   # Obsolete files correctly identified
        false_negatives = 0  # Obsolete files marked important (missed)
        true_negatives = 0   # Important files correctly protected

        for file_path, expected in ground_truth.items():
            predicted = classifications.get(file_path, "unknown")

            # Direct match is best
            if predicted == expected:
                correct += 1

            # Evaluate deletion safety
            expected_is_important = expected in ["critical", "important", "normal"]
            predicted_is_deletable = predicted in ["obsolete", "low"]

            if expected_is_important and predicted_is_deletable:
                false_positives += 1  # CRITICAL ERROR: would delete important file
            elif expected == "obsolete" and predicted in ["obsolete", "low"]:
                true_positives += 1  # Correctly identified for deletion
            elif expected == "obsolete" and predicted_is_deletable == False:
                false_negatives += 1  # Missed obsolete file (conservative, OK)
            elif expected_is_important and predicted_is_deletable == False:
                true_negatives += 1  # Correctly protected important file

        accuracy = correct / total_files if total_files > 0 else 0.0
        files_correctly_identified = correct
        files_incorrectly_identified = total_files - correct

        return {
            "total_files": total_files,
            "files_correctly_identified": files_correctly_identified,
            "files_incorrectly_identified": files_incorrectly_identified,
            "classification_accuracy": accuracy,
            "true_positives": true_positives,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "classifications": classifications
        }

    def _validate_parameters(self, candidate: Dict[str, Any]) -> bool:
        """Validate that all parameters are within bounds."""
        checks = [
            (self.test_config.retention_days_min <= candidate.get("retention_days", 30) <= self.test_config.retention_days_max),
            (self.test_config.vacuum_days_min <= candidate.get("vacuum_days", 7) <= self.test_config.vacuum_days_max),
            (self.test_config.reflection_retention_min <= candidate.get("reflection_retention_days", 60) <= self.test_config.reflection_retention_max),
            (self.test_config.reflection_log_max_mb_min <= candidate.get("reflection_log_max_mb", 50) <= self.test_config.reflection_log_max_mb_max),
            (self.test_config.max_uncondensed_min <= candidate.get("max_uncondensed_episodes", 100) <= self.test_config.max_uncondensed_max),
            (self.test_config.backup_retention_days_min <= candidate.get("backup_retention_days", 30) <= self.test_config.backup_retention_days_max),
            (self.test_config.max_backups_per_file_min <= candidate.get("max_backups_per_file", 3) <= self.test_config.max_backups_per_file_max),
            # Intelligent cleanup parameter validation
            (self.test_config.deletion_confidence_min <= candidate.get("deletion_confidence_threshold", 0.85) <= self.test_config.deletion_confidence_max),
            (self.test_config.critical_threshold_min <= candidate.get("critical_importance_threshold", 0.80) <= self.test_config.critical_threshold_max),
            (self.test_config.important_threshold_min <= candidate.get("important_importance_threshold", 0.60) <= self.test_config.important_threshold_max),
            (self.test_config.normal_threshold_min <= candidate.get("normal_importance_threshold", 0.30) <= self.test_config.normal_threshold_max),
            (self.test_config.low_threshold_min <= candidate.get("low_importance_threshold", 0.15) <= self.test_config.low_threshold_max),
        ]

        # Validate signal weights are in bounds and sum to ~1.0
        weights = [
            candidate.get("git_signal_weight", 0.40),
            candidate.get("dependency_signal_weight", 0.30),
            candidate.get("usage_signal_weight", 0.20),
            candidate.get("systemd_signal_weight", 0.10)
        ]
        weight_sum = sum(weights)
        weights_valid = (
            all(self.test_config.git_weight_min <= weights[0] <= self.test_config.git_weight_max for _ in [0]) and
            all(self.test_config.dependency_weight_min <= weights[1] <= self.test_config.dependency_weight_max for _ in [0]) and
            all(self.test_config.usage_weight_min <= weights[2] <= self.test_config.usage_weight_max for _ in [0]) and
            all(self.test_config.systemd_weight_min <= weights[3] <= self.test_config.systemd_weight_max for _ in [0]) and
            0.95 <= weight_sum <= 1.05  # Allow small rounding tolerance
        )

        return all(checks) and weights_valid

    def _run_housekeeping_test(self, **params) -> Dict[str, Any]:
        """
        Run housekeeping with test parameters (dry-run mode for safety).

        NOTE: This simulates housekeeping with given parameters WITHOUT
        actually deleting data. For full evaluation, set KLR_HOUSEKEEPING_TEST_MODE=0.
        """
        test_mode = os.getenv("KLR_HOUSEKEEPING_TEST_MODE", "1") == "1"

        results = {
            "cleanup_time": 0.0,
            "tasks_completed": [],
            "errors": [],
            "total_bytes_freed": 0,
            "python_cache_freed_mb": 0,
            "backup_files_deleted": 0,
            "tts_files_deleted": 0,
            "events_deleted": 0,
            "episodes_condensed": 0,
            "vacuum_performed": False
        }

        try:
            from src.kloros_memory.housekeeping import MemoryHousekeeper
            from src.kloros_memory.storage import MemoryStore

            # Create housekeeper with test parameters
            store = MemoryStore()
            housekeeper = MemoryHousekeeper(store=store)

            # Override configuration parameters
            housekeeper.retention_days = params.get("retention_days", 30)
            housekeeper.auto_vacuum_days = params.get("vacuum_days", 7)
            housekeeper.reflection_retention_days = params.get("reflection_retention_days", 60)
            housekeeper.reflection_log_max_mb = params.get("reflection_log_max_mb", 50)
            housekeeper.max_uncondensed_episodes = params.get("max_uncondensed_episodes", 100)

            # Temporarily override environment variables for cleanup operations
            os.environ["KLR_BACKUP_RETENTION_DAYS"] = str(params.get("backup_retention_days", 30))
            os.environ["KLR_MAX_BACKUPS_PER_FILE"] = str(params.get("max_backups_per_file", 3))

            start_time = time.time()

            if test_mode:
                # TEST MODE: Simulate without actual deletions
                logger.info("Running housekeeping in TEST MODE (no actual deletions)")

                # Simulate cleanup metrics based on parameters
                # More aggressive retention = faster but less data
                retention_factor = 30.0 / max(params.get("retention_days", 30), 1)
                
                results["cleanup_time"] = 5.0 + (params.get("retention_days", 30) * 0.1)
                results["tasks_completed"] = ["cleanup_simulation", "metrics_collection"]
                results["total_bytes_freed"] = int(1024 * 1024 * 10 * retention_factor)  # Scale with retention
                results["python_cache_freed_mb"] = 2.5
                results["backup_files_deleted"] = max(2, int(5 * retention_factor))
                results["tts_files_deleted"] = max(5, int(10 * retention_factor))
                results["events_deleted"] = max(50, int(100 * retention_factor))
                results["episodes_condensed"] = int(params.get("max_uncondensed_episodes", 100) * 0.1)
                results["vacuum_performed"] = (params.get("vacuum_days", 7) <= 7)

            else:
                # LIVE MODE: Run actual housekeeping (use with caution!)
                logger.warning("Running housekeeping in LIVE MODE (actual deletions)")

                # Run selected housekeeping tasks
                # Task 1: Cleanup old events
                events_deleted = housekeeper.cleanup_old_events(params.get("retention_days"))
                results["events_deleted"] = events_deleted
                results["tasks_completed"].append("cleanup_old_events")

                # Task 2: Python cache cleanup
                cache_result = housekeeper.cleanup_python_cache()
                results["python_cache_freed_mb"] = cache_result.get("bytes_freed", 0) / (1024 * 1024)
                results["total_bytes_freed"] += cache_result.get("bytes_freed", 0)
                results["tasks_completed"].append("cleanup_python_cache")

                # Task 3: Backup file cleanup
                backup_result = housekeeper.cleanup_backup_files()
                results["backup_files_deleted"] = backup_result.get("files_deleted", 0)
                results["total_bytes_freed"] += backup_result.get("bytes_freed", 0)
                results["tasks_completed"].append("cleanup_backup_files")

                # Task 4: TTS output cleanup
                tts_result = housekeeper.cleanup_tts_outputs()
                results["tts_files_deleted"] = tts_result.get("files_deleted", 0)
                results["total_bytes_freed"] += tts_result.get("bytes_freed", 0)
                results["tasks_completed"].append("cleanup_tts_outputs")

                # Task 5: Condense episodes
                episodes_condensed = housekeeper.condense_pending_episodes(params.get("max_uncondensed_episodes"))
                results["episodes_condensed"] = episodes_condensed
                results["tasks_completed"].append("condense_episodes")

                # Task 6: Vacuum if needed
                if housekeeper._should_vacuum():
                    housekeeper.vacuum_database()
                    results["vacuum_performed"] = True
                    results["tasks_completed"].append("vacuum_database")

                results["cleanup_time"] = time.time() - start_time

        except Exception as e:
            logger.error(f"Housekeeping test execution failed: {e}")
            results["errors"].append(str(e))

        return results

    def _create_invalid_result(self, test_id: str, config_hash: str, candidate: Dict) -> HousekeepingTestResult:
        """Create result object for invalid configuration."""
        return HousekeepingTestResult(
            test_id=test_id,
            config_hash=config_hash,
            status="invalid",
            retention_days=candidate.get("retention_days", 0),
            vacuum_days=candidate.get("vacuum_days", 0),
            reflection_retention_days=candidate.get("reflection_retention_days", 0),
            reflection_log_max_mb=candidate.get("reflection_log_max_mb", 0),
            max_uncondensed_episodes=candidate.get("max_uncondensed_episodes", 0),
            backup_retention_days=candidate.get("backup_retention_days", 0),
            max_backups_per_file=candidate.get("max_backups_per_file", 0),
            # Intelligent cleanup configuration
            deletion_confidence_threshold=candidate.get("deletion_confidence_threshold", 0.85),
            git_signal_weight=candidate.get("git_signal_weight", 0.40),
            dependency_signal_weight=candidate.get("dependency_signal_weight", 0.30),
            usage_signal_weight=candidate.get("usage_signal_weight", 0.20),
            systemd_signal_weight=candidate.get("systemd_signal_weight", 0.10),
            critical_importance_threshold=candidate.get("critical_importance_threshold", 0.80),
            important_importance_threshold=candidate.get("important_importance_threshold", 0.60),
            normal_importance_threshold=candidate.get("normal_importance_threshold", 0.30),
            low_importance_threshold=candidate.get("low_importance_threshold", 0.15),
            cleanup_time_sec=999.0,
            tasks_completed=0,
            errors=1,
            db_size_mb=999.0,
            disk_space_freed_mb=0.0,
            python_cache_freed_mb=0.0,
            backup_files_deleted=0,
            tts_files_deleted=0,
            intelligent_cleanup_files_deleted=0,
            intelligent_cleanup_bytes_freed=0,
            files_correctly_identified=0,
            files_incorrectly_identified=0,
            classification_accuracy=0.0,
            health_score=0.0,
            integrity_issues=999,
            events_deleted=0,
            episodes_condensed=0,
            vacuum_performed=False,
            test_duration_sec=0.0,
            test_timestamp=time.time()
        )

    def _create_error_result(self, test_id: str, config_hash: str, candidate: Dict, error: str) -> HousekeepingTestResult:
        """Create result object for failed test."""
        logger.error(f"Test error: {error}")
        return HousekeepingTestResult(
            test_id=test_id,
            config_hash=config_hash,
            status="error",
            retention_days=candidate.get("retention_days", 0),
            vacuum_days=candidate.get("vacuum_days", 0),
            reflection_retention_days=candidate.get("reflection_retention_days", 0),
            reflection_log_max_mb=candidate.get("reflection_log_max_mb", 0),
            max_uncondensed_episodes=candidate.get("max_uncondensed_episodes", 0),
            backup_retention_days=candidate.get("backup_retention_days", 0),
            max_backups_per_file=candidate.get("max_backups_per_file", 0),
            # Intelligent cleanup configuration
            deletion_confidence_threshold=candidate.get("deletion_confidence_threshold", 0.85),
            git_signal_weight=candidate.get("git_signal_weight", 0.40),
            dependency_signal_weight=candidate.get("dependency_signal_weight", 0.30),
            usage_signal_weight=candidate.get("usage_signal_weight", 0.20),
            systemd_signal_weight=candidate.get("systemd_signal_weight", 0.10),
            critical_importance_threshold=candidate.get("critical_importance_threshold", 0.80),
            important_importance_threshold=candidate.get("important_importance_threshold", 0.60),
            normal_importance_threshold=candidate.get("normal_importance_threshold", 0.30),
            low_importance_threshold=candidate.get("low_importance_threshold", 0.15),
            cleanup_time_sec=999.0,
            tasks_completed=0,
            errors=1,
            db_size_mb=999.0,
            disk_space_freed_mb=0.0,
            python_cache_freed_mb=0.0,
            backup_files_deleted=0,
            tts_files_deleted=0,
            intelligent_cleanup_files_deleted=0,
            intelligent_cleanup_bytes_freed=0,
            files_correctly_identified=0,
            files_incorrectly_identified=0,
            classification_accuracy=0.0,
            health_score=0.0,
            integrity_issues=999,
            events_deleted=0,
            episodes_condensed=0,
            vacuum_performed=False,
            test_duration_sec=0.0,
            test_timestamp=time.time()
        )

    def compute_fitness(self, result: HousekeepingTestResult) -> float:
        """Compute fitness score for a housekeeping configuration."""
        if result.status != "pass":
            return 0.0

        # Performance score: faster cleanup is better
        perf_norm = 1.0 - min(result.cleanup_time_sec / self.test_config.target_cleanup_time_sec, 1.0)

        # Disk efficiency: more space freed and smaller DB is better
        disk_freed_norm = min(result.disk_space_freed_mb / 50.0, 1.0)  # Target 50MB freed
        db_size_norm = 1.0 - min(result.db_size_mb / self.test_config.target_db_size_mb, 1.0)
        disk_efficiency = (disk_freed_norm + db_size_norm) / 2.0

        # Health score: higher is better
        health_norm = result.health_score / 100.0

        # Retention balance: not too aggressive (data loss) nor too conservative (bloat)
        # Optimal retention around 30 days
        retention_deviation = abs(result.retention_days - 30.0)
        retention_norm = 1.0 - min(retention_deviation / 30.0, 1.0)

        # Classification accuracy: higher is better (target > 98%)
        # This is the most important metric for intelligent cleanup
        cleanup_accuracy_norm = result.classification_accuracy

        # Weighted sum
        fitness = (
            perf_norm * self.test_config.fitness_weight_performance +
            disk_efficiency * self.test_config.fitness_weight_disk_efficiency +
            health_norm * self.test_config.fitness_weight_health +
            retention_norm * self.test_config.fitness_weight_retention +
            cleanup_accuracy_norm * self.test_config.fitness_weight_cleanup_accuracy
        )

        # Penalty for errors or integrity issues
        if result.errors > 0:
            fitness *= 0.5
        if result.integrity_issues > 0:
            fitness *= 0.8

        # Heavy penalty for false positives (would delete important files)
        # This is CRITICAL - we never want to delete important files
        if result.files_incorrectly_identified > 0:
            # Calculate false positive rate from incorrect identifications
            # If any important files marked for deletion, severely penalize
            false_positive_penalty = 1.0 - (result.files_incorrectly_identified / max(result.files_correctly_identified + result.files_incorrectly_identified, 1))
            fitness *= false_positive_penalty

        return fitness

    def evaluate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a candidate housekeeping configuration."""
        result = self.run_test(candidate)
        fitness = self.compute_fitness(result)

        return {
            # Traditional metrics
            "cleanup_time_sec": result.cleanup_time_sec,
            "disk_space_freed_mb": result.disk_space_freed_mb,
            "db_size_mb": result.db_size_mb,
            "health_score": result.health_score,
            "integrity_issues": result.integrity_issues,
            "tasks_completed": result.tasks_completed,
            # Intelligent cleanup metrics
            "classification_accuracy": result.classification_accuracy,
            "files_correctly_identified": result.files_correctly_identified,
            "files_incorrectly_identified": result.files_incorrectly_identified,
            # Fitness and status
            "fitness": fitness,
            "status": result.status
        }


def test_housekeeping_optimization():
    """Test the housekeeping optimization evaluator."""
    evaluator = SpicaHousekeeping()

    candidate = {
        "retention_days": 30,
        "vacuum_days": 7,
        "reflection_retention_days": 60,
        "reflection_log_max_mb": 50,
        "max_uncondensed_episodes": 100,
        "backup_retention_days": 30,
        "max_backups_per_file": 3
    }

    print("Testing Housekeeping Optimization Evaluator (SPICA)")
    print("=" * 70)
    print(f"Candidate: {json.dumps(candidate, indent=2)}")
    print("\nNOTE: Running in TEST MODE (no actual deletions)")
    print("Set KLR_HOUSEKEEPING_TEST_MODE=0 for live testing")

    metrics = evaluator.evaluate(candidate)

    print("\nResults:")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    test_housekeeping_optimization()
