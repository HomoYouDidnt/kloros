"""
SPICA Tournament Evaluator for D-REAM.

Spawns SPICA instances from candidate parameters,
submits to PHASE HTC tournament, and returns fitness scores.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# SPICA + PHASE adapters
from integrations.spica_spawn import spawn_instance, prune_instances
from integrations.phase_adapter import submit_tournament
import logging

logger = logging.getLogger(__name__)

# Feature flag: Use bracket tournament (fast) vs PHASE sequential (legacy)
USE_BRACKET_TOURNAMENT = os.getenv("KLR_USE_BRACKET_TOURNAMENT", "0") == "1"

# SPICA instance root directory
SPICA_INSTANCES = Path("/home/kloros/experiments/spica/instances")


class SPICATournamentEvaluator:
    """
    D-REAM evaluator that:
      1) Spawns N SPICA instances from candidate param sets
      2) Submits them to PHASE (Hyperbolic Time Chamber)
      3) Returns per-candidate fitness + artifacts for judging

    This is the bridge between D-REAM's evolutionary loop
    and SPICA's tournament-based variant selection.
    """

    def __init__(self, suite_id: str, qtime: Dict[str, int]):
        """
        Args:
            suite_id: Test suite identifier (e.g., "qa.rag.gold")
            qtime: Quantum time config with epochs, slices_per_epoch, replicas_per_slice
        """
        self.suite_id = suite_id
        self.qtime = qtime

    def evaluate(self, candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Single-candidate evaluation (legacy interface).

        Args:
            candidate: Parameter dictionary
            context: D-REAM context (experiment, generation, etc.)

        Returns:
            Metrics dictionary with fitness
        """
        # Spawn single instance
        instance_id = spawn_instance(
            mutations=candidate,
            parent_id=None,
            notes=f"D-REAM gen={context.get('generation', 0)} exp={context.get('experiment')}"
        )

        # Run tournament (single instance)
        tournament = submit_tournament(
            instances=[instance_id],
            suite_id=self.suite_id,
            qtime=self.qtime
        )

        # Extract metrics
        results = tournament.get("results", {})
        verified = results.get("passed", 0)
        failed = results.get("failed", 0)

        # Simple fitness: verification success rate
        fitness = verified / max(1, verified + failed)

        return {
            "fitness": fitness,
            "exact_match_mean": fitness,  # Placeholder - real PHASE would return this
            "latency_p50_ms": 100.0,      # Placeholder
            "passed": verified,
            "failed": failed,
            "spica_id": instance_id,
            "tournament": tournament
        }

    def evaluate_batch(self, candidates: List[Dict[str, Any]], context: Dict[str, Any] = None) -> Tuple[List[float], Dict[str, Any]]:
        """
        Batch evaluation for tournament mode.

        Args:
            candidates: List of parameter dicts from selector (RZero/QD/etc.)
            context: D-REAM context (optional)

        Returns:
            fitnesses: List[float] aligned to candidates
            artifacts: Dict with tournament.json and instance metadata
        """
        if context is None:
            context = {}

        # 1) Spawn instances deterministically from candidate params
        instance_paths: List[str] = []
        instance_map: List[Dict[str, Any]] = []

        for i, cand in enumerate(candidates):
            inst = spawn_instance(
                mutations=cand,
                parent_id=None,
                notes=f"D-REAM gen={context.get('generation', 0)} candidate={i}",
                auto_prune=False  # Disable auto-prune during batch spawn to prevent race condition
            )
            instance_paths.append(inst)
            instance_map.append({
                "params": cand,
                "instance_path": inst,
                "candidate_idx": i
            })

        # 2) Run tournament (bracket or PHASE based on feature flag)
        if USE_BRACKET_TOURNAMENT:
            logger.info("[TOURNAMENT] Using BRACKET tournament (fast parallel execution)")
            from dream.test_runner import DirectTestRunner
            from dream.evaluators.bracket_tournament import BracketTournament

            # Convert short instance IDs to full paths for DirectTestRunner
            full_instance_paths = [SPICA_INSTANCES / inst_id for inst_id in instance_paths]

            runner = DirectTestRunner(timeout=30)
            bracket = BracketTournament(full_instance_paths, runner)
            bracket_result = bracket.run(max_workers=4)

            champion = bracket_result["champion"]
            logger.info(
                f"[TOURNAMENT] Champion: {champion.name} "
                f"(duration: {bracket_result['total_duration_ms']:.0f}ms, "
                f"matches: {bracket_result['total_matches']})"
            )

            fitnesses: List[float] = []
            metrics_by_path: Dict[str, Dict[str, Any]] = {}

            for i, inst_path in enumerate(instance_paths):
                # Create full path to match champion Path object
                inst_path_full = SPICA_INSTANCES / inst_path
                inst_path_obj = Path(inst_path)

                # Compare full paths (champion is returned as full Path from bracket tournament)
                if inst_path_full == champion:
                    fitness = 1.0
                    round_eliminated = None
                    logger.info(f"[FITNESS] Instance {i} ({inst_path_obj.name}): CHAMPION - fitness=1.0")
                else:
                    round_eliminated = self._find_elimination_round(inst_path_full, bracket_result["rounds"])
                    fitness = 0.3 + (round_eliminated * 0.2)
                    logger.info(
                        f"[FITNESS] Instance {i} ({inst_path_obj.name}): "
                        f"eliminated round {round_eliminated} - fitness={fitness:.3f}"
                    )

                fitnesses.append(fitness)
                metrics_by_path[inst_path] = {
                    "spica_id": inst_path_obj.name,
                    "fitness": fitness,
                    "is_champion": inst_path_full == champion,
                    "round_eliminated": round_eliminated
                }

            # Convert champion Path to string for JSON serialization
            bracket_result_serializable = {
                "champion": str(bracket_result["champion"]),
                "rounds": bracket_result["rounds"],
                "total_duration_ms": bracket_result["total_duration_ms"],
                "total_matches": bracket_result["total_matches"],
                "total_candidates": bracket_result["total_candidates"]
            }

            artifacts = {
                "bracket_tournament": bracket_result_serializable,
                "instances": instance_map,
                "metrics_by_path": metrics_by_path,
                "suite_id": self.suite_id,
                "qtime": self.qtime,
                "tournament_type": "bracket"
            }

        else:
            logger.info("[TOURNAMENT] Using PHASE sequential tournament (legacy mode)")
            tournament = submit_tournament(
                instances=instance_paths,
                suite_id=self.suite_id,
                qtime=self.qtime
            )

            # 3) Extract fitness from tournament results using per-instance pass_rate
            fitnesses: List[float] = []
            metrics_by_path: Dict[str, Dict[str, Any]] = {}

            results = tournament.get("results", {})
            aggregated_by_instance = results.get("aggregated_by_instance", {})

            logger.info(f"[FITNESS_DEBUG] Per-instance results available: {list(aggregated_by_instance.keys())}")

            for i, m in enumerate(instance_map):
                # Read spica_id from manifest (construct absolute path)
                instance_id = m["instance_path"]  # This is just "spica-xxxxxxxx"
                manifest_path = SPICA_INSTANCES / instance_id / "manifest.json"

                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    spica_id = manifest["spica_id"]

                    # Extract per-instance fitness from aggregated results
                    if spica_id in aggregated_by_instance:
                        inst_stats = aggregated_by_instance[spica_id]
                        pass_rate = inst_stats.get("pass_rate", 0.0)
                        avg_latency = inst_stats.get("avg_latency_p50_ms", 0.0)
                        avg_exact_match = inst_stats.get("avg_exact_match_mean", 0.0)
                        passed = inst_stats.get("passed", 0)
                        failed = inst_stats.get("failed", 0)
                        total = inst_stats.get("total", 0)

                        # Composite fitness:
                        # - 70% correctness (pass_rate + exact_match_mean)
                        # - 30% speed bonus (penalize high latency)
                        # Latency normalized: 1.0 for <100ms, decreasing to 0.0 for >10000ms
                        latency_score = max(0.0, 1.0 - (avg_latency / 10000.0)) if avg_latency > 0 else 1.0

                        fitness = (
                            0.4 * pass_rate +           # Primary: tests passing
                            0.3 * avg_exact_match +     # Secondary: accuracy
                            0.3 * latency_score         # Tertiary: speed
                        )

                        logger.info(
                            f"[FITNESS] Instance {i} ({spica_id}): fitness={fitness:.3f} "
                            f"(pass={pass_rate:.3f}, acc={avg_exact_match:.3f}, "
                            f"lat={avg_latency:.1f}ms→{latency_score:.3f})"
                        )
                    else:
                        # Instance not in aggregated results (shouldn't happen)
                        logger.warning(f"[FITNESS] Instance {i} ({spica_id}): NOT IN aggregated_by_instance, using 0.0")
                        fitness = 0.0
                        passed = failed = total = 0
                        avg_latency = 0.0
                        avg_exact_match = 0.0

                    fitnesses.append(fitness)

                    metrics_by_path[m["instance_path"]] = {
                        "spica_id": spica_id,
                        "fitness": fitness,
                        "passed": passed,
                        "failed": failed,
                        "total": total,
                        "avg_latency_p50_ms": avg_latency,
                        "avg_exact_match_mean": avg_exact_match,
                        "latency_score": latency_score if 'latency_score' in locals() else 0.0
                    }
                else:
                    # Failed to spawn
                    logger.warning(f"[FITNESS] Instance {i}: manifest NOT FOUND, appending 0.0")
                    fitnesses.append(0.0)
                    metrics_by_path[m["instance_path"]] = {
                        "error": "manifest not found"
                    }

            logger.info(f"[FITNESS] Final fitnesses: {[f'{f:.3f}' for f in fitnesses]}")
            logger.info(f"[FITNESS] Max={max(fitnesses) if fitnesses else 0:.3f}, Min={min(fitnesses) if fitnesses else 0:.3f}, Avg={sum(fitnesses)/len(fitnesses) if fitnesses else 0:.3f}")

            # Determine champion (highest fitness)
            champion_idx = fitnesses.index(max(fitnesses)) if fitnesses else 0
            champion_instance = instance_map[champion_idx]["instance_path"] if instance_map else "unknown"

            # Get champion spica_id from manifest
            champion_spica_id = "unknown"
            if champion_instance != "unknown":
                manifest_path = SPICA_INSTANCES / champion_instance / "manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text())
                        champion_spica_id = manifest["spica_id"]
                    except Exception:
                        pass

            artifacts = {
                "tournament": tournament,
                "instances": instance_map,
                "metrics_by_path": metrics_by_path,
                "suite_id": self.suite_id,
                "qtime": self.qtime,
                "tournament_type": "phase_sequential",
                "bracket_tournament": {
                    "champion": champion_spica_id,
                    "total_candidates": len(candidates),
                    "max_fitness": max(fitnesses) if fitnesses else 0.0
                }
            }

        # Cleanup: Prune instances after tournament completes
        try:
            prune_result = prune_instances(max_instances=2, max_age_days=1, dry_run=False)
            logger.info(f"Post-tournament cleanup: pruned {prune_result.get('pruned', 0)} instances")
        except Exception as e:
            logger.warning(f"Post-tournament cleanup failed (non-fatal): {e}")

        logger.info(f"[FITNESS_DEBUG] Returning fitnesses to curiosity_processor: {fitnesses}")
        return fitnesses, artifacts

    def _find_elimination_round(self, instance_path: Path, rounds: List[Dict[str, Any]]) -> int:
        """
        Find which round an instance was eliminated in.

        Args:
            instance_path: Path to instance to check
            rounds: List of round results from bracket tournament

        Returns:
            Round number where instance was eliminated (1-indexed)
            Returns 0 if instance was never in tournament (shouldn't happen)
        """
        instance_name = instance_path.name

        for round_data in rounds:
            winners = round_data.get("winners", [])
            if instance_name not in winners:
                return round_data["round"]

        return 0
