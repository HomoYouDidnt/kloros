"""
Affective ChemBus Signal Definitions

Signals emitted based on affective introspection to trigger autonomous actions.
Each signal maps to a specific action domain (emergency, system, cognitive).
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass


class AffectSignal(str, Enum):
    """ChemBus signals for affective action execution."""

    # Emergency signals (PANIC-based) - Highest priority
    EMERGENCY_BRAKE = "AFFECT_EMERGENCY_BRAKE"
    CRITICAL_FATIGUE = "AFFECT_CRITICAL_FATIGUE"
    STUCK_LOOP = "AFFECT_STUCK_LOOP"

    # System healing signals (RAGE-based) - System infrastructure
    HIGH_RAGE = "AFFECT_HIGH_RAGE"
    RESOURCE_STRAIN = "AFFECT_RESOURCE_STRAIN"
    REPETITIVE_ERROR = "AFFECT_REPETITIVE_ERROR"

    # Cognitive action signals (FRUSTRATION/SEEKING-based) - Data operations
    MEMORY_PRESSURE = "AFFECT_MEMORY_PRESSURE"
    TASK_FAILURE_PATTERN = "AFFECT_TASK_FAILURE_PATTERN"
    MODULE_INTEGRATION_NEEDED = "AFFECT_MODULE_INTEGRATION_NEEDED"
    CONTEXT_OVERFLOW = "AFFECT_CONTEXT_OVERFLOW"

    # Informational signals
    STATE_CHANGE = "AFFECT_STATE_CHANGE"
    WELLBEING_LOW = "AFFECT_WELLBEING_LOW"
    WELLBEING_HIGH = "AFFECT_WELLBEING_HIGH"


@dataclass
class AffectSignalEmitter:
    """
    Analyzes affective introspection and emits appropriate ChemBus signals.

    Maps affective states → concrete signals that trigger autonomous actions.
    """

    def __init__(self, chem_pub):
        """
        Initialize signal emitter.

        Args:
            chem_pub: ChemPub instance for emitting signals
        """
        self.chem_pub = chem_pub
        self.last_emergency_emit = 0.0
        self.emergency_cooldown = 60.0  # Only emit emergency once per minute

        # Emergency lobotomy system
        self.lobotomy = None
        try:
            from .emergency_lobotomy import EmergencyLobotomy
            self.lobotomy = EmergencyLobotomy()
            print("[affect_signals] 🧠 Emergency lobotomy system available")
        except Exception as e:
            print(f"[affect_signals] Lobotomy system not available: {e}")

    def emit_from_introspection(self, introspection, affect, emotions) -> None:
        """
        Emit ChemBus signals based on affective introspection.

        Args:
            introspection: AffectIntrospection result
            affect: Current Affect state
            emotions: Current EmotionalState
        """
        import time

        if not introspection:
            return

        ecosystem = 'affect'

        # TIER 0: EXTREME CONDITION CHECK - Emergency Lobotomy
        # Check if affective state is so extreme it prevents rational thought
        # If so, temporarily disconnect affect system to allow remediation
        if self.lobotomy:
            should_lobotomize, reason = self.lobotomy.should_lobotomize(affect, emotions)
            if should_lobotomize:
                print(f"[affect_signals] 🧠❌ EXTREME AFFECTIVE STATE DETECTED")
                print(f"[affect_signals] Triggering emergency lobotomy: {reason}")
                if self.lobotomy.execute_lobotomy(reason):
                    # Lobotomy executed - stop processing further signals
                    # Operating in pure logic mode now
                    return

        # TIER 1: EMERGENCY SIGNALS (checked first)

        # Emergency brake: PANIC > 0.7 OR critical urgency
        if emotions.PANIC > 0.7 or introspection.urgency.value == 'critical':
            # Rate limit emergency signals
            now = time.time()
            if now - self.last_emergency_emit > self.emergency_cooldown:
                self.chem_pub.emit(
                    AffectSignal.EMERGENCY_BRAKE.value,
                    ecosystem=ecosystem,
                    intensity=emotions.PANIC,
                    facts={
                        'urgency': introspection.urgency.value,
                        'primary_affects': introspection.primary_affects,
                        'can_self_remediate': introspection.can_self_remediate,
                        'evidence': introspection.evidence
                    }
                )
                self.last_emergency_emit = now
                print(f"[affect_signals] 🚨 EMERGENCY BRAKE emitted (PANIC: {emotions.PANIC:.2f})")
                return  # Don't emit other signals if emergency

        # Critical fatigue
        if affect.fatigue > 0.9:
            self.chem_pub.emit(
                AffectSignal.CRITICAL_FATIGUE.value,
                ecosystem=ecosystem,
                intensity=affect.fatigue,
                facts={
                    'fatigue': affect.fatigue,
                    'evidence': introspection.evidence
                }
            )
            print(f"[affect_signals] ⚠️ CRITICAL_FATIGUE emitted ({affect.fatigue:.0%})")

        # TIER 2: SYSTEM HEALING SIGNALS (RAGE-based)

        # High RAGE → system frustrated, trigger healing
        if emotions.RAGE > 0.6:
            self.chem_pub.emit(
                AffectSignal.HIGH_RAGE.value,
                ecosystem=ecosystem,
                intensity=emotions.RAGE,
                facts={
                    'root_causes': introspection.root_causes,
                    'contributing_factors': introspection.contributing_factors,
                    'autonomous_actions': introspection.autonomous_actions,
                    'urgency': introspection.urgency.value
                }
            )
            print(f"[affect_signals] 😤 HIGH_RAGE emitted (RAGE: {emotions.RAGE:.2f})")

        # Resource strain detected
        if 'high_memory_pressure' in introspection.root_causes or \
           'high_context_pressure' in introspection.root_causes:
            self.chem_pub.emit(
                AffectSignal.RESOURCE_STRAIN.value,
                ecosystem=ecosystem,
                intensity=0.8,
                facts={
                    'root_causes': introspection.root_causes,
                    'contributing_factors': introspection.contributing_factors
                }
            )
            print(f"[affect_signals] 📊 RESOURCE_STRAIN emitted")

        # Repetitive errors detected
        if 'cumulative_strain' in introspection.root_causes or \
           any('repetitive' in str(c).lower() for c in introspection.root_causes):
            self.chem_pub.emit(
                AffectSignal.REPETITIVE_ERROR.value,
                ecosystem=ecosystem,
                intensity=emotions.RAGE,
                facts={
                    'root_causes': introspection.root_causes,
                    'autonomous_actions': introspection.autonomous_actions
                }
            )
            print(f"[affect_signals] 🔁 REPETITIVE_ERROR emitted")

        # TIER 3: COGNITIVE ACTION SIGNALS

        # Memory pressure (high token usage)
        if 'high_token_usage' in introspection.root_causes:
            self.chem_pub.emit(
                AffectSignal.MEMORY_PRESSURE.value,
                ecosystem=ecosystem,
                intensity=introspection.contributing_factors.get('high_token_usage', 0.7),
                facts={
                    'autonomous_actions': [
                        a for a in introspection.autonomous_actions
                        if 'context' in a.lower() or 'summarize' in a.lower() or 'archive' in a.lower()
                    ],
                    'evidence': introspection.evidence
                }
            )
            print(f"[affect_signals] 💾 MEMORY_PRESSURE emitted")

        # Context overflow
        if 'high_context_pressure' in introspection.root_causes:
            self.chem_pub.emit(
                AffectSignal.CONTEXT_OVERFLOW.value,
                ecosystem=ecosystem,
                intensity=introspection.contributing_factors.get('high_context_pressure', 0.7),
                facts={
                    'autonomous_actions': [
                        a for a in introspection.autonomous_actions
                        if 'context' in a.lower()
                    ]
                }
            )
            print(f"[affect_signals] 📝 CONTEXT_OVERFLOW emitted")

        # Task failure pattern
        if 'task_failures' in introspection.root_causes:
            self.chem_pub.emit(
                AffectSignal.TASK_FAILURE_PATTERN.value,
                ecosystem=ecosystem,
                intensity=introspection.contributing_factors.get('task_failures', 0.6),
                facts={
                    'autonomous_actions': [
                        a for a in introspection.autonomous_actions
                        if 'analyze' in a.lower() or 'failure' in a.lower()
                    ],
                    'root_causes': introspection.root_causes
                }
            )
            print(f"[affect_signals] ❌ TASK_FAILURE_PATTERN emitted")

        # TIER 4: INFORMATIONAL SIGNALS

        # Significant affective state change
        if introspection.affect_valence in ['negative', 'positive']:
            self.chem_pub.emit(
                AffectSignal.STATE_CHANGE.value,
                ecosystem=ecosystem,
                intensity=abs(affect.valence),
                facts={
                    'affect_description': introspection.affect_description,
                    'affect_valence': introspection.affect_valence,
                    'primary_affects': introspection.primary_affects,
                    'dominant_emotion': max(
                        [('SEEKING', emotions.SEEKING), ('RAGE', emotions.RAGE),
                         ('FEAR', emotions.FEAR), ('PANIC', emotions.PANIC)],
                        key=lambda x: x[1]
                    )[0]
                }
            )

        # Low wellbeing
        if hasattr(introspection, 'wellbeing'):
            # Compute wellbeing if not in introspection
            pass
