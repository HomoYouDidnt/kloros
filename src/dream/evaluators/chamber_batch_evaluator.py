#!/usr/bin/env python3
"""
Chamber Batch Evaluator - Adapts SPICA domain evaluators to tournament interface.

Wraps single-candidate SPICA evaluators (SpicaConversation, SpicaRepairLab, etc.)
to provide batch tournament evaluation with bracket-style fitness scoring.
"""

import logging
from typing import Dict, Any, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ChamberBatchEvaluator:
    """
    Adapter that wraps SPICA domain evaluators for batch tournament evaluation.

    Takes a chamber evaluator class (e.g., SpicaConversation) and provides
    batch evaluation with tournament-style fitness scoring.
    """

    def __init__(self, evaluator_class, init_kwargs: Dict[str, Any] = None):
        """
        Initialize batch evaluator wrapper.

        Args:
            evaluator_class: SPICA domain class (e.g., SpicaConversation)
            init_kwargs: Kwargs to pass to evaluator constructor
        """
        self.evaluator_class = evaluator_class
        self.init_kwargs = init_kwargs or {}
        logger.info(f"[chamber_batch] Initialized batch evaluator for {evaluator_class.__name__}")

    def evaluate_batch(self, candidates: List[Dict[str, Any]], context: Dict[str, Any] = None) -> Tuple[List[float], Dict[str, Any]]:
        """
        Evaluate multiple candidates and return tournament-style fitness scores.

        Args:
            candidates: List of parameter dicts
            context: Tournament context

        Returns:
            Tuple of (fitnesses, artifacts)
        """
        if context is None:
            context = {}

        logger.info(f"[chamber_batch] Evaluating {len(candidates)} candidates")

        # Track results for each candidate
        results = []
        fitnesses = []
        judge_unavailable = False

        # Evaluate each candidate independently
        for i, candidate in enumerate(candidates):
            try:
                # Create fresh evaluator instance with candidate params
                evaluator_init_kwargs = self.init_kwargs.copy()

                # Merge candidate params into init kwargs if evaluator accepts them
                # (Some evaluators like SpicaConversation take test_config)
                candidate_clean = {k: v for k, v in candidate.items() if k != "name"}

                # Create evaluator instance
                evaluator = self.evaluator_class(**evaluator_init_kwargs)

                # Prepare test input (chamber-specific)
                test_input = self._prepare_test_input(candidate, context)

                # Run evaluation
                result = evaluator.evaluate(test_input, context)

                # Check if judge unavailable - if so, queue entire batch
                if result.get("status") == "judge_unavailable":
                    judge_unavailable = True
                    logger.warning("[chamber_batch] Judge unavailable - queuing progression")
                    break

                # Extract fitness
                fitness = result.get("fitness", 0.0)

                logger.info(
                    f"[chamber_batch] Candidate {i} ({candidate.get('name', 'unnamed')}): "
                    f"fitness={fitness:.3f}, status={result.get('status', 'unknown')}"
                )

                results.append(result)
                fitnesses.append(fitness)

            except Exception as e:
                logger.error(f"[chamber_batch] Evaluation failed for candidate {i}: {e}", exc_info=True)
                results.append({
                    "fitness": 0.0,
                    "status": "error",
                    "error": str(e)
                })
                fitnesses.append(0.0)

        # Determine champion (highest fitness)
        if fitnesses:
            max_fitness_idx = fitnesses.index(max(fitnesses))
            champion_name = candidates[max_fitness_idx].get("name", f"candidate_{max_fitness_idx}")
        else:
            champion_name = "none"

        logger.info(f"[chamber_batch] Champion: {champion_name} (fitness={max(fitnesses) if fitnesses else 0:.3f})")

        # Build artifacts
        artifacts = {
            "chamber_evaluation": {
                "champion": champion_name,
                "champion_idx": max_fitness_idx if fitnesses else -1,
                "evaluator_class": self.evaluator_class.__name__,
                "total_candidates": len(candidates),
                "judge_unavailable": judge_unavailable
            },
            "results": results,
            "candidates": candidates,
            "context": context
        }

        return fitnesses, artifacts

    def _prepare_test_input(self, candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare test input dict for evaluator based on chamber type.

        This is chamber-specific - different evaluators expect different input formats.

        Args:
            candidate: Candidate parameters
            context: Tournament context (may contain skill-specific test_scenario)

        Returns:
            Test input dict
        """
        evaluator_name = self.evaluator_class.__name__

        # Check if context provides skill-specific test scenario
        if "test_scenario" in context and context["test_scenario"]:
            test_scenario = context["test_scenario"]
            logger.info(f"[chamber_batch] Using skill-specific test scenario: {test_scenario}")
            return test_scenario

        # Fallback to evaluator-specific defaults
        if evaluator_name == "SpicaConversation":
            # Conversation evaluator expects scenario
            return {
                "scenario": {
                    "name": "multi_turn_context",
                    "turns": [
                        {"user": "What is the weather?", "expected_intent": "weather_query"},
                        {"user": "What about tomorrow?", "expected_intent": "weather_query", "requires_context": True}
                    ]
                }
            }

        elif evaluator_name == "SpicaBugInjector":
            # Bug injector expects num_bugs and bug_types
            return {
                "num_bugs": candidate.get("num_bugs", 3),
                "bug_types": candidate.get("bug_types", None)
            }

        elif evaluator_name == "RepairLabEvaluator":
            # RepairLab expects difficulty and seed
            return {
                "difficulty": candidate.get("difficulty", "medium"),
                "seed": candidate.get("seed", 42)
            }

        else:
            # Generic fallback - pass candidate params as test input
            return {
                "params": candidate,
                "context": context
            }
