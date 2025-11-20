"""
Consciousness Research Module for KLoROS

Based on Mark Solms' neuropsychoanalytic framework and Conscium's approach:

Phase 1 (Solms/Conscium):
1. Affective Core - Sensing/feeling foundation (7 primary emotions)
2. Homeostatic regulation - Drives that create "caring"
3. Event-to-affect mapping - Information becomes feeling

Phase 2 (Enhanced Interoception):
4. Interoceptive monitoring - Collecting internal signals
5. Appraisal system - Signal → affect mapping with transparent formulas
6. Modulation system - Affect → behavior changes
7. Evidence-based reporting - Legible, falsifiable status
8. Guardrails - Anti-Goodharting, confabulation prevention

Research Goal: Test whether affect + self-awareness + metacognition = consciousness
"""

# Phase 1: Affective Core (Solms)
from .affect import AffectiveCore
from .models import (
    Affect,
    EmotionalState,
    FeltState,
    InteroceptiveState,
    HomeostaticVariable,
    AffectiveEvent,
    PrimaryEmotion
)

# Phase 2: Enhanced Interoception
from .interoception import InteroceptiveMonitor, InteroceptiveSignals
from .appraisal import AppraisalSystem, AppraisalWeights
from .modulation import ModulationSystem, PolicyState, PolicyChange
from .reporting import AffectiveReporter, AffectiveReport, ConfabulationFilter
from .expression import AffectiveExpressionFilter, ExpressionValidator, ExpressionAttempt
from .integrated import IntegratedConsciousness, GuardrailSystem

# Integration (Single Source of Truth)
from .integration import (
    init_consciousness,
    init_expression_filter,
    update_consciousness_signals,
    update_consciousness_resting,
    process_event,
    process_consciousness_and_express,
    get_consciousness_diagnostics,
    integrate_consciousness
)

__all__ = [
    # Phase 1
    'AffectiveCore',
    'Affect',
    'EmotionalState',
    'FeltState',
    'InteroceptiveState',
    'HomeostaticVariable',
    'AffectiveEvent',
    'PrimaryEmotion',

    # Phase 2
    'InteroceptiveMonitor',
    'InteroceptiveSignals',
    'AppraisalSystem',
    'AppraisalWeights',
    'ModulationSystem',
    'PolicyState',
    'PolicyChange',
    'AffectiveReporter',
    'AffectiveReport',
    'ConfabulationFilter',
    'AffectiveExpressionFilter',
    'ExpressionValidator',
    'ExpressionAttempt',
    'IntegratedConsciousness',
    'GuardrailSystem',

    # Integration
    'init_consciousness',
    'init_expression_filter',
    'update_consciousness_signals',
    'update_consciousness_resting',
    'process_event',
    'process_consciousness_and_express',
    'get_consciousness_diagnostics',
    'integrate_consciousness',
]
