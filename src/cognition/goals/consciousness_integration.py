"""
Consciousness Integration - Goal System ↔ Affective System

Bridges goal system with consciousness/emotional architecture:
- Goal events → affective events
- Goal pressure → homeostatic pressure → emotions
- Progress deltas → DriveLoop dynamics (Phase 3)
"""

import logging
from typing import TYPE_CHECKING, Optional, Dict

if TYPE_CHECKING:
    from src.cognition.mind.consciousness.integrated import IntegratedConsciousness
    from .manager import GoalManager

logger = logging.getLogger(__name__)


class GoalConsciousnessIntegrator:
    """
    Integrates goal system with consciousness architecture.

    Workflow:
        1. Goal events (set, progress, blocked, completed) →
        2. Affective events processed by consciousness →
        3. Emotions modulate behavior (via modulation system)
    """

    def __init__(
        self,
        consciousness: 'IntegratedConsciousness',
        goal_manager: 'GoalManager'
    ):
        """
        Initialize integrator.

        Args:
            consciousness: Integrated consciousness instance
            goal_manager: Goal manager instance
        """
        self.consciousness = consciousness
        self.goal_manager = goal_manager

        # Register as event callback
        goal_manager.register_event_callback(self._handle_goal_event)

        logger.info("[goal_consciousness] Integrator initialized")

    def _handle_goal_event(self, event_type: str, metadata: Dict):
        """
        Handle goal event and translate to affective processing.

        Args:
            event_type: Goal event type
            metadata: Event context
        """
        # Map goal events to affective events
        affective_event_map = {
            'goal_set': 'goal_accepted',
            'goal_activated': 'goal_activated',
            'goal_progress': 'goal_progress',
            'goal_blocked': 'goal_blocked',
            'goal_completed': 'goal_completed',
            'goal_failed': 'goal_failed',
            'goal_abandoned': 'goal_abandoned',
            'goal_paused': 'goal_paused',
            'goal_resumed': 'goal_resumed',
            'goal_unblocked': 'goal_unblocked'
        }

        affective_event = affective_event_map.get(event_type)
        if not affective_event:
            return

        # Process through consciousness Phase 1 (affective core)
        if self.consciousness.phase1_enabled and self.consciousness.affective_core:
            self.consciousness.process_event_phase1(affective_event, metadata)

        # Update signals for Phase 2 (interoception/appraisal)
        if self.consciousness.phase2_enabled:
            self._update_signals_for_event(event_type, metadata)

        # Update Phase 3 dynamics if enabled
        if hasattr(self.consciousness, 'phase3_enabled') and self.consciousness.phase3_enabled:
            self._update_dynamics_for_event(event_type, metadata)

    def _update_signals_for_event(self, event_type: str, metadata: Dict):
        """
        Update interoceptive signals based on goal event with hybrid affective rewards.

        Args:
            event_type: Goal event type
            metadata: Event context
        """
        # Map goal events to signal updates
        if event_type == 'goal_progress':
            progress_delta = metadata.get('progress_delta', 0.0)
            if progress_delta > 0:
                # Positive progress → success signal, increased confidence
                self.consciousness.update_signals(
                    success=True,
                    confidence=0.7 + (progress_delta * 0.3),
                    novelty=0.0  # Progress is expected
                )
                # Hybrid affective reward: progress reward
                if self.consciousness.affective_core:
                    satisfaction_boost = 0.15 * progress_delta
                    valence_boost = 0.1 * progress_delta
                    self.consciousness.affective_core.emotions.SATISFACTION = min(
                        1.0,
                        self.consciousness.affective_core.emotions.SATISFACTION + satisfaction_boost
                    )
                    self.consciousness.affective_core.current_affect.valence = min(
                        1.0,
                        self.consciousness.affective_core.current_affect.valence + valence_boost
                    )
                    logger.debug(f"[goal_consciousness] Progress reward: +{satisfaction_boost:.3f} SATISFACTION, +{valence_boost:.3f} valence")
            elif progress_delta < 0:
                # Negative progress → failure signal
                self.consciousness.update_signals(
                    success=False,
                    confidence=0.4,
                    surprise=0.3  # Unexpected regression
                )
                # Affective penalty for regression
                if self.consciousness.affective_core:
                    self.consciousness.affective_core.emotions.FRUSTRATION = min(
                        1.0,
                        self.consciousness.affective_core.emotions.FRUSTRATION + 0.1
                    )

        elif event_type == 'goal_blocked':
            # Blocked → high uncertainty, low confidence
            self.consciousness.update_signals(
                success=False,
                confidence=0.3,
                uncertainty=0.8,
                retries=metadata.get('retry_count', 0)
            )
            # Increase frustration on block
            if self.consciousness.affective_core:
                self.consciousness.affective_core.emotions.FRUSTRATION = min(
                    1.0,
                    self.consciousness.affective_core.emotions.FRUSTRATION + 0.15
                )

        elif event_type == 'goal_completed':
            # Completion → high success, high confidence
            self.consciousness.update_signals(
                success=True,
                confidence=0.9,
                novelty=0.2  # Achievement is somewhat novel
            )
            # Completion reward with pressure relief
            if self.consciousness.affective_core:
                goal_pressure = metadata.get('goal_pressure', 0.0)
                arousal_relief = goal_pressure * 0.8
                self.consciousness.affective_core.emotions.SATISFACTION = min(
                    1.0,
                    self.consciousness.affective_core.emotions.SATISFACTION + 0.4
                )
                self.consciousness.affective_core.current_affect.valence = min(
                    1.0,
                    self.consciousness.affective_core.current_affect.valence + 0.3
                )
                if arousal_relief > 0:
                    self.consciousness.affective_core.current_affect.arousal = max(
                        0.0,
                        self.consciousness.affective_core.current_affect.arousal - arousal_relief
                    )
                logger.debug(f"[goal_consciousness] Completion reward: +0.4 SATISFACTION, +0.3 valence, -{arousal_relief:.3f} arousal relief")
                self._log_completion_to_memory(metadata)

        elif event_type == 'goal_failed':
            # Failure → error signal
            self.consciousness.update_signals(
                success=False,
                confidence=0.2,
                exception=True
            )
            # Affective penalty for failure
            if self.consciousness.affective_core:
                self.consciousness.affective_core.emotions.FRUSTRATION = min(
                    1.0,
                    self.consciousness.affective_core.emotions.FRUSTRATION + 0.2
                )

    def _update_dynamics_for_event(self, event_type: str, metadata: Dict):
        """
        Update Phase 3 dynamics (DriveLoops, etc.) based on goal event.

        Args:
            event_type: Goal event type
            metadata: Event context
        """
        if not hasattr(self.consciousness, 'dynamics'):
            return

        goal_id = metadata.get('goal_id')
        if not goal_id:
            return

        dynamics = self.consciousness.dynamics

        # Create or update DriveLoop for this goal
        if event_type == 'goal_set' or event_type == 'goal_activated':
            dynamics.create_drive_loop(goal_id)

        # Update DriveLoop with progress delta
        elif event_type == 'goal_progress':
            progress_delta = metadata.get('progress_delta', 0.0)
            if goal_id in dynamics.drive_loops:
                # Get current emotional state
                emotional_state = self.consciousness.affective_core.emotions if self.consciousness.affective_core else None
                if emotional_state:
                    dynamics.drive_loops[goal_id].update(emotional_state, progress_delta)

    def sync_goal_homeostasis(self):
        """
        Sync active goals as homeostatic variables in consciousness.

        Each active goal becomes a homeostatic variable creating
        affective pressure based on progress.
        """
        if not self.consciousness.phase1_enabled or not self.consciousness.affective_core:
            return

        # Get active goals
        active_goals = self.goal_manager.get_active_goals()

        # Add goal homeostatic variables to affective core
        for goal in active_goals:
            # Create homeostatic variable name
            var_name = f"goal_{goal.id}"

            # Check if already exists
            if var_name in self.consciousness.affective_core.homeostasis:
                # Update existing
                self.consciousness.affective_core.homeostasis[var_name].current = goal.progress
            else:
                # Create new homeostatic variable
                from src.cognition.mind.consciousness.models import HomeostaticVariable
                self.consciousness.affective_core.homeostasis[var_name] = HomeostaticVariable(
                    name=var_name,
                    current=goal.progress,
                    target=goal.homeostatic_target,
                    tolerance=goal.homeostatic_tolerance
                )

        # Generate homeostatic pressure → emotions
        pressures = self.consciousness.affective_core.generate_homeostatic_pressure()

        if pressures:
            logger.debug(f"[goal_consciousness] Goal pressures: {pressures}")

    def _log_completion_to_memory(self, metadata: Dict):
        """
        Log goal completion as episodic memory event.

        Args:
            metadata: Goal event metadata containing goal_id, progress, etc.
        """
        try:
            from datetime import datetime, timezone

            goal_id = metadata.get('goal_id', 'unknown')
            goal_description = metadata.get('goal_description', '')
            final_progress = metadata.get('goal_progress', 1.0)

            goal = self.goal_manager.goals.get(goal_id)
            if not goal:
                logger.warning(f"[goal_consciousness] Goal {goal_id} not found for memory logging")
                return

            alignment = goal.properties.alignment_with_purpose if goal.properties else 0.5
            impact = goal.properties.impact if goal.properties else 0.5

            event_data = {
                'goal_id': goal_id,
                'description': goal_description,
                'final_progress': final_progress,
                'alignment': alignment,
                'impact': impact,
                'completion_time': datetime.now(timezone.utc).isoformat()
            }

            if hasattr(self.consciousness, 'conversation_logger') and self.consciousness.conversation_logger:
                try:
                    conversation_logger = self.consciousness.conversation_logger
                    log_entry = f"GOAL_COMPLETED: {goal_description} (alignment={alignment:.2f}, impact={impact:.2f})"

                    if hasattr(conversation_logger, 'log_event'):
                        conversation_logger.log_event(
                            event_type='goal_completed',
                            event_data=event_data,
                            metadata={'source': 'goal_system'}
                        )
                    elif hasattr(conversation_logger, 'log_turn'):
                        conversation_logger.log_turn(
                            user_query=f"[SYSTEM] Goal {goal_id} completed",
                            system_response=log_entry,
                            metadata={'goal_id': goal_id, 'goal_completed': True, **event_data}
                        )

                    logger.info(f"[goal_consciousness] Goal completion logged to memory: {goal_id}")
                except Exception as log_err:
                    logger.debug(f"[goal_consciousness] Could not log completion to conversation logger: {log_err}")

        except ImportError:
            logger.debug("[goal_consciousness] Episodic memory not available, skipping completion logging")
        except Exception as e:
            logger.error(f"[goal_consciousness] Error logging goal completion to memory: {e}")

    def get_goal_affect_mapping(self) -> Dict[str, Dict]:
        """
        Get mapping of goals to their affective consequences.

        Returns:
            Dict of {goal_id: {pressure, emotions, affect}}
        """
        if not self.consciousness.affective_core:
            return {}

        active_goals = self.goal_manager.get_active_goals()
        mapping = {}

        for goal in active_goals:
            var_name = f"goal_{goal.id}"
            homeostatic_var = self.consciousness.affective_core.homeostasis.get(var_name)

            if homeostatic_var:
                mapping[goal.id] = {
                    'goal_description': goal.description,
                    'progress': goal.progress,
                    'pressure': homeostatic_var.pressure,
                    'satisfied': homeostatic_var.satisfied,
                    'state': goal.state.value
                }

        return mapping


def integrate_goals_with_consciousness(
    consciousness: 'IntegratedConsciousness',
    goal_manager: 'GoalManager'
) -> GoalConsciousnessIntegrator:
    """
    One-shot integration of goal system with consciousness.

    Args:
        consciousness: Integrated consciousness instance
        goal_manager: Goal manager instance

    Returns:
        Integrator instance
    """
    integrator = GoalConsciousnessIntegrator(consciousness, goal_manager)

    # Initial sync of existing goals
    integrator.sync_goal_homeostasis()

    logger.info("[goal_consciousness] Goals integrated with consciousness")
    return integrator
