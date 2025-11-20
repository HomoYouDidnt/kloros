"""
PHASE Two-Track Testing Framework

Compares behavioral equivalence between legacy implementations and wrapper zooids
before deployment to shadow mode or production.

Architecture:
- Parallel execution of legacy + wrapper
- Deep comparison of outputs/side-effects
- Drift detection and reporting
- Success cycle tracking
"""

import time
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import traceback

logger = logging.getLogger(__name__)


class TestClass(Enum):
    """
    Test classification for PHASE validation.

    BEHAVIORAL: Tests that verify functional equivalence (count toward pass/fail)
    STRUCTURAL: Tests that document architectural changes (informational only)
    """
    BEHAVIORAL = "behavioral"
    STRUCTURAL = "structural"


# Metadata fields to exclude from behavioral drift calculation
# These are architectural additions for zooid ecology, not behavioral differences
EXCLUDED_METADATA_FIELDS = {
    "genome_id",
    "niche",
    "generation",
    "lineage",
    "parent_lineage",
    "genome_hash",
    "lifecycle_state",
    "spawn_timestamp",
    "last_updated",
    "has_genome_id",  # From configuration tests
    "has_tick",        # Interface detection fields
    "type",            # Class name (HousekeepingScheduler vs HousekeepingZooid)
    "subscriber_active",  # ChemBus subscription state (implementation detail, not core behavior)
}


@dataclass
class PHASEResult:
    """Result of a single PHASE comparison test."""
    niche: str
    test_scenario: str
    test_class: TestClass
    timestamp: float
    legacy_result: Optional[Dict[str, Any]]
    wrapper_result: Optional[Dict[str, Any]]
    legacy_error: Optional[str]
    wrapper_error: Optional[str]
    behavioral_match: bool
    drift_percentage: float
    comparison_details: Dict[str, Any]


class TwoTrackComparator:
    """
    Executes legacy and wrapper implementations in parallel and compares results.
    """

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or Path.home() / ".kloros" / "phase_testing"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def execute_test(
        self,
        niche: str,
        test_scenario: str,
        legacy_callable: callable,
        wrapper_callable: callable,
        test_class: TestClass = TestClass.BEHAVIORAL,
        legacy_args: Tuple = (),
        wrapper_args: Tuple = (),
        legacy_kwargs: Dict = None,
        wrapper_kwargs: Dict = None,
    ) -> PHASEResult:
        """
        Execute both implementations and compare results.

        Args:
            niche: Niche name (e.g., "maintenance_housekeeping")
            test_scenario: Description of test (e.g., "routine_cleanup")
            legacy_callable: Legacy implementation function
            wrapper_callable: Wrapper zooid function
            legacy_args: Positional args for legacy
            wrapper_args: Positional args for wrapper
            legacy_kwargs: Keyword args for legacy
            wrapper_kwargs: Keyword args for wrapper

        Returns:
            PHASEResult with comparison data
        """
        legacy_kwargs = legacy_kwargs or {}
        wrapper_kwargs = wrapper_kwargs or {}

        timestamp = time.time()

        # Execute legacy
        legacy_result = None
        legacy_error = None
        try:
            legacy_result = legacy_callable(*legacy_args, **legacy_kwargs)
        except Exception as e:
            legacy_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Legacy execution failed for {niche}.{test_scenario}: {legacy_error}")

        # Execute wrapper
        wrapper_result = None
        wrapper_error = None
        try:
            wrapper_result = wrapper_callable(*wrapper_args, **wrapper_kwargs)
        except Exception as e:
            wrapper_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Wrapper execution failed for {niche}.{test_scenario}: {wrapper_error}")

        # Compare results
        behavioral_match, drift_percentage, comparison_details = self._compare_results(
            legacy_result,
            wrapper_result,
            legacy_error,
            wrapper_error,
        )

        result = PHASEResult(
            niche=niche,
            test_scenario=test_scenario,
            test_class=test_class,
            timestamp=timestamp,
            legacy_result=legacy_result,
            wrapper_result=wrapper_result,
            legacy_error=legacy_error,
            wrapper_error=wrapper_error,
            behavioral_match=behavioral_match,
            drift_percentage=drift_percentage,
            comparison_details=comparison_details,
        )

        # Log result
        self._save_result(result)

        return result

    def _filter_metadata(self, data: Any) -> Any:
        """
        Recursively filter out metadata fields from comparison data.

        Args:
            data: Data structure to filter (dict, list, or primitive)

        Returns:
            Filtered data with metadata fields removed
        """
        if isinstance(data, dict):
            return {
                k: self._filter_metadata(v)
                for k, v in data.items()
                if k not in EXCLUDED_METADATA_FIELDS
            }
        elif isinstance(data, list):
            return [self._filter_metadata(item) for item in data]
        else:
            return data

    def _compare_results(
        self,
        legacy_result: Any,
        wrapper_result: Any,
        legacy_error: Optional[str],
        wrapper_error: Optional[str],
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Deep comparison of legacy vs wrapper results.

        Returns:
            (behavioral_match, drift_percentage, comparison_details)
        """
        comparison_details = {}

        # If both errored, check if error types match
        if legacy_error and wrapper_error:
            legacy_error_type = legacy_error.split(":")[0]
            wrapper_error_type = wrapper_error.split(":")[0]

            comparison_details["both_errored"] = True
            comparison_details["error_types_match"] = legacy_error_type == wrapper_error_type

            behavioral_match = legacy_error_type == wrapper_error_type
            drift_percentage = 0.0 if behavioral_match else 100.0

            return behavioral_match, drift_percentage, comparison_details

        # If one succeeded and one failed, that's a mismatch
        if (legacy_error and not wrapper_error) or (wrapper_error and not legacy_error):
            comparison_details["error_mismatch"] = True
            comparison_details["legacy_succeeded"] = legacy_error is None
            comparison_details["wrapper_succeeded"] = wrapper_error is None

            return False, 100.0, comparison_details

        # Both succeeded - compare results
        if legacy_result is None and wrapper_result is None:
            return True, 0.0, {"both_none": True}

        # Filter out metadata fields before comparison
        legacy_filtered = self._filter_metadata(legacy_result)
        wrapper_filtered = self._filter_metadata(wrapper_result)

        # Convert to comparable format
        legacy_str = json.dumps(legacy_filtered, sort_keys=True, default=str)
        wrapper_str = json.dumps(wrapper_filtered, sort_keys=True, default=str)

        # Hash for exact comparison
        legacy_hash = hashlib.sha256(legacy_str.encode()).hexdigest()
        wrapper_hash = hashlib.sha256(wrapper_str.encode()).hexdigest()

        comparison_details["legacy_hash"] = legacy_hash[:16]
        comparison_details["wrapper_hash"] = wrapper_hash[:16]
        comparison_details["exact_match"] = legacy_hash == wrapper_hash

        if legacy_hash == wrapper_hash:
            return True, 0.0, comparison_details

        # Calculate drift based on string similarity
        drift = self._calculate_drift(legacy_str, wrapper_str)
        comparison_details["calculated_drift"] = drift

        # Behavioral equivalence threshold: < 0.01% drift
        behavioral_match = drift < 0.01

        return behavioral_match, drift, comparison_details

    def _calculate_drift(self, legacy_str: str, wrapper_str: str) -> float:
        """
        Calculate percentage drift between two string representations.

        Uses Levenshtein-like edit distance normalized by length.
        """
        if legacy_str == wrapper_str:
            return 0.0

        # Simple character-level difference
        max_len = max(len(legacy_str), len(wrapper_str))
        if max_len == 0:
            return 0.0

        # Count differing characters
        differences = sum(1 for a, b in zip(legacy_str, wrapper_str) if a != b)
        differences += abs(len(legacy_str) - len(wrapper_str))

        drift_percentage = (differences / max_len) * 100

        return drift_percentage

    def _save_result(self, result: PHASEResult) -> None:
        """Save PHASE result to disk for analysis."""
        timestamp_str = datetime.fromtimestamp(result.timestamp).strftime("%Y%m%d_%H%M%S")
        filename = f"{result.niche}_{result.test_scenario}_{timestamp_str}.json"
        filepath = self.results_dir / filename

        with open(filepath, 'w') as f:
            json.dump(asdict(result), f, indent=2, default=str)

        logger.info(f"Saved PHASE result: {filepath}")


class PHASECycleTracker:
    """
    Tracks PHASE testing cycles and determines when wrappers are ready
    for shadow mode deployment.
    """

    def __init__(self, tracking_file: Path = None):
        self.tracking_file = tracking_file or Path.home() / ".kloros" / "phase_testing" / "cycle_tracker.json"
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)

    def load_tracker(self) -> Dict:
        """Load cycle tracker state."""
        if not self.tracking_file.exists():
            return {
                "niches": {},
                "last_updated": time.time(),
            }

        with open(self.tracking_file, 'r') as f:
            return json.load(f)

    def save_tracker(self, tracker: Dict) -> None:
        """Save cycle tracker state."""
        tracker["last_updated"] = time.time()

        with open(self.tracking_file, 'w') as f:
            json.dump(tracker, f, indent=2)

    def record_cycle(
        self,
        niche: str,
        results: List[PHASEResult],
    ) -> Dict[str, Any]:
        """
        Record a PHASE testing cycle for a niche.

        Args:
            niche: Niche name
            results: List of PHASE results from this cycle

        Returns:
            Cycle summary with readiness assessment
        """
        tracker = self.load_tracker()

        if niche not in tracker["niches"]:
            tracker["niches"][niche] = {
                "cycles": [],
                "consecutive_successes": 0,
                "total_cycles": 0,
                "ready_for_shadow": False,
            }

        niche_data = tracker["niches"][niche]

        # Separate behavioral and structural tests
        behavioral_results = [r for r in results if r.test_class == TestClass.BEHAVIORAL]
        structural_results = [r for r in results if r.test_class == TestClass.STRUCTURAL]

        # Analyze this cycle (only behavioral tests count for pass/fail)
        all_passed = all(r.behavioral_match for r in behavioral_results) if behavioral_results else False

        # Calculate drift metrics separately for behavioral and structural
        behavioral_max_drift = max(r.drift_percentage for r in behavioral_results) if behavioral_results else 0.0
        behavioral_avg_drift = sum(r.drift_percentage for r in behavioral_results) / len(behavioral_results) if behavioral_results else 0.0

        structural_max_drift = max(r.drift_percentage for r in structural_results) if structural_results else 0.0

        cycle_summary = {
            "cycle_number": niche_data["total_cycles"] + 1,
            "timestamp": time.time(),
            "test_count": len(results),
            "behavioral_test_count": len(behavioral_results),
            "structural_test_count": len(structural_results),
            "all_passed": all_passed,
            "behavioral_max_drift": behavioral_max_drift,
            "behavioral_avg_drift": behavioral_avg_drift,
            "structural_max_drift": structural_max_drift,
            "results": [
                {
                    "test_scenario": r.test_scenario,
                    "test_class": r.test_class.value,
                    "behavioral_match": r.behavioral_match,
                    "drift_percentage": r.drift_percentage,
                }
                for r in results
            ],
        }

        niche_data["cycles"].append(cycle_summary)
        niche_data["total_cycles"] += 1

        # Update consecutive successes
        if all_passed:
            niche_data["consecutive_successes"] += 1
        else:
            niche_data["consecutive_successes"] = 0

        # Check if ready for shadow mode (3 consecutive successful cycles)
        if niche_data["consecutive_successes"] >= 3:
            niche_data["ready_for_shadow"] = True
            logger.info(f"✅ {niche} is READY FOR SHADOW MODE (3 consecutive successful cycles)")

        self.save_tracker(tracker)

        return cycle_summary

    def get_readiness(self, niche: str) -> Dict[str, Any]:
        """Get readiness status for a niche."""
        tracker = self.load_tracker()

        if niche not in tracker["niches"]:
            return {
                "niche": niche,
                "status": "not_started",
                "total_cycles": 0,
                "consecutive_successes": 0,
                "ready_for_shadow": False,
            }

        niche_data = tracker["niches"][niche]

        return {
            "niche": niche,
            "status": "ready" if niche_data["ready_for_shadow"] else "testing",
            "total_cycles": niche_data["total_cycles"],
            "consecutive_successes": niche_data["consecutive_successes"],
            "ready_for_shadow": niche_data["ready_for_shadow"],
            "cycles_needed": max(0, 3 - niche_data["consecutive_successes"]),
        }


def run_cohort_1_tests() -> Dict[str, List[PHASEResult]]:
    """
    Run PHASE tests for Cohort 1 (maintenance_housekeeping, observability_logging).

    Returns:
        Dictionary mapping niche name to list of PHASE results
    """
    comparator = TwoTrackComparator()
    tracker = PHASECycleTracker()

    cohort_results = {}

    # Test maintenance_housekeeping
    logger.info("Testing maintenance_housekeeping...")

    # TODO: Implement actual test scenarios once legacy implementations are accessible
    # For now, return placeholder

    cohort_results["maintenance_housekeeping"] = []
    cohort_results["observability_logging"] = []

    return cohort_results
