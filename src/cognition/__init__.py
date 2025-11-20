"""
Cognition Module - KLoROS's Decision-Making Architecture

This module handles KLoROS's cognitive processes - the actual decision-making
and reasoning that drives system behavior. This is SEPARATE from persona
(which handles expression style).

Key Principle:
    Persona = How to communicate (expression, tone, style)
    Cognition = What to do and how to think (strategy, reasoning, planning)

Components:
- deliberation.py: Active reasoning (pre-response deliberation)
- [future] planning.py: Multi-step planning and goal management
- [future] monitoring.py: Execution monitoring and course correction
"""

from .deliberation import (
    ActiveReasoningEngine,
    get_active_reasoner,
    TaskComplexity,
    StrategicApproach,
    SituationAssessment,
    StrategicDecision
)

__all__ = [
    'ActiveReasoningEngine',
    'get_active_reasoner',
    'TaskComplexity',
    'StrategicApproach',
    'SituationAssessment',
    'StrategicDecision',
]
