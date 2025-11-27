#!/usr/bin/env python3
"""
Skill Decomposer - KLoROS's ability to break goals into progressive skill sequences.

GLaDOS designing test chamber sequences. Takes high-level goals and decomposes
them into progressive skill mastery paths.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class SkillLevel:
    """
    A single skill in the progression sequence.

    Example: "Intent Classification" before "Multi-turn Context"
    """
    name: str
    description: str
    chamber_name: str
    test_scenario: Dict[str, Any]
    difficulty: str  # "easy", "medium", "hard"
    graduation_threshold: float  # Minimum fitness to graduate (0.0-1.0)
    max_attempts: int = 3  # How many tournament attempts before giving up


@dataclass
class SkillProgression:
    """
    Complete skill mastery path from newborn to competent agent.

    Example: Conversation Agent
    - Skill 1: Simple intent classification
    - Skill 2: Context retention (2 turns)
    - Skill 3: Error recovery
    - Skill 4: Full multi-turn conversation
    """
    goal: str
    target_capability: str
    skills: List[SkillLevel]
    final_chamber: str
    estimated_duration_minutes: int


class SkillDecomposer:
    """
    KLoROS's skill decomposition engine.

    Analyzes high-level goals and creates progressive skill sequences
    that build from basic to advanced capabilities.
    """

    # Predefined skill progressions for common goals
    SKILL_PROGRESSIONS = {
        "conversation_agent": SkillProgression(
            goal="Create competent conversation agent",
            target_capability="Multi-turn conversation with intent classification, context retention, and error recovery",
            skills=[
                SkillLevel(
                    name="Basic Intent Classification",
                    description="Classify simple single-turn user intents",
                    chamber_name="conv_quality_spica",
                    test_scenario={
                        "scenario": {
                            "name": "simple_query",
                            "turns": [
                                {"user": "What time is it?", "expected_intent": "time_query"}
                            ]
                        }
                    },
                    difficulty="easy",
                    graduation_threshold=0.7,
                    max_attempts=2
                ),
                SkillLevel(
                    name="Two-Turn Context",
                    description="Maintain context across 2 conversation turns",
                    chamber_name="conv_quality_spica",
                    test_scenario={
                        "scenario": {
                            "name": "two_turn_context",
                            "turns": [
                                {"user": "What is the weather?", "expected_intent": "weather_query"},
                                {"user": "What about tomorrow?", "expected_intent": "weather_query", "requires_context": True}
                            ]
                        }
                    },
                    difficulty="medium",
                    graduation_threshold=0.75,
                    max_attempts=3
                ),
                SkillLevel(
                    name="Error Recovery",
                    description="Handle unintelligible input gracefully",
                    chamber_name="conv_quality_spica",
                    test_scenario={
                        "scenario": {
                            "name": "error_recovery",
                            "turns": [
                                {"user": "unintelligible audio", "expected_intent": "unknown", "should_recover": True}
                            ]
                        }
                    },
                    difficulty="medium",
                    graduation_threshold=0.7,
                    max_attempts=2
                ),
                SkillLevel(
                    name="Full Multi-Turn Mastery",
                    description="Complete multi-turn conversation with all skills combined",
                    chamber_name="conv_quality_spica",
                    test_scenario={
                        "scenario": {
                            "name": "multi_turn_mastery",
                            "turns": [
                                {"user": "What is the weather?", "expected_intent": "weather_query"},
                                {"user": "What about tomorrow?", "expected_intent": "weather_query", "requires_context": True},
                                {"user": "And the day after?", "expected_intent": "weather_query", "requires_context": True}
                            ]
                        }
                    },
                    difficulty="hard",
                    graduation_threshold=0.8,
                    max_attempts=5
                )
            ],
            final_chamber="conv_quality_spica",
            estimated_duration_minutes=15
        ),

        "code_repair_agent": SkillProgression(
            goal="Create code repair specialist",
            target_capability="Fix syntax errors, logic bugs, and pass test suites",
            skills=[
                SkillLevel(
                    name="Syntax Error Detection",
                    description="Identify and fix basic syntax errors",
                    chamber_name="spica_repairlab",
                    test_scenario={
                        "difficulty": "easy",
                        "seed": 42
                    },
                    difficulty="easy",
                    graduation_threshold=0.7,
                    max_attempts=2
                ),
                SkillLevel(
                    name="Logic Bug Repair",
                    description="Fix logic errors (off-by-one, wrong operators)",
                    chamber_name="spica_repairlab",
                    test_scenario={
                        "difficulty": "medium",
                        "seed": 1337
                    },
                    difficulty="medium",
                    graduation_threshold=0.75,
                    max_attempts=3
                ),
                SkillLevel(
                    name="Complex Repair Mastery",
                    description="Handle complex bugs with multiple fixes needed",
                    chamber_name="spica_repairlab",
                    test_scenario={
                        "difficulty": "hard",
                        "seed": 99999
                    },
                    difficulty="hard",
                    graduation_threshold=0.8,
                    max_attempts=5
                )
            ],
            final_chamber="spica_repairlab",
            estimated_duration_minutes=20
        ),

        "planning_agent": SkillProgression(
            goal="Create strategic planning agent",
            target_capability="Generate effective plans using various search strategies",
            skills=[
                SkillLevel(
                    name="Greedy Planning",
                    description="Simple greedy strategy for quick plans",
                    chamber_name="spica_planning",
                    test_scenario={
                        "params": {"strategy": "greedy", "lookahead_depth": 1}
                    },
                    difficulty="easy",
                    graduation_threshold=0.6,
                    max_attempts=2
                ),
                SkillLevel(
                    name="Beam Search Planning",
                    description="Wider search with beam strategy",
                    chamber_name="spica_planning",
                    test_scenario={
                        "params": {"strategy": "beam", "lookahead_depth": 2}
                    },
                    difficulty="medium",
                    graduation_threshold=0.7,
                    max_attempts=3
                ),
                SkillLevel(
                    name="MCTS Planning Mastery",
                    description="Advanced MCTS strategy for complex problems",
                    chamber_name="spica_planning",
                    test_scenario={
                        "params": {"strategy": "mcts", "lookahead_depth": 3}
                    },
                    difficulty="hard",
                    graduation_threshold=0.8,
                    max_attempts=4
                )
            ],
            final_chamber="spica_planning",
            estimated_duration_minutes=18
        )
    }

    def decompose_goal(self, goal: str, context: Optional[Dict[str, Any]] = None) -> Optional[SkillProgression]:
        """
        Decompose a high-level goal into progressive skill sequence.

        Args:
            goal: High-level goal description
            context: Additional context for decomposition

        Returns:
            SkillProgression or None if goal not recognized
        """
        # Keyword matching for predefined progressions
        goal_lower = goal.lower()

        if any(kw in goal_lower for kw in ["conversation", "chat", "dialogue", "talk"]):
            logger.info(f"[skill_decomposer] Mapped goal to conversation_agent progression")
            return self.SKILL_PROGRESSIONS["conversation_agent"]

        elif any(kw in goal_lower for kw in ["repair", "fix", "debug", "code quality"]):
            logger.info(f"[skill_decomposer] Mapped goal to code_repair_agent progression")
            return self.SKILL_PROGRESSIONS["code_repair_agent"]

        elif any(kw in goal_lower for kw in ["planning", "strategy", "plan"]):
            logger.info(f"[skill_decomposer] Mapped goal to planning_agent progression")
            return self.SKILL_PROGRESSIONS["planning_agent"]

        else:
            logger.warning(f"[skill_decomposer] No progression found for goal: {goal}")
            return None

    def get_progression(self, progression_name: str) -> Optional[SkillProgression]:
        """Get a predefined skill progression by name."""
        return self.SKILL_PROGRESSIONS.get(progression_name)

    def list_progressions(self) -> List[str]:
        """List all available skill progressions."""
        return list(self.SKILL_PROGRESSIONS.keys())

    def save_progression(self, progression: SkillProgression, filepath: str):
        """Save skill progression to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(asdict(progression), f, indent=2)
        logger.info(f"[skill_decomposer] Saved progression to {filepath}")

    def load_progression(self, filepath: str) -> SkillProgression:
        """Load skill progression from JSON file."""
        with open(filepath) as f:
            data = json.load(f)

        # Reconstruct SkillLevel objects
        skills = [SkillLevel(**skill) for skill in data["skills"]]
        data["skills"] = skills

        return SkillProgression(**data)


# Singleton instance
_skill_decomposer = None


def get_skill_decomposer() -> SkillDecomposer:
    """Get singleton skill decomposer instance."""
    global _skill_decomposer
    if _skill_decomposer is None:
        _skill_decomposer = SkillDecomposer()
    return _skill_decomposer
