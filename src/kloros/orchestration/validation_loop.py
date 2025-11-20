"""
Validation Loop - Tests deployments and provides learning feedback

Purpose:
    After deploying a D-REAM winner, validate that it actually improved
    the system. Rollback if it degraded performance. Feed results back
    to Curiosity for learning.

Workflow:
    1. Deployment happens (winner_deployer applies config)
    2. Run domain-specific tests (PHASE or targeted)
    3. Compare metrics before/after deployment
    4. Decide: keep (improvement) or rollback (regression)
    5. Update baseline metrics
    6. Feed success/failure back to Curiosity (learning loop closes)

This completes the autonomous learning loop:
    Observer → Curiosity → D-REAM → Deployment → 🔗 Validation → Learning
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class ValidationLoop:
    """
    Validates deployments and provides learning feedback.

    Purpose:
        Ensure deployed configurations actually improve the system
        and rollback if they degrade performance

    Design:
        - Stores baseline metrics before deployment
        - Runs domain tests after deployment
        - Compares metrics to baseline
        - Rolls back if regression detected
        - Feeds results to Curiosity for learning
    """

    def __init__(
        self,
        baseline_dir: Path = Path("/home/kloros/.kloros/baselines"),
        validation_log: Path = Path("/home/kloros/logs/orchestrator/validations.jsonl"),
        min_improvement: float = 0.02  # 2% minimum improvement to keep
    ):
        """
        Initialize validation loop.

        Parameters:
            baseline_dir: Directory to store baseline metrics
            validation_log: Log file for validation results
            min_improvement: Minimum improvement required (0.02 = 2%)
        """
        self.baseline_dir = baseline_dir
        self.validation_log = validation_log
        self.min_improvement = min_improvement

        # Create directories
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.validation_log.parent.mkdir(parents=True, exist_ok=True)

    def validate_deployment(
        self,
        deployment_id: str,
        experiment_name: str,
        domain: str,
        deployed_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate a deployment by running domain tests.

        Parameters:
            deployment_id: Unique deployment ID (hash)
            experiment_name: Name of the D-REAM experiment
            domain: Domain to test (e.g., "vllm", "tts", "conversation")
            deployed_params: Parameters that were deployed

        Returns:
            Dict with validation results
        """
        logger.info(f"[validation] Starting validation for {deployment_id} (domain={domain})")

        # 1. Get baseline metrics
        baseline = self._get_baseline_metrics(domain)

        if not baseline:
            logger.warning(f"[validation] No baseline for {domain}, creating initial baseline")
            # Run tests to establish baseline
            baseline = self._run_domain_tests(domain)
            if baseline:
                self._save_baseline(domain, baseline)
            else:
                return {
                    "status": "error",
                    "message": "Could not establish baseline",
                    "deployment_id": deployment_id
                }

        # 2. Run domain tests with new config
        new_metrics = self._run_domain_tests(domain)

        if not new_metrics:
            return {
                "status": "error",
                "message": "Domain tests failed",
                "deployment_id": deployment_id,
                "baseline": baseline
            }

        # 3. Compare metrics
        comparison = self._compare_metrics(baseline, new_metrics, domain)
        improvement = comparison["improvement_pct"]

        # 4. Decide: keep or rollback
        if improvement >= self.min_improvement:
            logger.info(f"[validation] ✅ Deployment {deployment_id} improved {domain} by {improvement:.1%}")
            self._update_baseline(domain, new_metrics)

            result = {
                "status": "success",
                "deployment_id": deployment_id,
                "experiment_name": experiment_name,
                "domain": domain,
                "improvement": improvement,
                "baseline_metrics": baseline,
                "new_metrics": new_metrics,
                "comparison": comparison,
                "action": "kept",
                "timestamp": datetime.now().isoformat()
            }

            # Feed success to Curiosity (future: trigger learning)
            self._feed_success_to_curiosity(experiment_name, improvement, deployed_params)

        elif improvement < -0.05:  # 5% degradation triggers rollback
            logger.warning(f"[validation] ❌ Deployment {deployment_id} degraded {domain} by {abs(improvement):.1%}, rolling back")
            self._rollback_deployment(deployment_id, deployed_params)

            result = {
                "status": "rollback",
                "deployment_id": deployment_id,
                "experiment_name": experiment_name,
                "domain": domain,
                "degradation": abs(improvement),
                "baseline_metrics": baseline,
                "new_metrics": new_metrics,
                "comparison": comparison,
                "action": "rolled_back",
                "timestamp": datetime.now().isoformat()
            }

            # Feed failure to Curiosity (future: avoid similar configs)
            self._feed_failure_to_curiosity(experiment_name, improvement, deployed_params)

        else:
            # Small change, not significant enough to keep or rollback
            logger.info(f"[validation] 🟡 Deployment {deployment_id} neutral change ({improvement:.1%}), keeping")

            result = {
                "status": "neutral",
                "deployment_id": deployment_id,
                "experiment_name": experiment_name,
                "domain": domain,
                "improvement": improvement,
                "baseline_metrics": baseline,
                "new_metrics": new_metrics,
                "comparison": comparison,
                "action": "kept",
                "timestamp": datetime.now().isoformat()
            }

        # Log validation result
        self._log_validation(result)

        return result

    def _get_baseline_metrics(self, domain: str) -> Optional[Dict[str, float]]:
        """Get baseline metrics for a domain."""
        baseline_file = self.baseline_dir / f"{domain}_baseline.json"

        if not baseline_file.exists():
            return None

        try:
            with open(baseline_file, 'r') as f:
                data = json.load(f)
            return data.get("metrics", {})
        except Exception as e:
            logger.error(f"[validation] Failed to load baseline for {domain}: {e}")
            return None

    def _save_baseline(self, domain: str, metrics: Dict[str, float]):
        """Save baseline metrics for a domain."""
        baseline_file = self.baseline_dir / f"{domain}_baseline.json"

        data = {
            "domain": domain,
            "metrics": metrics,
            "updated_at": datetime.now().isoformat()
        }

        try:
            with open(baseline_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"[validation] Saved baseline for {domain}: {metrics}")
        except Exception as e:
            logger.error(f"[validation] Failed to save baseline for {domain}: {e}")

    def _update_baseline(self, domain: str, new_metrics: Dict[str, float]):
        """Update baseline metrics after successful deployment."""
        self._save_baseline(domain, new_metrics)

    def _run_domain_tests(self, domain: str) -> Optional[Dict[str, float]]:
        """
        Run domain-specific tests.

        For now, returns mock metrics. In the future, this should:
        - Trigger PHASE for that specific domain
        - Or run targeted domain evaluator
        - Return actual metrics

        Parameters:
            domain: Domain to test

        Returns:
            Dict of metric_name → value
        """
        logger.info(f"[validation] Running domain tests for {domain}")

        # Domain-specific test commands (future implementation)
        test_commands = {
            "vllm": "python -m src.dream.domains.vllm_domain_evaluator",
            "tts": "python -m src.dream.domains.tts_domain_evaluator",
            "conversation": "python -m src.dream.domains.conversation_domain_evaluator",
            "rag": "python -m src.dream.domains.rag_context_domain_evaluator",
        }

        # For now, return mock metrics based on domain
        # TODO: Implement actual test execution
        mock_metrics = {
            "vllm": {"throughput": 45.2, "latency_p50": 120.5, "error_rate": 0.02},
            "tts": {"quality_mos": 4.1, "latency_ms": 85.3, "wer": 0.08},
            "conversation": {"intent_accuracy": 0.89, "response_quality": 4.2, "latency_ms": 1250},
            "rag": {"context_precision": 0.87, "context_recall": 0.91, "latency_ms": 245},
        }

        if domain in mock_metrics:
            logger.warning(f"[validation] Using mock metrics for {domain} (TODO: implement actual tests)")
            return mock_metrics[domain]

        logger.error(f"[validation] Unknown domain: {domain}")
        return None

    def _compare_metrics(
        self,
        baseline: Dict[str, float],
        new_metrics: Dict[str, float],
        domain: str
    ) -> Dict[str, Any]:
        """
        Compare baseline vs new metrics.

        Returns:
            Dict with comparison results and overall improvement %
        """
        # Define which metrics should increase vs decrease
        # TODO: Load from domain config
        metric_directions = {
            "throughput": "up",
            "quality_mos": "up",
            "intent_accuracy": "up",
            "response_quality": "up",
            "context_precision": "up",
            "context_recall": "up",
            "latency_p50": "down",
            "latency_ms": "down",
            "error_rate": "down",
            "wer": "down",
        }

        comparisons = {}
        improvements = []

        for metric_name in baseline.keys():
            if metric_name not in new_metrics:
                continue

            baseline_val = baseline[metric_name]
            new_val = new_metrics[metric_name]

            if baseline_val == 0:
                continue  # Avoid division by zero

            change_pct = (new_val - baseline_val) / baseline_val

            direction = metric_directions.get(metric_name, "up")
            if direction == "down":
                # For metrics where lower is better, invert the change
                change_pct = -change_pct

            comparisons[metric_name] = {
                "baseline": baseline_val,
                "new": new_val,
                "change_pct": change_pct,
                "direction": direction,
                "improved": change_pct > 0
            }

            improvements.append(change_pct)

        # Overall improvement is average of all metric improvements
        overall_improvement = sum(improvements) / len(improvements) if improvements else 0

        return {
            "metrics": comparisons,
            "improvement_pct": overall_improvement,
            "improved_count": sum(1 for c in comparisons.values() if c["improved"]),
            "total_count": len(comparisons)
        }

    def _rollback_deployment(self, deployment_id: str, deployed_params: Dict[str, Any]):
        """
        Rollback a deployment.

        For now, logs the rollback. In the future:
        - Restore previous .kloros_env
        - Restart affected services
        - Remove ACK file
        """
        logger.warning(f"[validation] Rolling back deployment {deployment_id}")
        logger.warning(f"[validation] Params to revert: {deployed_params}")

        # TODO: Implement actual rollback
        # 1. Load previous .kloros_env from backup
        # 2. Restore previous config
        # 3. Restart services if needed
        # 4. Remove ACK file

        logger.warning("[validation] TODO: Implement actual rollback mechanism")

    def _feed_success_to_curiosity(
        self,
        experiment_name: str,
        improvement: float,
        deployed_params: Dict[str, Any]
    ):
        """Feed successful deployment back to Curiosity for learning."""
        feedback_file = Path("/home/kloros/.kloros/curiosity_feedback.jsonl")
        feedback_file.parent.mkdir(parents=True, exist_ok=True)

        feedback = {
            "type": "deployment_success",
            "experiment": experiment_name,
            "improvement": improvement,
            "params": deployed_params,
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(feedback_file, 'a') as f:
                f.write(json.dumps(feedback) + '\n')
            logger.info(f"[validation] Fed success to Curiosity: {experiment_name} (+{improvement:.1%})")
        except Exception as e:
            logger.error(f"[validation] Failed to write curiosity feedback: {e}")

    def _feed_failure_to_curiosity(
        self,
        experiment_name: str,
        degradation: float,
        deployed_params: Dict[str, Any]
    ):
        """Feed failed deployment back to Curiosity for learning."""
        feedback_file = Path("/home/kloros/.kloros/curiosity_feedback.jsonl")
        feedback_file.parent.mkdir(parents=True, exist_ok=True)

        feedback = {
            "type": "deployment_failure",
            "experiment": experiment_name,
            "degradation": abs(degradation),
            "params": deployed_params,
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(feedback_file, 'a') as f:
                f.write(json.dumps(feedback) + '\n')
            logger.info(f"[validation] Fed failure to Curiosity: {experiment_name} ({degradation:.1%})")
        except Exception as e:
            logger.error(f"[validation] Failed to write curiosity feedback: {e}")

    def _log_validation(self, result: Dict[str, Any]):
        """Log validation result."""
        try:
            with open(self.validation_log, 'a') as f:
                f.write(json.dumps(result) + '\n')
        except Exception as e:
            logger.error(f"[validation] Failed to log validation: {e}")


def validate_deployment(
    deployment_id: str,
    experiment_name: str,
    domain: str,
    deployed_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate a deployment (called by winner_deployer).

    Parameters:
        deployment_id: Unique deployment ID
        experiment_name: D-REAM experiment name
        domain: Domain being tested
        deployed_params: Parameters that were deployed

    Returns:
        Validation result dict
    """
    validator = ValidationLoop()
    return validator.validate_deployment(
        deployment_id,
        experiment_name,
        domain,
        deployed_params
    )


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== Validation Loop Self-Test ===\n")

    validator = ValidationLoop()

    # Test validation with mock deployment
    result = validator.validate_deployment(
        deployment_id="test_12345678",
        experiment_name="vllm_config_tuning",
        domain="vllm",
        deployed_params={"context_length": 2048, "gpu_layers": 35}
    )

    print("\nValidation Result:")
    print(f"  Status: {result['status']}")
    print(f"  Action: {result['action']}")
    if 'improvement' in result:
        print(f"  Improvement: {result['improvement']:.1%}")
    if 'degradation' in result:
        print(f"  Degradation: {result['degradation']:.1%}")
