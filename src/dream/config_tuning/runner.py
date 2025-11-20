"""
D-REAM Config Tuning Runner

Autonomous configuration parameter tuning with bounded canary testing.

Flow:
1. Accept intent with seed_fix or context
2. Generate candidate configurations (or use seed)
3. Launch SPICA canaries to test each candidate
4. Compute fitness scores
5. Promote best candidate or escalate

Safety:
- All parameters bounded by actuators.py
- Max 3 canaries per 24h per subsystem
- 6h cooldown after failures
- Ephemeral params only (no baseline writes until PHASE validation)
"""

import os
import json
import time
import uuid
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from .actuators import generate_candidates, validate_candidate, ACTUATOR_BOUNDS

logger = logging.getLogger(__name__)

# Two-mode operation: predictive (no downtime) vs canary (real VLLM test)
MODE = os.environ.get("KLR_CANARY_MODE", "predictive").lower()

# Import canary runner for canary mode
import sys
sys.path.insert(0, '/home/kloros')
from src.spica.gpu_canary_runner import run_canary, CanaryOutcome as GPUCanaryOutcome


@dataclass
class CanaryResult:
    """Result from a single canary test."""
    candidate_id: str
    candidate: Dict[str, float]
    status: str  # "pass", "fail", "invalid"
    fitness: float
    metrics: Dict[str, Any]
    test_duration_s: float
    timestamp: float


@dataclass
class ConfigTuningRun:
    """Complete config tuning run result."""
    run_id: str
    subsystem: str
    intent_data: Dict[str, Any]
    candidates_tested: List[CanaryResult]
    best_candidate: Optional[CanaryResult]
    promoted: bool
    promotion_path: Optional[str]
    status: str  # "success", "all_failed", "bounded_out", "rate_limited"
    duration_s: float
    timestamp: float


class ConfigTuningRunner:
    """Autonomous config tuning orchestrator."""

    def __init__(self, history_dir: Path = Path("/home/kloros/.kloros/self_heal")):
        """
        Args:
            history_dir: Directory for audit trail and rate limiting state
        """
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self.history_file = self.history_dir / "history.jsonl"
        self.state_file = self.history_dir / "state.json"

        # Load state (for rate limiting)
        self._load_state()

    def _load_state(self):
        """Load runner state from disk."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                self.state = json.load(f)
        else:
            self.state = {
                "last_run_by_subsystem": {},  # subsystem -> timestamp
                "runs_in_window": {}  # subsystem -> list of timestamps
            }

    def _save_state(self):
        """Save runner state to disk."""
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _check_rate_limit(self, subsystem: str) -> tuple[bool, str]:
        """
        Check if we're within rate limits for this subsystem.

        Rate limits:
        - Max 3 runs per 24 hours per subsystem
        - Min 6h cooldown between runs

        Returns:
            (allowed, reason)
        """
        now = time.time()
        window_24h = now - (24 * 3600)
        cooldown_6h = now - (6 * 3600)

        # Clean old runs from window
        if subsystem in self.state["runs_in_window"]:
            self.state["runs_in_window"][subsystem] = [
                ts for ts in self.state["runs_in_window"][subsystem]
                if ts >= window_24h
            ]
        else:
            self.state["runs_in_window"][subsystem] = []

        # Check 24h window limit
        runs_in_window = len(self.state["runs_in_window"][subsystem])
        if runs_in_window >= 3:
            return False, f"Rate limit: {runs_in_window} runs in last 24h (max 3)"

        # Check 6h cooldown
        last_run = self.state["last_run_by_subsystem"].get(subsystem, 0)
        if last_run >= cooldown_6h:
            time_since = now - last_run
            return False, f"Cooldown: last run {time_since/3600:.1f}h ago (min 6h)"

        return True, "OK"

    def _record_run(self, subsystem: str):
        """Record a run for rate limiting."""
        now = time.time()
        self.state["last_run_by_subsystem"][subsystem] = now

        if subsystem not in self.state["runs_in_window"]:
            self.state["runs_in_window"][subsystem] = []
        self.state["runs_in_window"][subsystem].append(now)

        self._save_state()

    def _log_to_history(self, run: ConfigTuningRun):
        """Append run to audit history."""
        with open(self.history_file, 'a') as f:
            f.write(json.dumps(asdict(run)) + '\n')

    def _test_candidate_with_spica(self, candidate: Dict[str, float]) -> CanaryResult:
        """
        Test a candidate configuration using isolated SPICA instance.

        This spawns an ephemeral SPICA filesystem clone, applies the candidate
        config, runs tests in complete isolation, then destroys the instance.

        Args:
            candidate: Parameter dict (e.g., {"vllm.gpu_memory_utilization": 0.80})

        Returns:
            CanaryResult with fitness score
        """
        start_time = time.time()
        candidate_id = hashlib.sha256(
            json.dumps(candidate, sort_keys=True).encode()
        ).hexdigest()[:16]

        # Validate candidate
        valid, error = validate_candidate(candidate)
        if not valid:
            logger.error(f"Candidate validation failed: {error}")
            return CanaryResult(
                candidate_id=candidate_id,
                candidate=candidate,
                status="invalid",
                fitness=0.0,
                metrics={"validation_error": error},
                test_duration_s=time.time() - start_time,
                timestamp=time.time()
            )

        # Import SPICA spawner
        try:
            import sys
            sys.path.insert(0, '/home/kloros')
            from src.dream.config_tuning.spica_spawner import spawn_instance, run_test_in_instance
        except ImportError as e:
            logger.error(f"Failed to import SPICA spawner: {e}")
            return CanaryResult(
                candidate_id=candidate_id,
                candidate=candidate,
                status="fail",
                fitness=0.0,
                metrics={"import_error": str(e)},
                test_duration_s=time.time() - start_time,
                timestamp=time.time()
            )

        # Spawn isolated SPICA instance
        logger.info(f"Spawning SPICA instance for candidate {candidate_id}")
        try:
            instance = spawn_instance(
                candidate=candidate,
                notes=f"ConfigTuning VLLM OOM fix - candidate {candidate_id}"
            )
        except Exception as e:
            logger.error(f"Failed to spawn SPICA instance: {e}")
            return CanaryResult(
                candidate_id=candidate_id,
                candidate=candidate,
                status="fail",
                fitness=0.0,
                metrics={"spawn_error": str(e)},
                test_duration_s=time.time() - start_time,
                timestamp=time.time()
            )

        # Create test script to run inside SPICA instance
        test_script = f"""
import sys
import json
import time
sys.path.insert(0, '/home/kloros')

from src.phase.domains.spica_gpu_allocation import SpicaGPUAllocation, GPUAllocationTestConfig

# Create SPICA evaluator with test config
test_config = GPUAllocationTestConfig(
    vllm_memory_util_min=0.60,
    vllm_memory_util_max=0.90,
    whisper_models=["small"],
    test_duration_sec=15,
    max_oom_events=0
)

evaluator = SpicaGPUAllocation(test_config=test_config)

# Convert candidate to SPICA format
spica_candidate = {{
    "vllm_memory_util": {candidate.get("vllm.gpu_memory_utilization", 0.50)},
    "whisper_model_size": "small",
}}

# Run test
result = evaluator.run_test(spica_candidate)
fitness = evaluator.compute_fitness(result)

# Output results as JSON
output = {{
    "status": result.status,
    "oom_events": result.oom_events,
    "stt_latency_ms": result.stt_latency_ms,
    "llm_latency_ms": result.llm_latency_ms,
    "concurrent_capacity": result.concurrent_capacity,
    "fitness": fitness,
    "validation_passed": result.validation_passed,
    "validation_reason": result.validation_reason
}}

print("SPICA_RESULT_JSON:" + json.dumps(output))
"""

        # Run test in isolated instance
        logger.info(f"Running test in SPICA instance {instance.spica_id}")
        try:
            test_result = run_test_in_instance(
                instance=instance,
                test_script=test_script,
                timeout_sec=120  # 2 minute timeout
            )

            # Parse results from stdout
            if test_result["success"]:
                # Extract JSON result from stdout
                stdout = test_result["stdout"]
                if "SPICA_RESULT_JSON:" in stdout:
                    json_str = stdout.split("SPICA_RESULT_JSON:")[1].strip()
                    metrics = json.loads(json_str)

                    # Check hard pass gates
                    pass_gates = (
                        metrics.get("oom_events", 999) == 0 and
                        metrics.get("validation_passed", False) and
                        metrics.get("status") == "pass"
                    )

                    status = "pass" if pass_gates else "fail"
                    fitness = metrics.get("fitness", 0.0)

                    logger.info(f"Candidate {candidate_id} (SPICA {instance.spica_id}): status={status}, "
                               f"fitness={fitness:.3f}, validation={metrics.get('validation_passed')}, "
                               f"oom={metrics.get('oom_events')}")

                    return CanaryResult(
                        candidate_id=candidate_id,
                        candidate=candidate,
                        status=status,
                        fitness=fitness,
                        metrics=metrics,
                        test_duration_s=time.time() - start_time,
                        timestamp=time.time()
                    )
                else:
                    # No JSON result found in stdout
                    logger.error(f"No SPICA result found in stdout for {instance.spica_id}")
                    return CanaryResult(
                        candidate_id=candidate_id,
                        candidate=candidate,
                        status="fail",
                        fitness=0.0,
                        metrics={"error": "No SPICA result in output", "stdout": stdout[:500]},
                        test_duration_s=time.time() - start_time,
                        timestamp=time.time()
                    )
            else:
                # Test failed
                logger.error(f"Test failed in SPICA instance {instance.spica_id}: {test_result['stderr'][:500]}")
                return CanaryResult(
                    candidate_id=candidate_id,
                    candidate=candidate,
                    status="fail",
                    fitness=0.0,
                    metrics={
                        "test_failed": True,
                        "timeout": test_result.get("timeout", False),
                        "stderr": test_result["stderr"][:500]
                    },
                    test_duration_s=time.time() - start_time,
                    timestamp=time.time()
                )

        except Exception as e:
            logger.error(f"SPICA test failed for candidate {candidate_id}: {e}", exc_info=True)
            return CanaryResult(
                candidate_id=candidate_id,
                candidate=candidate,
                status="fail",
                fitness=0.0,
                metrics={"exception": str(e)},
                test_duration_s=time.time() - start_time,
                timestamp=time.time()
            )
        finally:
            # Always destroy SPICA instance after test
            try:
                logger.info(f"Destroying SPICA instance {instance.spica_id}")
                instance.destroy()
            except Exception as e:
                logger.warning(f"Failed to destroy SPICA instance {instance.spica_id}: {e}")

    def _write_promotion(self, result: CanaryResult, subsystem: str, context: Dict[str, Any]) -> str:
        """
        Write promotion artifact for successful candidate.

        Promotions go to /home/kloros/out/promotions/ with schema config_tuning.v1

        Args:
            result: Passing canary result
            subsystem: Subsystem name (vllm, whisper, etc.)
            context: Original error context

        Returns:
            Path to promotion file
        """
        promotions_dir = Path("/home/kloros/out/promotions")
        promotions_dir.mkdir(parents=True, exist_ok=True)

        promotion_id = f"config_tuning_{subsystem}_{uuid.uuid4().hex[:8]}"
        promotion_file = promotions_dir / f"{promotion_id}.json"

        promotion = {
            "schema": "config_tuning.v1",
            "promotion_id": promotion_id,
            "origin": "self_heal",
            "subsystem": subsystem,
            "candidate": result.candidate,
            "fitness": result.fitness,
            "metrics": result.metrics,
            "context": context,
            "bounds_checked": True,
            "timestamp": datetime.now().isoformat(),
            "generated_at": time.time()
        }

        with open(promotion_file, 'w') as f:
            json.dump(promotion, f, indent=2)

        logger.info(f"Promotion written: {promotion_file}")
        return str(promotion_file)

    def run(self, intent_data: Dict[str, Any]) -> ConfigTuningRun:
        """
        Execute config tuning run from Observer intent.

        Args:
            intent_data: Intent payload with mode, subsystem, seed_fix, context

        Returns:
            ConfigTuningRun result
        """
        run_id = f"config_tuning_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        subsystem = intent_data.get("subsystem", "unknown")
        seed_fix = intent_data.get("seed_fix")
        context = intent_data.get("context", {})

        logger.info(f"Config tuning run {run_id} starting: subsystem={subsystem}, seed_fix={seed_fix}")

        # Check rate limits
        allowed, reason = self._check_rate_limit(subsystem)
        if not allowed:
            logger.warning(f"Config tuning rate limited for {subsystem}: {reason}")
            run = ConfigTuningRun(
                run_id=run_id,
                subsystem=subsystem,
                intent_data=intent_data,
                candidates_tested=[],
                best_candidate=None,
                promoted=False,
                promotion_path=None,
                status="rate_limited",
                duration_s=time.time() - start_time,
                timestamp=time.time()
            )
            self._log_to_history(run)
            return run

        # Generate candidates
        candidates = generate_candidates(
            seed_fix=seed_fix,
            subsystem=subsystem,
            context=context,
            max_candidates=6
        )

        if not candidates:
            logger.error(f"No candidates generated for {subsystem}")
            run = ConfigTuningRun(
                run_id=run_id,
                subsystem=subsystem,
                intent_data=intent_data,
                candidates_tested=[],
                best_candidate=None,
                promoted=False,
                promotion_path=None,
                status="no_candidates",
                duration_s=time.time() - start_time,
                timestamp=time.time()
            )
            self._log_to_history(run)
            return run

        logger.info(f"Generated {len(candidates)} candidates for testing")

        # Test candidates
        results = []
        for idx, candidate in enumerate(candidates):
            logger.info(f"Testing candidate {idx+1}/{len(candidates)}: {candidate}")
            result = self._test_candidate_with_spica(candidate)
            results.append(result)

            # Early exit: if first candidate (seed fix) passes, use it
            if idx == 0 and result.status == "pass":
                logger.info(f"Seed fix passed on first try (fitness={result.fitness:.3f}) - skipping tournament")
                break

            # Stop after 2 failures
            if len([r for r in results if r.status == "fail"]) >= 2:
                logger.info("Stopping after 2 failures (backoff)")
                break

        # Record run for rate limiting
        self._record_run(subsystem)

        # Find best passing candidate
        passing = [r for r in results if r.status == "pass"]

        if not passing:
            logger.warning(f"No passing candidates for {subsystem} (tested {len(results)})")
            run = ConfigTuningRun(
                run_id=run_id,
                subsystem=subsystem,
                intent_data=intent_data,
                candidates_tested=results,
                best_candidate=None,
                promoted=False,
                promotion_path=None,
                status="all_failed",
                duration_s=time.time() - start_time,
                timestamp=time.time()
            )
            self._log_to_history(run)
            return run

        # Select best by fitness
        best = max(passing, key=lambda r: r.fitness)
        logger.info(f"Best candidate: {best.candidate} (fitness={best.fitness:.3f})")

        # Write promotion
        promotion_path = self._write_promotion(best, subsystem, context)

        run = ConfigTuningRun(
            run_id=run_id,
            subsystem=subsystem,
            intent_data=intent_data,
            candidates_tested=results,
            best_candidate=best,
            promoted=True,
            promotion_path=promotion_path,
            status="success",
            duration_s=time.time() - start_time,
            timestamp=time.time()
        )

        self._log_to_history(run)
        logger.info(f"Config tuning run {run_id} complete: promoted {best.candidate_id}")

        return run
