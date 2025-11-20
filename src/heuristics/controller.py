#!/usr/bin/env python3
"""
Heuristic Controller for PHASE (Phased Heuristic Adaptive Scheduling Engine)

Continuously evaluates information yield vs. cost from recent PHASE runs and D-REAM outcomes,
then emits read-only hints that let PHASE adapt weights, fidelity, and phase type.

Signals:
- Y (yield): improvement signal per wall-clock cost
- C (cost): runtime × resource weight
- S (stability): 1 - flake rate
- N (novelty): KL/JS divergence of error vectors
- P (promotion): downstream acceptance rate

Phase Types:
- LIGHT: Quick diagnostics when resource pressure high
- DEEP: Intensive integration (default)
- REM: D-REAM meta-learning when high novelty/acceptance
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import math

from heuristics.dt import parse_ts_utc
from heuristics.bandit_state import BanditState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestGroupStats:
    """Statistics for a test group (pass type)."""
    name: str
    trials: int = 0
    passed: int = 0
    failed: int = 0
    total_runtime_s: float = 0.0
    flakes: int = 0  # Tests that alternate pass/fail
    unique_failures: set = None
    yield_score: float = 0.0
    cost_score: float = 0.0
    stability_score: float = 1.0
    novelty_score: float = 0.0

    def __post_init__(self):
        if self.unique_failures is None:
            self.unique_failures = set()


@dataclass
class Hints:
    """Read-only hints for PHASE adaptation."""
    schema_version: int = 1
    generated_at_utc: str = ""
    phase_type: str = "DEEP"  # LIGHT/DEEP/REM
    workers_hint: int = 0  # 0 = auto, >0 = specific count
    fidelity_hint: str = "standard"  # fast/standard/high
    test_group_overrides: Dict[str, Dict[str, Any]] = None
    pass_weights: Dict[str, float] = None
    rationale: str = ""
    signals: Dict[str, float] = None

    def __post_init__(self):
        if self.test_group_overrides is None:
            self.test_group_overrides = {}
        if self.pass_weights is None:
            self.pass_weights = {}
        if self.signals is None:
            self.signals = {}


class HeuristicController:
    """Adaptive controller for PHASE orchestration."""

    def __init__(self, root: str = "/home/kloros"):
        self.root = Path(root)
        self.runs_dir = self.root / "out" / "test_runs"
        self.logs_dir = self.root / "logs"
        self.hints_path = self.root / "out" / "hints.json"
        self.dreameval_status_path = self.root / "out" / "dreameval_status.json"

        # Scoring weights (tunable)
        self.alpha = 0.4  # Yield weight
        self.beta = 0.2   # Novelty weight
        self.gamma = 0.2  # Promotion impact weight
        self.delta = 0.15 # Stability weight
        self.lambda_cost = 0.05  # Cost penalty

        # Phase type thresholds
        self.light_cost_threshold = 3600  # Switch to LIGHT if avg cost > 1 hour
        self.rem_novelty_threshold = 0.6  # Switch to REM if novelty > 60%
        self.rem_acceptance_threshold = 0.7  # And D-REAM acceptance > 70%

        # UCB1 parameters
        self.ucb_exploration = 1.4  # Exploration constant
        self.total_trials = 0  # Total trials across all groups

        # Bandit state persistence
        self.bandit_state = BanditState()

        # Weight capping to prevent mode collapse
        self.min_weight = 0.10
        self.max_weight = 0.50

    def collect_recent_runs(self, lookback_hours: int = 24) -> List[Dict]:
        """Collect manifests from recent PHASE runs."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        runs = []

        if not self.runs_dir.exists():
            logger.warning(f"Runs directory not found: {self.runs_dir}")
            return runs

        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)

                # Parse timestamp (robust, handles Z/offsets/naive)
                completed_at_str = manifest.get('completed_at_utc', '')
                if not completed_at_str:
                    logger.warning(f"Manifest missing completed_at_utc: {manifest_path}")
                    continue

                completed_at = parse_ts_utc(completed_at_str)

                if completed_at < cutoff:
                    continue

                # Load associated files
                manifest['_results'] = self._load_jsonl(run_dir / "results.jsonl")
                manifest['_metrics'] = self._load_jsonl(run_dir / "metrics.jsonl")
                manifest['_dir'] = run_dir

                runs.append(manifest)
            except Exception as e:
                logger.warning(f"Failed to load manifest from {run_dir}: {e}")

        return sorted(runs, key=lambda r: r.get('completed_at_utc', ''))

    def _load_jsonl(self, path: Path) -> List[Dict]:
        """Load JSONL file."""
        if not path.exists():
            return []

        lines = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in {path}: {e}")
        return lines

    def load_recent_candidates(self, lookback_hours: int = 6) -> List[Dict]:
        """Load recent candidates from D-REAM with timestamp windowing."""
        candidates_path = Path('/var/log/dream/candidates.jsonl')
        if not candidates_path.exists():
            logger.warning("Candidates file not found: /var/log/dream/candidates.jsonl")
            return []

        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(hours=lookback_hours)

        # Use deque for memory efficiency on large files
        tail = deque(maxlen=500)

        with open(candidates_path, 'r') as f:
            for line in f:
                try:
                    j = json.loads(line.strip())
                    # Parse timestamp from various possible fields
                    ts_str = j.get('created_at_utc') or j.get('ts') or j.get('meta', {}).get('created_at')
                    if not ts_str:
                        continue

                    j_ts = parse_ts_utc(ts_str)
                    j['_ts_utc'] = j_ts
                    tail.append(j)
                except Exception as e:
                    logger.debug(f"Skipped malformed candidate line: {e}")
                    continue

        # Filter to window
        recent = [j for j in tail if j['_ts_utc'] >= window_start]
        return recent

    def compute_test_group_stats(self, runs: List[Dict]) -> Dict[str, TestGroupStats]:
        """Compute statistics for each test group (last-failed, new-first, seed, e2e, promotion)."""
        stats = {
            'last_failed': TestGroupStats('last_failed'),
            'new_first': TestGroupStats('new_first'),
            'seed_sweep': TestGroupStats('seed_sweep'),
            'e2e': TestGroupStats('e2e'),
            'promotion': TestGroupStats('promotion'),
        }

        # Track failure patterns for novelty detection
        failure_history = defaultdict(list)  # {test_name: [pass/fail sequence]}

        for run in runs:
            run_dir = run.get('_dir')
            if not run_dir:
                continue

            # Scan JSON reports
            for report_file in run_dir.glob("*.json"):
                report_name = report_file.stem

                # Classify report by name
                group = None
                if 'lf' in report_name:
                    group = 'last_failed'
                elif 'nf' in report_name:
                    group = 'new_first'
                elif 'seed' in report_name:
                    group = 'seed_sweep'
                elif 'e2e' in report_name:
                    group = 'e2e'
                elif 'phase0' in report_name:
                    group = 'promotion'  # Fast triage includes promotion

                if not group:
                    continue

                try:
                    with open(report_file) as f:
                        report = json.load(f)

                    summary = report.get('summary', {})
                    passed = summary.get('passed', 0)
                    failed = summary.get('failed', 0)
                    duration = report.get('duration', 0.0)

                    stats[group].trials += 1
                    stats[group].passed += passed
                    stats[group].failed += failed
                    stats[group].total_runtime_s += duration

                    # Track unique failures
                    for test in report.get('tests', []):
                        if test.get('outcome') == 'failed':
                            test_name = test.get('nodeid', '')
                            stats[group].unique_failures.add(test_name)
                            failure_history[test_name].append(False)
                        elif test.get('outcome') == 'passed':
                            test_name = test.get('nodeid', '')
                            failure_history[test_name].append(True)

                except Exception as e:
                    logger.warning(f"Failed to parse report {report_file}: {e}")

        # Detect flakes (tests with alternating pass/fail)
        for test_name, outcomes in failure_history.items():
            if len(outcomes) < 2:
                continue

            # Count transitions
            transitions = sum(1 for i in range(len(outcomes)-1) if outcomes[i] != outcomes[i+1])
            if transitions >= 2:  # At least 2 transitions = flaky
                # Find which group this test belongs to
                for group_stats in stats.values():
                    if test_name in group_stats.unique_failures:
                        group_stats.flakes += 1

        return stats

    def compute_signals(self, stats: Dict[str, TestGroupStats],
                       dreameval_status: Optional[Dict] = None) -> Dict[str, float]:
        """Compute Y, C, S, N, P signals."""
        signals = {}

        for name, group in stats.items():
            if group.trials == 0:
                continue

            # Yield (Y): failures detected per hour of runtime
            runtime_hours = group.total_runtime_s / 3600.0 if group.total_runtime_s > 0 else 0.01
            yield_score = len(group.unique_failures) / runtime_hours

            # Cost (C): average runtime per trial (normalized to minutes)
            cost_score = (group.total_runtime_s / group.trials) / 60.0 if group.trials > 0 else 0

            # Stability (S): 1 - flake rate
            total_tests = group.passed + group.failed
            flake_rate = group.flakes / total_tests if total_tests > 0 else 0
            stability_score = 1.0 - flake_rate

            # Novelty (N): ratio of unique failures to total failures
            novelty_score = (len(group.unique_failures) / group.failed) if group.failed > 0 else 0.5

            group.yield_score = yield_score
            group.cost_score = cost_score
            group.stability_score = stability_score
            group.novelty_score = novelty_score

            signals[f'{name}_yield'] = yield_score
            signals[f'{name}_cost'] = cost_score
            signals[f'{name}_stability'] = stability_score
            signals[f'{name}_novelty'] = novelty_score

        # Promotion impact (P): D-REAM candidate acceptance rate
        # Use recent candidates from last 6 hours for accurate windowed measurement
        try:
            recent_candidates = self.load_recent_candidates(lookback_hours=6)
            if recent_candidates:
                # Count "accepted" candidates vs total
                accepted = sum(1 for c in recent_candidates if c.get('accepted') or c.get('meta', {}).get('accepted'))
                total = len(recent_candidates)
                promotion_score = accepted / total if total > 0 else 0.0
                signals['promotion_acceptance'] = promotion_score
                signals['candidates_last_6h'] = total
            else:
                # Fallback to dreameval_status if no recent candidates
                if dreameval_status:
                    candidates = dreameval_status.get('candidates_emitted', 0)
                    evaluations = dreameval_status.get('evaluations_run', 0)
                    promotion_score = candidates / evaluations if evaluations > 0 else 0.0
                    signals['promotion_acceptance'] = promotion_score
                else:
                    signals['promotion_acceptance'] = 0.0
        except Exception as e:
            logger.warning(f"Failed to compute promotion acceptance: {e}")
            signals['promotion_acceptance'] = 0.0

        # Aggregate signals
        signals['avg_yield'] = sum(s.yield_score for s in stats.values()) / len(stats) if stats else 0
        signals['avg_cost'] = sum(s.cost_score for s in stats.values()) / len(stats) if stats else 0
        signals['avg_stability'] = sum(s.stability_score for s in stats.values()) / len(stats) if stats else 1.0
        signals['avg_novelty'] = sum(s.novelty_score for s in stats.values()) / len(stats) if stats else 0

        return signals

    def ucb1_score(self, group: TestGroupStats, total_trials: int) -> float:
        """Compute UCB1 score for a test group."""
        if group.trials == 0:
            return float('inf')  # Explore untried groups

        if total_trials == 0:
            return 1.0  # Uniform weights if no history

        # Exploitation: normalized yield-cost ratio
        exploit = group.yield_score / (group.cost_score + 0.1)  # Avoid div by zero

        # Exploration bonus
        explore = self.ucb_exploration * math.sqrt(math.log(total_trials) / group.trials)

        return exploit + explore

    def compute_pass_weights(self, stats: Dict[str, TestGroupStats]) -> Dict[str, float]:
        """Compute adaptive weights for each pass using UCB1."""
        self.total_trials = sum(s.trials for s in stats.values())

        if self.total_trials == 0:
            # Default uniform weights
            return {
                'last_failed': 1.0,
                'new_first': 1.0,
                'seed_sweep': 0.8,
                'e2e': 0.6,
                'promotion': 0.5,
            }

        # Compute UCB1 scores
        scores = {name: self.ucb1_score(group, self.total_trials)
                 for name, group in stats.items()}

        # Normalize to weights (softmax-like)
        max_score = max(scores.values()) if scores else 1.0
        # Clamp extreme values to avoid overflow
        weights = {name: math.exp(min(score / max(max_score, 0.1), 10.0))
                  for name, score in scores.items()}
        total_weight = sum(weights.values())

        if total_weight == 0 or not math.isfinite(total_weight):
            # Fallback to uniform if normalization fails
            return {
                'last_failed': 1.0,
                'new_first': 1.0,
                'seed_sweep': 0.8,
                'e2e': 0.6,
                'promotion': 0.5,
            }

        normalized = {name: w / total_weight for name, w in weights.items()}

        # Cap weights to prevent mode collapse
        capped = {name: max(self.min_weight, min(self.max_weight, w))
                 for name, w in normalized.items()}

        # Renormalize after capping
        capped_total = sum(capped.values())
        if capped_total > 0:
            capped = {name: w / capped_total for name, w in capped.items()}

        return capped

    def determine_phase_type(self, signals: Dict[str, float]) -> str:
        """Determine phase type based on signals."""
        avg_cost = signals.get('avg_cost', 0)
        avg_novelty = signals.get('avg_novelty', 0)
        promotion_acceptance = signals.get('promotion_acceptance', 0)

        # LIGHT: Resource pressure (high cost)
        if avg_cost > self.light_cost_threshold / 60.0:  # Convert to minutes
            return "LIGHT"

        # REM: High novelty + high D-REAM acceptance
        if avg_novelty > self.rem_novelty_threshold and promotion_acceptance > self.rem_acceptance_threshold:
            return "REM"

        # Default: DEEP
        return "DEEP"

    def determine_fidelity(self, phase_type: str, signals: Dict[str, float]) -> str:
        """Determine fidelity hint based on phase type."""
        if phase_type == "LIGHT":
            return "fast"
        elif phase_type == "REM":
            return "high"
        else:
            return "standard"

    def determine_workers(self, phase_type: str) -> int:
        """Determine worker count hint."""
        if phase_type == "LIGHT":
            return 0  # Auto (likely fewer)
        elif phase_type == "REM":
            return 0  # Auto (let xdist decide)
        else:
            return 0  # Auto

    def generate_hints(self) -> Hints:
        """Generate hints.json from recent PHASE runs and D-REAM status."""
        logger.info("Collecting recent PHASE runs...")
        runs = self.collect_recent_runs(lookback_hours=24)

        if not runs:
            logger.warning("No recent runs found, using default hints")
            return Hints(
                generated_at_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                phase_type="DEEP",
                workers_hint=0,
                fidelity_hint="standard",
                pass_weights={
                    'last_failed': 1.0,
                    'new_first': 1.0,
                    'seed_sweep': 0.8,
                    'e2e': 0.6,
                    'promotion': 0.5,
                },
                rationale="No recent runs, using defaults"
            )

        logger.info(f"Collected {len(runs)} recent runs")

        # Load D-REAM status
        dreameval_status = None
        if self.dreameval_status_path.exists():
            try:
                with open(self.dreameval_status_path) as f:
                    dreameval_status = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load dreameval_status.json: {e}")

        # Compute statistics
        logger.info("Computing test group statistics...")
        stats = self.compute_test_group_stats(runs)

        # Compute signals
        logger.info("Computing signals (Y, C, S, N, P)...")
        signals = self.compute_signals(stats, dreameval_status)

        # Compute pass weights using UCB1
        logger.info("Computing adaptive pass weights...")
        pass_weights = self.compute_pass_weights(stats)

        # Determine phase type
        phase_type = self.determine_phase_type(signals)
        logger.info(f"Determined phase type: {phase_type}")

        # Determine fidelity and workers
        fidelity_hint = self.determine_fidelity(phase_type, signals)
        workers_hint = self.determine_workers(phase_type)

        # Build rationale
        rationale = f"Phase={phase_type} based on cost={signals.get('avg_cost', 0):.1f}m, "
        rationale += f"novelty={signals.get('avg_novelty', 0):.2f}, "
        rationale += f"acceptance={signals.get('promotion_acceptance', 0):.2f}"

        return Hints(
            schema_version=1,
            generated_at_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            phase_type=phase_type,
            workers_hint=workers_hint,
            fidelity_hint=fidelity_hint,
            pass_weights=pass_weights,
            rationale=rationale,
            signals=signals
        )

    def write_hints(self, hints: Hints) -> None:
        """Atomically write hints.json."""
        self.hints_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        temp_path = self.hints_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(asdict(hints), f, indent=2)

        # Atomic rename
        temp_path.replace(self.hints_path)
        logger.info(f"Hints written to {self.hints_path}")

    def write_daily_snapshot(self) -> None:
        """Write daily summary snapshot for quick morning scans."""
        snapshot_path = self.root / "out" / "heuristics" / "summary.json"

        try:
            # Collect phase histogram from recent runs
            runs = self.collect_recent_runs(lookback_hours=24)
            phase_hist = defaultdict(int)
            for run in runs:
                # Would need to track phase_type used in manifest
                # For now, use most recent hints
                phase_hist["DEEP"] += 1  # Placeholder

            # Candidate stats
            recent_candidates = self.load_recent_candidates(lookback_hours=6)
            candidates_per_hour = len(recent_candidates) / 6.0 if recent_candidates else 0.0

            accepted = sum(1 for c in recent_candidates if c.get('accepted'))
            acceptance_ratio = accepted / len(recent_candidates) if recent_candidates else 0.0

            # Top groups by yield and cost
            stats = self.compute_test_group_stats(runs)
            top_yield = sorted(stats.items(), key=lambda x: x[1].yield_score, reverse=True)[:5]
            top_cost = sorted(stats.items(), key=lambda x: x[1].cost_score)[:5]

            snapshot = {
                "generated_at_utc": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "lookback_hours": 24,
                "phase_histogram": dict(phase_hist),
                "avg_pass_weights": self.compute_pass_weights(stats) if stats else {},
                "top_yield": {name: g.yield_score for name, g in top_yield},
                "top_cost": {name: g.cost_score for name, g in top_cost},
                "candidates_per_hour": candidates_per_hour,
                "acceptance_ratio": acceptance_ratio,
                "exploration_rate": self.bandit_state.get_exploration_rate(),
                "total_bandit_selections": self.bandit_state.total_selections
            }

            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(snapshot_path, 'w') as f:
                json.dump(snapshot, f, indent=2)

            logger.info(f"Daily snapshot written: {snapshot_path}")
        except Exception as e:
            logger.warning(f"Failed to write daily snapshot: {e}")

    def run(self) -> None:
        """Main controller loop."""
        logger.info("PHASE Heuristic Controller starting...")

        try:
            hints = self.generate_hints()
            self.write_hints(hints)

            # Save bandit state after generating hints
            self.bandit_state.save()

            # Write daily snapshot (checks time internally could be added)
            self.write_daily_snapshot()

            logger.info(f"✓ Generated hints: phase_type={hints.phase_type}, "
                       f"fidelity={hints.fidelity_hint}")
            logger.info(f"  Pass weights: {hints.pass_weights}")
            logger.info(f"  Rationale: {hints.rationale}")
            logger.info(f"  Exploration rate: {self.bandit_state.get_exploration_rate():.3f}")
        except Exception as e:
            logger.error(f"Controller failed: {e}", exc_info=True)
            raise


def main():
    """Entry point for heuristic controller."""
    controller = HeuristicController()
    controller.run()


if __name__ == '__main__':
    main()
