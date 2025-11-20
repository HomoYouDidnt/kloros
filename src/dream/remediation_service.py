"""
Remediation experiment generation and approval service.

Clean separation of concerns with single-responsibility components:
- RemediationExperimentGenerator: Generates experiments from questions
- ApprovalService: Handles approval workflow
- ExperimentInjector: Injects experiments into D-REAM config
"""
import json
import logging
from pathlib import Path
from typing import List, Set, Dict, Any, Optional

try:
    from .experiment_types import (
        BaseExperiment,
        RemediationExperiment,
        IntegrationFix
    )
    from .experiment_repository import ExperimentRepository, ApprovedExperimentsData
except ImportError:
    from experiment_types import (
        BaseExperiment,
        RemediationExperiment,
        IntegrationFix
    )
    from experiment_repository import ExperimentRepository, ApprovedExperimentsData
from datetime import datetime

logger = logging.getLogger(__name__)


class RemediationExperimentGenerator:
    """
    Generates remediation experiments from curiosity questions.

    Responsibilities:
    - Load curiosity feed
    - Generate typed experiments from questions
    - Filter by priority threshold
    """

    def __init__(
        self,
        feed_path: Path = Path("/home/kloros/.kloros/curiosity_feed.json")
    ):
        self.feed_path = feed_path

    def load_questions(self) -> List[Dict[str, Any]]:
        """
        Load curiosity questions from feed.

        Returns:
            List of question dicts

        Raises:
            FileNotFoundError: If feed file doesn't exist
            json.JSONDecodeError: If feed is corrupted
        """
        if not self.feed_path.exists():
            logger.warning(f"[remediation] Curiosity feed not found: {self.feed_path}")
            return []

        try:
            with open(self.feed_path, 'r') as f:
                feed = json.load(f)
            return feed.get("questions", [])
        except Exception as e:
            logger.error(f"[remediation] Failed to load feed: {e}")
            return []

    def generate_remediation_experiments(
        self,
        min_priority: float = 0.6
    ) -> List[BaseExperiment]:
        """
        Generate remediation experiments from high-priority questions.

        Args:
            min_priority: Minimum value_estimate threshold (0.0-1.0)

        Returns:
            List of typed experiments sorted by priority (highest first)
        """
        questions = self.load_questions()
        experiments: List[BaseExperiment] = []

        for question in questions:
            if question.get("value_estimate", 0) < min_priority:
                continue

            # Polymorphic generation
            exp = self.generate_from_question(question)
            if exp:
                experiments.append(exp)
                logger.info(
                    f"[remediation] Generated: {exp.get_name()} "
                    f"(priority={exp.get_priority():.2f}, "
                    f"runnable={exp.is_runnable()})"
                )

        # Type-safe sorting (no isinstance needed!)
        experiments.sort(key=lambda e: e.get_priority(), reverse=True)

        return experiments

    def generate_from_question(self, question: Dict[str, Any]) -> Optional[BaseExperiment]:
        """
        Factory method for question -> experiment conversion.

        Delegates to specialized generators based on question type.

        Args:
            question: Curiosity question dict

        Returns:
            Typed experiment or None if not applicable
        """
        hypothesis = question.get("hypothesis", "")

        # Performance degradation -> RemediationExperiment
        if hypothesis.endswith(("_DEGRADATION", "_REGRESSION")):
            return self.generate_from_performance_question(question)

        # Integration issues -> IntegrationFix
        if hypothesis.startswith(("ORPHANED_QUEUE_", "UNINITIALIZED_COMPONENT_", "DUPLICATE_")):
            return self.generate_from_integration_question(question)

        return None

    def generate_from_performance_question(
        self,
        question: Dict[str, Any]
    ) -> Optional[RemediationExperiment]:
        """
        Generate remediation experiment from performance question.

        (Implementation continues from original remediation_manager.py logic)
        """
        question_id = question.get("id", "unknown")
        hypothesis = question.get("hypothesis", "")

        # Extract experiment name from question_id
        if not question_id.startswith("performance."):
            return None

        parts = question_id.split(".")
        if len(parts) < 3:
            return None

        source_experiment = parts[1]
        degradation_type = parts[2]

        remediation_name = f"remediation_{source_experiment}_{degradation_type}"

        # Map to evaluator config (simplified - extend as needed)
        experiment_configs = {
            "spica_cognitive_variants": {
                "evaluator": {
                    "path": "/home/kloros/src/dream/evaluators/spica_tournament_evaluator.py",
                    "class": "SPICATournamentEvaluator",
                    "init_kwargs": {
                        "suite_id": "qa.rag.gold",
                        "qtime": {"epochs": 2, "slices_per_epoch": 4, "replicas_per_slice": 8}
                    }
                },
                "search_space": {
                    "tau_persona": [0.01, 0.02, 0.03, 0.05, 0.07],
                    "tau_task": [0.06, 0.08, 0.10, 0.12, 0.15],
                    "max_context_turns": [6, 8, 10, 12]
                },
                "metrics": {
                    "target_direction": {"exact_match_mean": "up", "latency_p50_ms": "down"},
                    "map": {"exact_match_mean": "quality", "latency_p50_ms": "latency"}
                }
            }
        }

        if source_experiment not in experiment_configs:
            logger.warning(f"[remediation] No template for experiment: {source_experiment}")
            return None

        exp_config = experiment_configs[source_experiment]
        value = question.get("value_estimate", 0.5)

        budget = {
            "wallclock_sec": 480,
            "max_candidates": 12,
            "max_generations": 4,
            "allow_gpu": False
        }

        return RemediationExperiment(
            name=remediation_name,
            question_id=question_id,
            hypothesis=hypothesis,
            search_space=exp_config["search_space"],
            evaluator=exp_config["evaluator"],
            budget=budget,
            metrics=exp_config["metrics"],
            priority=value
        )

    def generate_from_integration_question(
        self,
        question: Dict[str, Any]
    ) -> Optional[IntegrationFix]:
        """
        Generate fix specification from integration question.

        Args:
            question: Curiosity question dict

        Returns:
            IntegrationFix or None if not applicable
        """
        question_id = question.get("id", "unknown")
        hypothesis = question.get("hypothesis", "")

        # Handle integration issues
        if hypothesis.startswith("ORPHANED_QUEUE_"):
            return self._generate_add_consumer_fix(question)
        elif hypothesis.startswith("UNINITIALIZED_COMPONENT_"):
            return self._generate_null_check_fix(question)
        elif hypothesis.startswith("DUPLICATE_"):
            return self._generate_consolidation_report(question)

        return None

    def _generate_add_consumer_fix(self, question: Dict[str, Any]) -> IntegrationFix:
        """Generate fix spec for orphaned queue."""
        import re

        evidence = question.get("evidence", [])
        channel = question.get("id", "").replace("orphaned_queue_", "")

        producer_file = None
        for e in evidence:
            file_match = re.search(r"Produced in: (/[^\s]+\.py)", e)
            if file_match:
                producer_file = file_match.group(1)
                break

        if producer_file is None:
            logger.warning(
                f"[remediation] Could not extract producer file from evidence for {channel}"
            )

        return IntegrationFix(
            question_id=question.get("id"),
            fix_type="add_consumer",
            hypothesis=question.get("hypothesis"),
            action="add_consumer",
            params={
                "channel": channel,
                "producer_file": producer_file,
                "evidence": evidence,
                "autonomy": question.get("autonomy", 2)
            },
            value_estimate=question.get("value_estimate", 0.9),
            cost=question.get("cost", 0.3)
        )

    def _generate_null_check_fix(self, question: Dict[str, Any]) -> IntegrationFix:
        """Generate fix spec for uninitialized component."""
        import re

        evidence = question.get("evidence", [])
        component = question.get("id", "").replace("missing_wiring_", "")
        question_text = question.get("question", "")

        file_match = re.search(r"in (/[^\s]+\.py)", question_text)
        file_path = file_match.group(1) if file_match else None

        if file_path is None:
            logger.warning(
                f"[remediation] Could not extract file path from question for {component}"
            )

        usage_line = None
        for e in evidence:
            line_match = re.search(r"line (\d+)", e)
            if line_match:
                usage_line = int(line_match.group(1))
                break

        if usage_line is None:
            logger.warning(
                f"[remediation] Could not extract line number from evidence for {component}"
            )

        check_code = f"if hasattr(self, '{component}') and self.{component}:"

        return IntegrationFix(
            question_id=question.get("id"),
            fix_type="add_null_check",
            hypothesis=question.get("hypothesis"),
            action="add_null_check",
            params={
                "file": file_path,
                "component": component,
                "usage_line": usage_line,
                "check_code": check_code,
                "evidence": evidence,
                "autonomy": question.get("autonomy", 2)
            },
            value_estimate=question.get("value_estimate", 0.8),
            cost=question.get("cost", 0.2)
        )

    def _generate_consolidation_report(self, question: Dict[str, Any]) -> IntegrationFix:
        """Generate documentation for duplicate components."""
        return IntegrationFix(
            question_id=question.get("id"),
            fix_type="consolidate_duplicates",
            hypothesis=question.get("hypothesis"),
            action="consolidate_duplicates",
            params={
                "evidence": question.get("evidence", []),
                "autonomy": 2
            },
            value_estimate=question.get("value_estimate", 0.7),
            cost=question.get("cost", 0.5)
        )


class ApprovalService:
    """
    Handles user approval workflow for remediation experiments.

    Responsibilities:
    - Check autonomy level
    - Request manual approval if needed
    - Track approved experiment IDs
    - Persist approvals
    """

    def __init__(self, repository: ExperimentRepository):
        self.repository = repository

    def get_experiments_to_approve(
        self,
        proposed: List[BaseExperiment],
        autonomy_level: int
    ) -> List[BaseExperiment]:
        """
        Determine which experiments need approval.

        Args:
            proposed: Newly generated experiments
            autonomy_level: System autonomy setting (0-3)

        Returns:
            List of experiments requiring approval
        """
        if autonomy_level >= 2:
            logger.info(
                f"[approval] Auto-approved {len(proposed)} experiments "
                f"(autonomy={autonomy_level})"
            )
            return proposed

        # Load already-approved to avoid re-prompting
        saved_data = self.repository.load()
        approved_ids: Set[str] = {
            exp.get_question_id() for exp in saved_data.experiments
        }

        # Filter to new experiments only
        new_experiments = [
            exp for exp in proposed
            if exp.get_question_id() not in approved_ids
        ]

        if not new_experiments:
            logger.info("[approval] All experiments previously approved")
            return saved_data.experiments

        # Request manual approval
        approved_new = self._request_user_approval(new_experiments)
        combined = saved_data.experiments + approved_new

        # Persist approved list
        if approved_new:
            self.repository.save(ApprovedExperimentsData(
                experiments=combined,
                approved_at=datetime.now().isoformat()
            ))

        return combined

    def _request_user_approval(
        self,
        experiments: List[BaseExperiment]
    ) -> List[BaseExperiment]:
        """
        Interactive approval prompt with timeout.

        Displays experiment details and waits for user confirmation.
        Auto-rejects if no response within timeout period.
        """
        import signal
        import os

        print("\n" + "="*60)
        print("🔬 D-REAM AUTONOMOUS REMEDIATION PROPOSAL")
        print("="*60)
        print(f"\nDetected {len(experiments)} performance issues. "
              f"Proposed remediation experiments:\n")

        for i, exp in enumerate(experiments, 1):
            print(f"{i}. {exp.get_name()}")
            print(f"   Priority: {exp.get_priority():.2f}")
            print(f"   Runnable: {'Yes' if exp.is_runnable() else 'No (manual fix)'}")

            # Type-specific details
            if isinstance(exp, RemediationExperiment):
                print(f"   Hypothesis: {exp.hypothesis}")
                print(f"   Budget: {exp.budget['max_candidates']} candidates × "
                      f"{exp.budget['max_generations']} generations")
            elif isinstance(exp, IntegrationFix):
                print(f"   Fix Type: {exp.fix_type}")
                print(f"   Action: {exp.action}")
            print()

        def timeout_handler(signum, frame):
            raise TimeoutError("User approval timeout")

        timeout_seconds = int(os.environ.get("REMEDIATION_APPROVAL_TIMEOUT", "300"))

        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

            try:
                response = input(
                    f"Approve all remediation experiments? [Y/n] "
                    f"({timeout_seconds}s timeout): "
                ).strip().lower()

                signal.alarm(0)

                if response in ("", "y", "yes"):
                    print(f"\n✅ Approved {len(experiments)} remediation experiments")
                    return experiments
                else:
                    print("\n❌ Remediation experiments rejected")
                    return []

            except TimeoutError:
                print(f"\n⏱️ Approval timeout ({timeout_seconds}s) - defaulting to reject")
                logger.warning(
                    f"[approval] User approval timed out after {timeout_seconds}s, rejecting"
                )
                return []
            finally:
                signal.alarm(0)

        except (EOFError, KeyboardInterrupt):
            print("\n❌ User approval interrupted")
            return []


class ExperimentInjector:
    """
    Injects approved experiments into D-REAM configuration.

    Responsibilities:
    - Filter runnable vs non-runnable experiments
    - Merge with existing config
    - Validate experiment structure
    """

    @staticmethod
    def inject_experiments(
        config: Dict[str, Any],
        approved: List[BaseExperiment]
    ) -> Dict[str, Any]:
        """
        Inject approved experiments into D-REAM config.

        Only runnable experiments are injected. Integration fixes are
        logged but skipped since they require manual implementation.

        Args:
            config: Base D-REAM configuration
            approved: List of approved experiments

        Returns:
            Modified configuration with experiments injected
        """
        import copy

        config_copy = copy.deepcopy(config)
        experiments = config_copy.get("experiments", [])

        # Remove old remediation experiments from previous cycles
        experiments = [e for e in experiments if not e.get("_remediation")]

        # Inject only runnable experiments
        runnable_count = 0
        skipped_count = 0

        for exp in approved:
            if exp.is_runnable():
                if isinstance(exp, RemediationExperiment):
                    experiments.append(exp.to_dream_config())
                runnable_count += 1
            else:
                logger.info(
                    f"[injection] Skipping non-runnable experiment: {exp.get_name()} "
                    f"({type(exp).__name__})"
                )
                skipped_count += 1

        config_copy["experiments"] = experiments

        logger.info(
            f"[injection] Injected {runnable_count}/{len(approved)} experiments "
            f"({skipped_count} manual fixes skipped)"
        )

        return config_copy
