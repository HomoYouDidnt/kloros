"""
D-REAM Autonomous Remediation Manager

Purpose:
    Converts curiosity questions into remediation experiments that
    automatically diagnose and fix performance degradation

Workflow:
    1. Read curiosity_feed.json for performance/resource issues
    2. Generate remediation experiment configs
    3. Request user approval (autonomy level 2)
    4. Inject approved experiments into D-REAM runner

KPIs:
    - Question → Experiment conversion rate
    - Remediation success rate (did performance improve?)
    - Time to remediation (detection → fix)
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RemediationExperiment:
    """
    A remediation experiment generated from a curiosity question.

    Attributes:
        name: Unique experiment name
        question_id: Source curiosity question ID
        hypothesis: What we're testing
        search_space: Parameters to explore
        evaluator: Which evaluator to use
        budget: Resource constraints
        metrics: What to measure
        priority: Urgency (0.0-1.0, higher = more urgent)
    """
    name: str
    question_id: str
    hypothesis: str
    search_space: Dict[str, List[Any]]
    evaluator: Dict[str, Any]
    budget: Dict[str, Any]
    metrics: Dict[str, Any]
    priority: float
    created_at: str = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dream_config(self) -> Dict[str, Any]:
        """
        Convert to D-REAM experiment config format.

        Returns:
            Dict compatible with dream.yaml experiments list
        """
        return {
            "name": self.name,
            "enabled": True,
            "template": None,  # Direct evaluator, no template
            "search_space": self.search_space,
            "evaluator": self.evaluator,
            "budget": self.budget,
            "metrics": self.metrics,
            "selector": {
                "kind": "rzero",
                "tournament_size": 4,
                "survivors": 2,
                "elitism": 1,
                "fresh_inject": 1
            },
            "convergence": {
                "patience_gens": 2  # Early stop if no improvement
            },
            "_remediation": {
                "question_id": self.question_id,
                "hypothesis": self.hypothesis,
                "priority": self.priority,
                "created_at": self.created_at
            }
        }


class RemediationExperimentGenerator:
    """
    Generates remediation experiments from curiosity questions.

    Purpose:
        Auto-generate targeted experiments to fix detected performance
        degradation or resource issues

    Strategy:
        - Performance questions → parameter tuning experiments
        - Resource questions → resource optimization experiments
        - Capability questions → not auto-remediated (manual fixes)
    """

    def __init__(
        self,
        feed_path: Path = Path("/home/kloros/.kloros/curiosity_feed.json"),
        approved_path: Path = Path("/home/kloros/.kloros/remediation_approved.json")
    ):
        """
        Initialize remediation generator.

        Parameters:
            feed_path: Path to curiosity_feed.json
            approved_path: Path to store approved remediation experiments
        """
        self.feed_path = feed_path
        self.approved_path = approved_path

    def load_questions(self) -> List[Dict[str, Any]]:
        """
        Load curiosity questions from feed.

        Returns:
            List of question dicts
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

    def generate_from_integration_question(
        self,
        question: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate fix specification from integration question.

        Parameters:
            question: Curiosity question dict

        Returns:
            Fix specification dict or None if not applicable
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

    def _generate_add_consumer_fix(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate fix spec for orphaned queue.

        Note: Orphaned queues are complex - requires architectural analysis to determine
        where consumer should be added. Respects question's autonomy level.
        """
        import re

        evidence = question.get("evidence", [])
        channel = question.get("id", "").replace("orphaned_queue_", "")

        # Parse producer file from evidence: "Produced in: /path/to/file.py"
        producer_file = None
        for e in evidence:
            file_match = re.search(r"Produced in: (/[^\s]+\.py)", e)
            if file_match:
                producer_file = file_match.group(1)
                break

        # For orphaned queues, we need architectural context to know WHERE to add consumer
        # Respect the question's original autonomy level - let system settings determine behavior
        return {
            "fix_type": "consolidate_duplicates",
            "question_id": question.get("id"),
            "hypothesis": question.get("hypothesis"),
            "action": "consolidate_duplicates",
            "params": {
                "channel": channel,
                "producer_file": producer_file,
                "evidence": evidence,
                "autonomy": question.get("autonomy", 2)
            },
            "value_estimate": question.get("value_estimate", 0.9),
            "cost": question.get("cost", 0.3)
        }

    def _generate_null_check_fix(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fix spec for uninitialized component."""
        import re

        evidence = question.get("evidence", [])
        component = question.get("id", "").replace("missing_wiring_", "")
        question_text = question.get("question", "")

        # Parse file path from question: "Component 'X' is used in /path/to/file.py"
        file_match = re.search(r"in (/[^\s]+\.py)", question_text)
        file_path = file_match.group(1) if file_match else None

        # Parse usage line from evidence: "Used at line 2680"
        usage_line = None
        for e in evidence:
            line_match = re.search(r"line (\d+)", e)
            if line_match:
                usage_line = int(line_match.group(1))
                break

        # Generate null check code
        check_code = f"if hasattr(self, '{component}') and self.{component}:"

        return {
            "fix_type": "add_null_check",
            "question_id": question.get("id"),
            "hypothesis": question.get("hypothesis"),
            "action": "add_null_check",
            "params": {
                "file": file_path,
                "component": component,
                "usage_line": usage_line,
                "check_code": check_code,
                "evidence": evidence,
                "autonomy": question.get("autonomy", 2)
            },
            "value_estimate": question.get("value_estimate", 0.8),
            "cost": question.get("cost", 0.2)
        }

    def _generate_consolidation_report(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """Generate documentation for duplicate components."""
        return {
            "fix_type": "consolidate_duplicates",
            "question_id": question.get("id"),
            "hypothesis": question.get("hypothesis"),
            "action": "consolidate_duplicates",
            "params": {
                "evidence": question.get("evidence", []),
                "autonomy": 2  # Always requires manual review
            },
            "value_estimate": question.get("value_estimate", 0.7),
            "cost": question.get("cost", 0.5)
        }

    def generate_from_performance_question(
        self,
        question: Dict[str, Any]
    ) -> Optional[RemediationExperiment]:
        """
        Generate remediation experiment from performance question.

        Parameters:
            question: Curiosity question dict

        Returns:
            RemediationExperiment or None if not applicable
        """
        question_id = question.get("id", "unknown")
        hypothesis = question.get("hypothesis", "")

        # Only handle performance degradation questions
        if not hypothesis.endswith("_DEGRADATION") and not hypothesis.endswith("_REGRESSION"):
            # Check if it's an integration question
            integration_fix = self.generate_from_integration_question(question)
            if integration_fix:
                return integration_fix
            return None

        # Extract experiment name and degradation type from question_id
        # Format: "performance.{experiment}.{degradation_type}"
        if not question_id.startswith("performance."):
            return None

        parts = question_id.split(".")
        if len(parts) < 3:
            return None

        source_experiment = parts[1]  # e.g., "spica_cognitive_variants"
        degradation_type = parts[2]   # e.g., "pass_rate_drop"

        # Extract current params from evidence
        evidence = question.get("evidence", [])
        current_params = {}
        for e in evidence:
            if e.startswith("params:"):
                param_str = e.split(":", 1)[1]
                # Parse comma-separated params
                for param in param_str.split(","):
                    if param:
                        current_params[param.strip()] = "current"

        # Generate remediation name
        remediation_name = f"remediation_{source_experiment}_{degradation_type}"

        # Map experiment to evaluator and search space
        experiment_configs = {
            "spica_cognitive_variants": {
                "evaluator": {
                    "path": "/home/kloros/src/dream/evaluators/spica_tournament_evaluator.py",
                    "class": "SPICATournamentEvaluator",
                    "init_kwargs": {
                        "suite_id": "qa.rag.gold",
                        "qtime": {
                            "epochs": 2,
                            "slices_per_epoch": 4,
                            "replicas_per_slice": 8
                        }
                    }
                },
                "search_space": {
                    "tau_persona": [0.01, 0.02, 0.03, 0.05, 0.07],
                    "tau_task": [0.06, 0.08, 0.10, 0.12, 0.15],
                    "max_context_turns": [6, 8, 10, 12]
                },
                "metrics": {
                    "target_direction": {
                        "exact_match_mean": "up",
                        "latency_p50_ms": "down"
                    },
                    "map": {
                        "exact_match_mean": "quality",
                        "latency_p50_ms": "latency"
                    }
                }
            },
            "audio_latency_trim": {
                "evaluator": {
                    "path": "/home/kloros/src/dream/domains/audio_domain_evaluator.py",
                    "class": "AudioDomainEvaluator",
                    "init_kwargs": {}
                },
                "search_space": {
                    "sample_rates": [16000, 22050, 24000],
                    "frame_sizes": [256, 320, 512, 640],
                    "buffering_strategy": ["double", "triple"],
                    "resampler": ["soxr", "speex"]
                },
                "metrics": {
                    "target_direction": {
                        "end_to_end_latency_ms_p95": "down",
                        "underrun_count": "down",
                        "cpu_percent": "down"
                    },
                    "map": {
                        "end_to_end_latency_ms_p95": "latency",
                        "underrun_count": "quality",
                        "cpu_percent": "throughput"
                    }
                }
            },
            "conv_quality_tune": {
                "evaluator": {
                    "path": "/home/kloros/src/dream/domains/conversation_domain_evaluator.py",
                    "class": "ConversationDomainEvaluator",
                    "init_kwargs": {}
                },
                "search_space": {
                    "max_context_turns": [6, 8, 10, 12, 14],
                    "response_length_tokens": [160, 220, 280, 320],
                    "anti_hallucination_mode": ["off", "light", "strict"],
                    "cite_threshold": [0.55, 0.65, 0.75, 0.85]
                },
                "metrics": {
                    "target_direction": {
                        "helpfulness": "up",
                        "faithfulness": "up",
                        "latency_ms_p50": "down"
                    },
                    "map": {
                        "helpfulness": "quality",
                        "faithfulness": "quality",
                        "latency_ms_p50": "latency"
                    }
                }
            },
            "rag_opt_baseline": {
                "evaluator": {
                    "path": "/home/kloros/src/dream/domains/rag_context_domain_evaluator.py",
                    "class": "RAGContextDomainEvaluator",
                    "init_kwargs": {}
                },
                "search_space": {
                    "top_k_values": [3, 5, 7, 10, 12],
                    "chunk_sizes": [256, 512, 768, 1024, 1280],
                    "similarity_thresholds": [0.55, 0.65, 0.75, 0.85],
                    "embedder": ["bge-small", "e5-base-v2"]
                },
                "metrics": {
                    "target_direction": {
                        "context_recall": "up",
                        "context_precision": "up",
                        "response_latency_ms": "down",
                        "hallucination_rate": "down"
                    },
                    "map": {
                        "context_precision": "quality",
                        "response_latency_ms": "latency",
                        "context_recall": "throughput"
                    }
                }
            }
        }

        # Get config for this experiment
        if source_experiment not in experiment_configs:
            logger.warning(f"[remediation] No template for experiment: {source_experiment}")
            return None

        exp_config = experiment_configs[source_experiment]

        # Set budget based on degradation urgency
        value = question.get("value_estimate", 0.5)
        budget = {
            "wallclock_sec": 480,  # 8 minutes per candidate
            "max_candidates": 12,
            "max_generations": 4,
            "allow_gpu": False  # Keep GPU free for live system
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

    def generate_remediation_experiments(
        self,
        min_priority: float = 0.6
    ) -> List[RemediationExperiment]:
        """
        Generate remediation experiments from all applicable questions.

        Parameters:
            min_priority: Minimum value_estimate to trigger remediation

        Returns:
            List of RemediationExperiment objects
        """
        questions = self.load_questions()
        experiments = []

        for question in questions:
            # Only generate for high-priority performance questions
            if question.get("value_estimate", 0) < min_priority:
                continue

            # Try performance question
            exp = self.generate_from_performance_question(question)
            if exp:
                experiments.append(exp)
                if isinstance(exp, dict):
                    name = exp.get('question_id', 'unknown')
                    priority = exp.get('value_estimate', 0.0)
                    logger.info(f"[remediation] Generated: {name} (priority={priority:.2f})")
                else:
                    logger.info(f"[remediation] Generated: {exp.name} (priority={exp.priority:.2f})")

        # Sort by priority (highest first)
        experiments.sort(key=lambda e: e.get('value_estimate', 0.0) if isinstance(e, dict) else e.priority, reverse=True)

        return experiments

    def save_approved_experiments(self, experiments: List[RemediationExperiment]):
        """
        Save approved remediation experiments to file.

        Parameters:
            experiments: List of approved experiments (can be mix of objects and dicts)
        """
        exp_list = []
        for e in experiments:
            if isinstance(e, dict):
                exp_list.append(e)
            else:
                exp_list.append(asdict(e))

        data = {
            "experiments": exp_list,
            "approved_at": datetime.now().isoformat()
        }

        with open(self.approved_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"[remediation] Saved {len(experiments)} approved experiments to {self.approved_path}")

    def load_approved_experiments(self) -> List[RemediationExperiment]:
        """
        Load approved remediation experiments from file.

        Returns:
            List of RemediationExperiment objects (or dicts for integration fixes)
        """
        if not self.approved_path.exists():
            return []

        try:
            with open(self.approved_path, 'r') as f:
                data = json.load(f)

            experiments = []
            for exp_data in data.get("experiments", []):
                if 'fix_type' in exp_data or 'action' in exp_data:
                    experiments.append(exp_data)
                else:
                    experiments.append(RemediationExperiment(**exp_data))

            return experiments
        except Exception as e:
            logger.error(f"[remediation] Failed to load approved experiments: {e}")
            return []


def request_user_approval(
    experiments: List[RemediationExperiment],
    autonomy_level: int = 2
) -> List[RemediationExperiment]:
    """
    Request user approval for remediation experiments.

    Parameters:
        experiments: List of proposed experiments
        autonomy_level: Current autonomy level (2+ = auto-approve low-risk experiments)

    Returns:
        List of approved experiments
    """
    if autonomy_level >= 2:
        # Auto-approve at autonomy level 2+ (Nov 1, 2025: Changed from 3 to enable autonomy)
        logger.info(f"[remediation] Auto-approved {len(experiments)} experiments (autonomy={autonomy_level})")
        return experiments

    if not experiments:
        return []

    print("\n" + "="*60)
    print("🔬 D-REAM AUTONOMOUS REMEDIATION PROPOSAL")
    print("="*60)
    print(f"\nDetected {len(experiments)} performance issues. Proposed remediation experiments:\n")

    for i, exp in enumerate(experiments, 1):
        if isinstance(exp, dict):
            name = exp.get('question_id', 'unknown')
            hypothesis = exp.get('hypothesis', 'N/A')
            priority = exp.get('value_estimate', 0.0)
            budget = exp.get('params', {})
            print(f"{i}. {name}")
            print(f"   Hypothesis: {hypothesis}")
            print(f"   Priority: {priority:.2f}")
            print(f"   Type: Integration fix")
            print()
        else:
            print(f"{i}. {exp.name}")
            print(f"   Hypothesis: {exp.hypothesis}")
            print(f"   Priority: {exp.priority:.2f}")
            print(f"   Budget: {exp.budget['max_candidates']} candidates × {exp.budget['max_generations']} generations")
            print(f"   Estimated time: {exp.budget['wallclock_sec'] * exp.budget['max_candidates'] / 60:.1f} minutes")
            print()

    print("These experiments will run autonomously to diagnose and fix performance degradation.")
    print(f"Autonomy level: {autonomy_level} (level 0-1: manual approval required)")
    print()

    try:
        response = input("Approve all remediation experiments? [Y/n]: ").strip().lower()
        if response in ("", "y", "yes"):
            print(f"\n✅ Approved {len(experiments)} remediation experiments")
            return experiments
        else:
            print("\n❌ Remediation experiments rejected")
            return []
    except (EOFError, KeyboardInterrupt):
        print("\n❌ User approval interrupted")
        return []


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(level=logging.INFO)

    generator = RemediationExperimentGenerator()

    print("=== Remediation Experiment Generator Self-Test ===\n")

    # Load questions
    questions = generator.load_questions()
    print(f"Loaded {len(questions)} curiosity questions")

    # Generate remediation experiments
    experiments = generator.generate_remediation_experiments(min_priority=0.6)
    print(f"\nGenerated {len(experiments)} remediation experiments:\n")

    for exp in experiments:
        print(f"  - {exp.name} (priority={exp.priority:.2f})")
        print(f"    Search space: {list(exp.search_space.keys())}")
        print()

    if experiments:
        print("Sample experiment config:")
        print(json.dumps(experiments[0].to_dream_config(), indent=2))
