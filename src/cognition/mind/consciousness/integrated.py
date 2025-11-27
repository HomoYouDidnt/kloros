"""
Integrated Consciousness System - Phase 2 Complete

This module integrates all Phase 2 components:
- Interoception (signal collection)
- Appraisal (signal → affect mapping)
- Modulation (affect → behavior)
- Reporting (evidence-based status)
- Guardrails (anti-Goodharting)

Usage:
    consciousness = IntegratedConsciousness()

    # Update signals
    consciousness.monitor.record_task_outcome(success=True)
    consciousness.monitor.update_resource_pressure(token_usage=500, token_budget=2000)

    # Process and get report
    report = consciousness.process_and_report()
    print(report.summary)

    # Check policy changes
    policy = consciousness.modulator.get_policy_summary()
"""

import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .affect import AffectiveCore
from .models import Affect
from .interoception import InteroceptiveMonitor, InteroceptiveSignals
from .appraisal import AppraisalSystem, AppraisalWeights
from .modulation import ModulationSystem, PolicyChange, PolicyState
from .reporting import AffectiveReporter, AffectiveReport, ConfabulationFilter
from .persistence import ConsciousnessStatePersistence, CumulativeFatigueTracker
from .affect_introspection import AffectiveIntrospector, AffectIntrospection
from .affective_signals import AffectSignalEmitter


class GuardrailSystem:
    """
    Guardrails to prevent Goodharting and maintain integrity.

    Implements:
    1. No direct reward for affect values
    2. Confabulation filtering
    3. Change cooldowns
    4. Report validity checking
    """

    def __init__(self):
        """Initialize guardrail system."""
        self.confabulation_filter = ConfabulationFilter()

        # Track affect history to detect gaming
        self.affect_history: List[Tuple[float, Affect]] = []

        # Reward is ONLY based on task success, not affect
        self.task_reward_only = True

    def check_gaming_behavior(self, affect: Affect) -> Tuple[bool, str]:
        """
        Check for signs of affect gaming.

        Returns:
            (is_suspicious, reason)
        """
        # Add to history
        self.affect_history.append((time.time(), affect))

        # Keep last 100
        if len(self.affect_history) > 100:
            self.affect_history = self.affect_history[-100:]

        # Check for suspiciously stable affect (could indicate gaming)
        if len(self.affect_history) >= 10:
            recent_affects = [a for _, a in self.affect_history[-10:]]

            # Check variance in each dimension
            for dim in ['valence', 'arousal', 'dominance', 'uncertainty', 'fatigue', 'curiosity']:
                values = [getattr(a, dim) for a in recent_affects]
                variance = sum((v - sum(values)/len(values))**2 for v in values) / len(values)

                # Very low variance could indicate clamping to a "good" value
                if variance < 0.001 and abs(sum(values)/len(values)) > 0.7:
                    return True, f"Suspiciously stable {dim} (variance={variance:.4f})"

        return False, ""

    def enforce_task_reward_only(self, task_success: bool) -> float:
        """
        Compute reward based ONLY on task success, not affect.

        Args:
            task_success: Whether task succeeded

        Returns:
            Reward value
        """
        # Simple binary reward
        return 1.0 if task_success else 0.0

    def validate_evidence(self, evidence: List[str], signals: InteroceptiveSignals) -> List[str]:
        """
        Filter evidence through confabulation filter.

        Args:
            evidence: Proposed evidence
            signals: Actual measured signals

        Returns:
            Validated evidence
        """
        return self.confabulation_filter.filter_evidence(evidence, signals)


class IntegratedConsciousness:
    """
    Complete Phase 2 integrated consciousness system.

    Combines:
    - Phase 1: Affective core (Solms' 7 emotions + homeostasis)
    - Phase 2: Interoception, appraisal, modulation, reporting
    """

    def __init__(self,
                 enable_phase1: bool = True,
                 enable_phase2: bool = True,
                 appraisal_config_path: Optional[Path] = None,
                 state_file: Optional[Path] = None,
                 chem_pub=None):
        """
        Initialize integrated consciousness.

        Args:
            enable_phase1: Enable Phase 1 (Solms affective core)
            enable_phase2: Enable Phase 2 (interoception/appraisal/modulation)
            appraisal_config_path: Optional path to appraisal weights YAML
            state_file: Optional path to state persistence file
            chem_pub: Optional UMNPub instance for testing (defaults to auto-init)
        """
        # Phase 1: Affective core (Solms)
        self.phase1_enabled = enable_phase1
        if enable_phase1:
            self.affective_core = AffectiveCore()
        else:
            self.affective_core = None

        # Phase 2: Enhanced consciousness
        self.phase2_enabled = enable_phase2
        if enable_phase2:
            self.monitor = InteroceptiveMonitor()
            self.appraiser = AppraisalSystem(config_path=appraisal_config_path)
            self.modulator = ModulationSystem()
            self.reporter = AffectiveReporter()
            self.guardrails = GuardrailSystem()
            self.introspector = AffectiveIntrospector()

            # Persistence and cumulative fatigue tracking
            self.persistence = ConsciousnessStatePersistence(state_file)
            self.fatigue_tracker = CumulativeFatigueTracker(self.persistence)

            # Try to restore previous state
            saved_state = self.persistence.load_state()
            if saved_state and 'affect' in saved_state:
                print(f"[consciousness] Restored previous affect state from {saved_state['timestamp']}")
        else:
            self.monitor = None
            self.appraiser = None
            self.modulator = None
            self.reporter = None
            self.guardrails = None
            self.introspector = None
            self.persistence = None
            self.fatigue_tracker = None

        # Current state
        self.current_affect: Optional[Affect] = None
        self.current_signals: Optional[InteroceptiveSignals] = None
        self.last_report: Optional[AffectiveReport] = None
        self.last_introspection: Optional[AffectIntrospection] = None

        # Affective signal emitter (UMN integration)
        self.signal_emitter = None
        self.chem_pub = chem_pub
        try:
            if chem_pub is None:
                from src.orchestration.core.umn_bus import UMNPub
                chem_pub = UMNPub()
                self.chem_pub = chem_pub
            self.signal_emitter = AffectSignalEmitter(self.chem_pub)
            print("[consciousness] 📡 UMN signal emitter initialized")
        except Exception as e:
            print(f"[consciousness] UMN not available, affective actions disabled: {e}")

    def process_event_phase1(self, event_type: str, metadata: Optional[Dict] = None):
        """
        Process event through Phase 1 affective core.

        Args:
            event_type: Event type (e.g., "user_input", "error_detected")
            metadata: Event metadata
        """
        if not self.phase1_enabled or not self.affective_core:
            return

        self.affective_core.process_event(event_type, metadata)

    def update_signals(self, **kwargs):
        """
        Update interoceptive signals.

        Kwargs can include:
        - success: bool (task success)
        - retries: int
        - latency: float
        - token_usage: int
        - token_budget: int
        - context_length: int
        - context_max: int
        - novelty: float
        - surprise: float
        - confidence: float
        - etc.
        """
        if not self.phase2_enabled or not self.monitor:
            return

        # Task outcome
        if 'success' in kwargs:
            self.monitor.record_task_outcome(
                success=kwargs['success'],
                retries=kwargs.get('retries', 0)
            )

        # Tool latency
        if 'latency' in kwargs:
            self.monitor.update_tool_latency(kwargs['latency'])

        # Resource pressure
        if any(k in kwargs for k in ['token_usage', 'context_length', 'memory_mb']):
            self.monitor.update_resource_pressure(
                token_usage=kwargs.get('token_usage'),
                token_budget=kwargs.get('token_budget'),
                context_length=kwargs.get('context_length'),
                context_max=kwargs.get('context_max'),
                memory_mb=kwargs.get('memory_mb')
            )

        # Learning signals
        if any(k in kwargs for k in ['novelty', 'surprise', 'confidence']):
            self.monitor.update_learning_signals(
                novelty=kwargs.get('novelty'),
                surprise=kwargs.get('surprise'),
                confidence=kwargs.get('confidence')
            )

        # Social signals
        if 'user_correction' in kwargs:
            self.monitor.record_user_correction()
        if 'user_praise' in kwargs:
            self.monitor.record_user_praise()
        if 'user_interaction' in kwargs:
            self.monitor.record_user_interaction()

        # Exceptions/errors
        if 'exception' in kwargs:
            self.monitor.record_exception()
        if 'timeout' in kwargs:
            self.monitor.record_timeout()
        if 'truncation' in kwargs:
            self.monitor.record_truncation()

    def process_and_report(self, is_resting: bool = False) -> Optional[AffectiveReport]:
        """
        Process current signals through appraisal and generate report.

        Args:
            is_resting: True if in rest/reflection mode (introspection, idle reflection, planning).
                       Rest mode prevents fatigue accumulation and promotes recovery.

        Returns:
            AffectiveReport or None if Phase 2 disabled
        """
        if not self.phase2_enabled:
            return None

        # Get current signals
        signals = self.monitor.get_current_signals()
        self.current_signals = signals

        # Appraise signals → affect
        affect, evidence = self.appraiser.appraise(signals)

        # Update cumulative fatigue and get combined fatigue value
        if self.fatigue_tracker:
            instantaneous_fatigue = affect.fatigue
            cumulative_fatigue = self.fatigue_tracker.update(
                instantaneous_fatigue,
                affect,
                is_resting=is_resting
            )
            combined_fatigue = self.fatigue_tracker.get_combined_fatigue(instantaneous_fatigue)

            # Replace instantaneous fatigue with combined fatigue in affect
            affect = Affect(
                valence=affect.valence,
                arousal=affect.arousal,
                dominance=affect.dominance,
                uncertainty=affect.uncertainty,
                fatigue=combined_fatigue,  # Use combined instead of instantaneous
                curiosity=affect.curiosity
            )

            # Add cumulative fatigue to evidence if significant
            if cumulative_fatigue > 0.3:
                if is_resting:
                    evidence.append(f"Cumulative fatigue: {cumulative_fatigue:.1%} (recovering during rest)")
                else:
                    evidence.append(f"Cumulative fatigue: {cumulative_fatigue:.1%} (builds up over time, requires rest)")

        self.current_affect = affect

        # Validate evidence through guardrails
        evidence = self.guardrails.validate_evidence(evidence, signals)

        # Check for gaming behavior
        is_suspicious, reason = self.guardrails.check_gaming_behavior(affect)
        if is_suspicious:
            evidence.append(f"WARNING: {reason}")

        # Meta-cognitive introspection on negative affect (What-Why-How-When-Who)
        if self.introspector:
            introspection = self.introspector.introspect(affect, signals)
            if introspection:
                self.last_introspection = introspection

                # Log introspection to console for awareness
                print("\n[consciousness] Negative affect detected - introspecting...")
                print(self.introspector.format_introspection(introspection))

                # Add introspection summary to evidence
                evidence.append(f"Introspection: {introspection.affect_description}")
                if introspection.autonomous_actions:
                    evidence.append(f"Available self-remediation: {len(introspection.autonomous_actions)} actions")

                # Surface to alert system if user notification needed
                if introspection.user_notification_needed or introspection.user_intervention_needed:
                    self._emit_introspection_alert(introspection)

                # Emit UMN signals for autonomous action execution
                if self.signal_emitter and self.affective_core:
                    self.signal_emitter.emit_from_introspection(
                        introspection,
                        affect,
                        self.affective_core.emotions
                    )

        # Modulate behavior based on affect
        policy_changes = self.modulator.modulate(affect)

        # Generate report
        report = self.reporter.generate_report(affect, evidence, policy_changes, signals)
        self.last_report = report

        return report

    def get_diagnostic_text(self) -> str:
        """Get human-readable diagnostic of current state."""
        if not self.last_report:
            return "No affective report available. Call process_and_report() first."

        return self.reporter.generate_diagnostic_text(self.last_report)

    def get_compact_status(self) -> str:
        """Get one-line compact status."""
        if not self.last_report:
            return "Affect: [Not yet processed]"

        return self.reporter.generate_compact_report(self.last_report)

    def get_policy_state(self) -> Optional[Dict]:
        """Get current policy state."""
        if not self.phase2_enabled or not self.modulator:
            return None

        return self.modulator.get_policy_summary()

    def _emit_introspection_alert(self, introspection: AffectIntrospection):
        """
        Emit introspection as an alert for KLoROS awareness.

        This surfaces negative affect analysis to the alert system so KLoROS
        can consciously decide how to respond.
        """
        try:
            # Try to access alert manager if available
            # This will be caught by KLoROS's alert system integration
            print(f"\n[consciousness] ⚠️ INTROSPECTION ALERT")
            print(f"  Urgency: {introspection.urgency.value.upper()}")
            print(f"  Can self-remediate: {introspection.can_self_remediate}")
            print(f"  User intervention needed: {introspection.user_intervention_needed}")

            # Format as structured data for alert system
            alert_data = {
                'category': 'affective_state',
                'hypothesis': 'NEGATIVE_AFFECT_DETECTED',
                'evidence': introspection.evidence,
                'autonomous_actions': introspection.autonomous_actions,
                'requires_user': introspection.requires_user,
                'urgency': introspection.urgency.value,
                'can_self_remediate': introspection.can_self_remediate
            }

            # TODO: Hook into alert manager when available
            # For now, just log it
        except Exception as e:
            print(f"[consciousness] Failed to emit introspection alert: {e}")

    def get_combined_state(self) -> Dict:
        """
        Get combined Phase 1 + Phase 2 state.

        Returns:
            Dictionary with both affective core and interoception state
        """
        state = {}

        # Phase 1 state
        if self.phase1_enabled and self.affective_core:
            state['phase1'] = self.affective_core.introspect()

        # Phase 2 state
        if self.phase2_enabled and self.current_affect:
            state['phase2'] = {
                'affect': {
                    'valence': self.current_affect.valence,
                    'arousal': self.current_affect.arousal,
                    'dominance': self.current_affect.dominance,
                    'uncertainty': self.current_affect.uncertainty,
                    'fatigue': self.current_affect.fatigue,
                    'curiosity': self.current_affect.curiosity,
                },
                'signals': self.monitor.get_signal_summary() if self.monitor else {},
                'policy': self.get_policy_state(),
                'last_report': self.last_report.to_dict() if self.last_report else None,
                'introspection': {
                    'active': self.last_introspection is not None,
                    'urgency': self.last_introspection.urgency.value if self.last_introspection else None,
                    'can_self_remediate': self.last_introspection.can_self_remediate if self.last_introspection else None,
                    'user_intervention_needed': self.last_introspection.user_intervention_needed if self.last_introspection else None
                } if self.last_introspection else None
            }

        return state

    def process_task_outcome(self,
                             task_type: str,
                             success: bool,
                             duration: Optional[float] = None,
                             error: Optional[str] = None) -> Optional[AffectiveReport]:
        """
        Process task execution outcome and trigger affective introspection.

        This is the primary integration point for the affective action system.
        Task completion events trigger signal updates, appraisal, introspection,
        and potentially UMN signal emission for autonomous responses.

        Args:
            task_type: Type of task executed (e.g., 'tool_call', 'analysis', 'planning')
            success: Whether task succeeded
            duration: Task execution time in seconds (optional)
            error: Error message if task failed (optional)

        Returns:
            AffectiveReport if Phase 2 enabled, None otherwise
        """
        if not self.phase2_enabled or not self.monitor:
            return None

        self.monitor.record_task_outcome(success=success, retries=0)

        if error:
            self.monitor.record_exception()

        if duration is not None:
            self.monitor.update_tool_latency(duration)

        if success:
            if self.affective_core:
                self.affective_core.emotions.SEEKING = min(
                    1.0,
                    self.affective_core.emotions.SEEKING + 0.05
                )
        else:
            if self.affective_core:
                self.affective_core.emotions.RAGE = min(
                    1.0,
                    self.affective_core.emotions.RAGE + 0.1
                )

        report = self.process_and_report()

        return report

    def process_discovery(self,
                         discovery_type: str,
                         significance: float,
                         context: Optional[str] = None) -> Optional[AffectiveReport]:
        """
        Process curiosity discovery event and trigger affective introspection.

        Handles pattern discoveries, answered questions, and integrated learning.
        Discovery events increase SEEKING (reward satisfaction) and may increase
        PLAY (joy of discovery) for high-significance discoveries.

        Args:
            discovery_type: Type of discovery ("pattern", "question_answered", "learning_integrated")
            significance: Significance level 0.0-1.0 of the discovery
            context: Optional context string describing the discovery

        Returns:
            AffectiveReport if Phase 2 enabled, None otherwise
        """
        if not self.phase2_enabled or not self.monitor:
            return None

        self.monitor.record_task_outcome(success=True, retries=0)

        if self.affective_core:
            self.affective_core.emotions.SEEKING = min(
                1.0,
                self.affective_core.emotions.SEEKING + 0.08
            )

            if significance > 0.8:
                self.affective_core.emotions.PLAY = min(
                    1.0,
                    self.affective_core.emotions.PLAY + 0.1
                )

        report = self.process_and_report()

        return report

    def process_resource_pressure(self,
                                  pressure_type: str,
                                  level: float,
                                  evidence: Optional[List[str]] = None) -> Optional[AffectiveReport]:
        """
        Process resource pressure event and trigger affective introspection.

        Handles system health events including memory pressure, CPU strain, context
        overflow, and error patterns. Resource pressure triggers threat awareness
        (FEAR) and may trigger crisis state (PANIC) for critical pressure, or
        problem-solving activation (SEEKING) for moderate pressure.

        Args:
            pressure_type: Type of pressure ("memory", "cpu", "context", "errors")
            level: Pressure level 0.0-1.0 (1.0 = critical)
            evidence: Optional list of evidence strings describing the pressure

        Returns:
            AffectiveReport if Phase 2 enabled, None otherwise
        """
        if not self.phase2_enabled or not self.monitor:
            return None

        self.monitor.record_task_outcome(success=False, retries=0)

        if self.affective_core:
            self.affective_core.emotions.FEAR = min(
                1.0,
                self.affective_core.emotions.FEAR + (0.10 * level)
            )

            if level > 0.9:
                self.affective_core.emotions.PANIC = min(
                    1.0,
                    self.affective_core.emotions.PANIC + 0.15
                )
            elif level > 0.7:
                self.affective_core.emotions.SEEKING = min(
                    1.0,
                    self.affective_core.emotions.SEEKING + 0.08
                )

        report = self.process_and_report()

        return report

    def reset(self):
        """Reset all systems to baseline."""
        if self.phase1_enabled and self.affective_core:
            # Phase 1 doesn't have a reset, create new instance
            self.affective_core = AffectiveCore()

        if self.phase2_enabled:
            self.monitor = InteroceptiveMonitor()
            self.appraiser = AppraisalSystem()
            self.modulator = ModulationSystem()
            self.guardrails = GuardrailSystem()

        self.current_affect = None
        self.current_signals = None
        self.last_report = None
