#!/usr/bin/env python3
"""
Progressive Skill Orchestrator - Runs skill progression tournaments.

The system that actually executes progressive skill mastery:
Skill 1 → Tournament → Champion → Skill 2 → Tournament → ... → Graduate
"""

import logging
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.skill_decomposer import SkillProgression, SkillLevel, get_skill_decomposer
from dream.dream_config_loader import get_dream_config
from dream.evaluators.chamber_batch_evaluator import ChamberBatchEvaluator

logger = logging.getLogger(__name__)


@dataclass
class SkillAttempt:
    """Record of a single skill tournament attempt."""
    skill_name: str
    attempt_number: int
    champion_name: str
    champion_fitness: float
    champion_params: Dict[str, Any]
    passed: bool
    duration_seconds: float


@dataclass
class ProgressionResult:
    """Complete result of a skill progression run."""
    goal: str
    progression_name: str
    start_time: float
    end_time: float
    total_duration_seconds: float
    skills_attempted: int
    skills_passed: int
    graduated: bool
    attempts: List[SkillAttempt]
    final_champion_params: Optional[Dict[str, Any]]
    final_champion_fitness: float
    graduation_path: str  # Path to graduated agent


class ProgressiveSkillOrchestrator:
    """
    Orchestrates progressive skill mastery tournaments.

    Takes a SkillProgression and runs each skill in sequence,
    using champions as baselines for next skill.
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.skill_decomposer = get_skill_decomposer()
        self.dream_config = get_dream_config()
        self.progression_log = Path("/home/kloros/.kloros/skill_progressions.jsonl")
        self.progression_log.parent.mkdir(parents=True, exist_ok=True)

        logger.info("[skill_orchestrator] Initialized progressive skill orchestrator")

    def run_progression(
        self,
        progression: SkillProgression,
        baseline_params: Optional[Dict[str, Any]] = None
    ) -> ProgressionResult:
        """
        Run complete skill progression from start to graduation.

        Args:
            progression: SkillProgression to execute
            baseline_params: Optional starting parameters (defaults to empty dict)

        Returns:
            ProgressionResult with complete journey
        """
        start_time = time.time()

        logger.info(f"[skill_orchestrator] Starting progression: {progression.goal}")
        logger.info(f"[skill_orchestrator] Target capability: {progression.target_capability}")
        logger.info(f"[skill_orchestrator] Skills to master: {len(progression.skills)}")

        if baseline_params is None:
            baseline_params = {}

        attempts = []
        current_params = baseline_params.copy()
        graduated = False

        # Run each skill in sequence
        for skill_idx, skill in enumerate(progression.skills):
            logger.info(f"\n{'='*80}")
            logger.info(f"[skill_orchestrator] SKILL {skill_idx + 1}/{len(progression.skills)}: {skill.name}")
            logger.info(f"[skill_orchestrator] Difficulty: {skill.difficulty}, Threshold: {skill.graduation_threshold}")
            logger.info(f"{'='*80}\n")

            # Attempt skill mastery (with retries)
            passed = False
            for attempt_num in range(1, skill.max_attempts + 1):
                logger.info(f"[skill_orchestrator] Attempt {attempt_num}/{skill.max_attempts}")

                attempt = self._run_skill_tournament(
                    skill=skill,
                    attempt_number=attempt_num,
                    baseline_params=current_params
                )

                attempts.append(attempt)

                # Check if queued due to judge unavailability
                if attempt.champion_name == "queued":
                    logger.warning(
                        f"[skill_orchestrator] ⏸️ QUEUED - Judge unavailable, will retry when online"
                    )
                    # Don't count this against max_attempts - will retry later
                    break

                if attempt.passed:
                    logger.info(f"[skill_orchestrator] ✓ PASSED! Champion fitness: {attempt.champion_fitness:.3f}")
                    # Update baseline with champion params for next skill
                    current_params = attempt.champion_params.copy()
                    passed = True
                    break
                else:
                    logger.warning(
                        f"[skill_orchestrator] ✗ Failed (fitness {attempt.champion_fitness:.3f} "
                        f"< threshold {skill.graduation_threshold})"
                    )

            if not passed:
                logger.error(
                    f"[skill_orchestrator] Failed to master {skill.name} after {skill.max_attempts} attempts. "
                    f"Aborting progression."
                )
                break

        # Check if graduated (all skills passed)
        graduated = len(attempts) == len(progression.skills) and all(a.passed for a in attempts)

        end_time = time.time()

        # Create result
        result = ProgressionResult(
            goal=progression.goal,
            progression_name=f"{progression.final_chamber}_progression",
            start_time=start_time,
            end_time=end_time,
            total_duration_seconds=end_time - start_time,
            skills_attempted=len(attempts),
            skills_passed=sum(1 for a in attempts if a.passed),
            graduated=graduated,
            attempts=attempts,
            final_champion_params=current_params if graduated else None,
            final_champion_fitness=attempts[-1].champion_fitness if attempts else 0.0,
            graduation_path=""  # Will be set by deployment
        )

        # Log result
        self._log_progression(result)

        if graduated:
            logger.info(f"\n{'='*80}")
            logger.info(f"[skill_orchestrator] 🎓 GRADUATED! All {len(progression.skills)} skills mastered")
            logger.info(f"[skill_orchestrator] Final fitness: {result.final_champion_fitness:.3f}")
            logger.info(f"[skill_orchestrator] Total duration: {result.total_duration_seconds:.1f}s")
            logger.info(f"{'='*80}\n")
        else:
            logger.warning(f"[skill_orchestrator] Progression incomplete: {result.skills_passed}/{len(progression.skills)} skills passed")

        return result

    def _run_skill_tournament(
        self,
        skill: SkillLevel,
        attempt_number: int,
        baseline_params: Dict[str, Any]
    ) -> SkillAttempt:
        """
        Run tournament for a single skill.

        Args:
            skill: SkillLevel to test
            attempt_number: Which attempt this is
            baseline_params: Parameters from previous champion (or baseline)

        Returns:
            SkillAttempt with results
        """
        start_time = time.time()

        # Get chamber evaluator class
        evaluator_class = self.dream_config.get_evaluator_class(skill.chamber_name)
        if not evaluator_class:
            logger.error(f"[skill_orchestrator] Failed to load evaluator for {skill.chamber_name}")
            return SkillAttempt(
                skill_name=skill.name,
                attempt_number=attempt_number,
                champion_name="none",
                champion_fitness=0.0,
                champion_params={},
                passed=False,
                duration_seconds=time.time() - start_time
            )

        # Get init kwargs
        init_kwargs = self.dream_config.get_evaluator_init_kwargs(skill.chamber_name)

        # Get search space and generate candidates
        search_space = self.dream_config.get_search_space(skill.chamber_name)

        # Generate 8 candidates, starting from baseline params
        import random
        candidates = []
        for i in range(8):
            candidate = baseline_params.copy()
            candidate["name"] = f"{skill.chamber_name}_skill_{skill.name.replace(' ', '_').lower()}_{i}"

            # Add variations from search space
            for param_name, param_values in search_space.items():
                if isinstance(param_values, list) and param_values:
                    candidate[param_name] = random.choice(param_values)

            candidates.append(candidate)

        logger.info(f"[skill_orchestrator] Generated {len(candidates)} candidates from baseline + search space")

        # Wrap evaluator for batch mode
        evaluator = ChamberBatchEvaluator(evaluator_class, init_kwargs)

        # Prepare context with skill-specific test scenario
        context = {
            "skill_name": skill.name,
            "skill_difficulty": skill.difficulty,
            "attempt_number": attempt_number,
            "test_scenario": skill.test_scenario
        }

        # Run tournament
        try:
            fitnesses, artifacts = evaluator.evaluate_batch(candidates, context)

            # Check if judge unavailable - if so, return special queued status
            if artifacts.get("chamber_evaluation", {}).get("judge_unavailable", False):
                logger.warning(f"[skill_orchestrator] Judge unavailable - skill {skill.name} queued for later")
                return SkillAttempt(
                    skill_name=skill.name,
                    attempt_number=attempt_number,
                    champion_name="queued",
                    champion_fitness=0.0,
                    champion_params={},
                    passed=False,  # Not passed, but special "queued" status
                    duration_seconds=time.time() - start_time
                )

            # Find champion
            max_fitness = max(fitnesses) if fitnesses else 0.0
            champion_idx = fitnesses.index(max_fitness) if fitnesses else 0
            champion = candidates[champion_idx]

            # Check if passed graduation threshold
            passed = max_fitness >= skill.graduation_threshold

            duration = time.time() - start_time

            return SkillAttempt(
                skill_name=skill.name,
                attempt_number=attempt_number,
                champion_name=champion.get("name", "unknown"),
                champion_fitness=max_fitness,
                champion_params=champion,
                passed=passed,
                duration_seconds=duration
            )

        except Exception as e:
            logger.error(f"[skill_orchestrator] Tournament failed: {e}", exc_info=True)
            return SkillAttempt(
                skill_name=skill.name,
                attempt_number=attempt_number,
                champion_name="error",
                champion_fitness=0.0,
                champion_params={},
                passed=False,
                duration_seconds=time.time() - start_time
            )

    def _log_progression(self, result: ProgressionResult):
        """Write progression result to log file."""
        try:
            with open(self.progression_log, 'a') as f:
                f.write(json.dumps(asdict(result)) + "\n")
            logger.info(f"[skill_orchestrator] Logged progression to {self.progression_log}")
        except Exception as e:
            logger.error(f"[skill_orchestrator] Failed to log progression: {e}")


# Singleton instance
_skill_orchestrator = None


def get_skill_orchestrator() -> ProgressiveSkillOrchestrator:
    """Get singleton skill orchestrator instance."""
    global _skill_orchestrator
    if _skill_orchestrator is None:
        _skill_orchestrator = ProgressiveSkillOrchestrator()
    return _skill_orchestrator
