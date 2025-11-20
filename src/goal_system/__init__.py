"""
Goal System - Explicit Goal Tracking and Homeostatic Integration

Provides the "what the system wants" layer that drives consciousness.
Goals create homeostatic pressure → emotions → behavioral modulation.

Architecture:
    Goal → Homeostatic Variable → Affective Pressure → Emotions → Modulation

Future integration points:
    - Neurochemical state per goal (dopamine, serotonin, cortisol)
    - Reward prediction error (progress_delta - expected_progress)
    - Per-emotion affective half-life for decay dynamics
"""

from .models import Goal, GoalState, GoalProperties, NeurochemicalState
from .manager import GoalManager
from .consciousness_integration import (
    GoalConsciousnessIntegrator,
    integrate_goals_with_consciousness
)

__all__ = [
    'Goal',
    'GoalState',
    'GoalProperties',
    'NeurochemicalState',
    'GoalManager',
    'GoalConsciousnessIntegrator',
    'integrate_goals_with_consciousness',
]
