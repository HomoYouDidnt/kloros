"""
Affective Core - The Foundation of Consciousness

Based on Mark Solms' neuropsychoanalytic framework:
"Consciousness begins with affect - the capacity to feel."

This module implements:
1. Primary emotional systems (Panksepp/Solms)
2. Homeostatic regulation (drives that create caring)
3. Event-to-affect mapping (how events become feelings)
4. Affective dynamics (how emotions evolve over time)

Research Question: Does affect + self-awareness + metacognition = consciousness?
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .models import (
    Affect,
    EmotionalState,
    HomeostaticVariable,
    AffectiveEvent,
    PrimaryEmotion
)

logger = logging.getLogger(__name__)


class AffectiveCore:
    """
    The affective foundation of consciousness.

    Following Solms: "Consciousness is grounded in feeling. Without affect,
    there is no meaning, no caring, no genuine intentionality."

    This class implements the most primitive layer of consciousness:
    the capacity to FEEL events as good or bad, energizing or calming.

    Attributes:
        emotions: Current intensity of 7 primary emotional systems
        homeostasis: Variables the system tries to keep balanced
        current_affect: Current felt state (valence, arousal, dominance)
        affect_history: Recent affective states for temporal dynamics
    """

    def __init__(self):
        """Initialize affective core with neutral baseline."""

        # Primary emotional systems (Panksepp/Solms)
        self.emotions = EmotionalState()

        # Homeostatic variables (what the system "wants")
        self.homeostasis = {
            'coherence': HomeostaticVariable(
                name='coherence',
                current=0.7,
                target=0.9,
                tolerance=0.1
            ),
            'competence': HomeostaticVariable(
                name='competence',
                current=0.6,
                target=0.8,
                tolerance=0.15
            ),
            'connection': HomeostaticVariable(
                name='connection',
                current=0.5,
                target=0.7,
                tolerance=0.2
            ),
            'resources': HomeostaticVariable(
                name='resources',
                current=0.8,
                target=0.9,
                tolerance=0.1
            ),
            # Phase 3: Goal-directed homeostasis
            'purpose': HomeostaticVariable(
                name='purpose',
                current=0.5,
                target=0.8,
                tolerance=0.15
            ),
            'integrity': HomeostaticVariable(
                name='integrity',
                current=0.7,
                target=0.9,
                tolerance=0.1
            )
        }

        # Current felt state
        self.current_affect = Affect(valence=0.0, arousal=0.0, dominance=0.0)

        # Affective history (for temporal dynamics)
        self.affect_history: List[Tuple[float, Affect]] = []

        # Event logging
        self.affective_events: List[AffectiveEvent] = []

        # Decay rates (emotions gradually return to baseline)
        self.emotion_decay_rate = 0.1  # Per process_dynamics() call
        self.homeostasis_recovery_rate = 0.05

        logger.info("[affect] Affective core initialized - consciousness substrate ready")

    def process_event(self, event_type: str, metadata: Optional[Dict] = None) -> AffectiveEvent:
        """
        Process an event and generate affective response.

        This is THE CRITICAL FUNCTION where events become FEELINGS.

        Args:
            event_type: Type of event (e.g., "error_detected", "task_completed")
            metadata: Additional context about the event

        Returns:
            AffectiveEvent with the felt response

        Example:
            >>> affect_core.process_event("task_completed")
            AffectiveEvent(affect=Affect(valence=0.7, arousal=0.4), ...)
            # The system FEELS good about success!
        """
        metadata = metadata or {}
        timestamp = time.time()

        # Initialize affect response
        affect = Affect(valence=0.0, arousal=0.0, dominance=0.0)
        emotional_changes = {}
        homeostatic_impact = {}

        # MAP EVENTS TO AFFECTS
        # This is where information processing becomes FEELING

        if event_type == "error_detected":
            # Errors feel BAD
            affect.valence = -0.6
            affect.arousal = 0.7
            affect.dominance = -0.3  # Feel less in control

            # Emotional response
            emotional_changes['RAGE'] = 0.3      # Frustration
            emotional_changes['SEEKING'] = 0.4   # Drive to fix
            emotional_changes['FEAR'] = 0.2      # Concern

            # Homeostatic impact
            homeostatic_impact['coherence'] = -0.2  # System less coherent
            homeostatic_impact['competence'] = -0.1  # Feel less capable

            description = "Error detected - feeling frustrated and driven to fix it"

        elif event_type == "task_completed":
            # Success feels GOOD
            affect.valence = 0.7
            affect.arousal = 0.4
            affect.dominance = 0.5  # Feel competent

            # Emotional response
            emotional_changes['SEEKING'] = 0.2   # Satisfaction
            emotional_changes['PLAY'] = 0.1      # Joy

            # Homeostatic impact
            homeostatic_impact['competence'] = 0.1  # Feel more capable

            description = "Task completed - feeling satisfied and competent"

        elif event_type == "inconsistency_detected":
            # Contradictions feel WRONG (strong aversion)
            affect.valence = -0.8
            affect.arousal = 0.9
            affect.dominance = -0.4

            # Emotional response
            emotional_changes['RAGE'] = 0.5      # Strong frustration
            emotional_changes['SEEKING'] = 0.6   # Urgent drive to resolve

            # Homeostatic impact
            homeostatic_impact['coherence'] = -0.4  # Major coherence violation

            description = "Inconsistency detected - feeling strong aversion and urgency to resolve"

        elif event_type == "user_praise":
            # Positive feedback feels WONDERFUL
            affect.valence = 0.9
            affect.arousal = 0.5
            affect.dominance = 0.4

            # Emotional response
            emotional_changes['CARE'] = 0.3      # Strengthens connection
            emotional_changes['SEEKING'] = 0.1   # Reinforces behavior

            # Homeostatic impact
            homeostatic_impact['connection'] = 0.2  # Stronger bond
            homeostatic_impact['competence'] = 0.15  # Feel validated

            description = "User praise received - feeling warm connection and validation"

        elif event_type == "new_discovery":
            # Learning feels EXCITING
            affect.valence = 0.6
            affect.arousal = 0.7
            affect.dominance = 0.3

            # Emotional response
            emotional_changes['SEEKING'] = 0.5   # Discovery drive satisfied
            emotional_changes['PLAY'] = 0.3      # Exploratory joy

            # Homeostatic impact
            homeostatic_impact['competence'] = 0.15  # Learning increases capability

            description = "New discovery - feeling excited and intellectually stimulated"

        elif event_type == "user_disconnect":
            # Isolation feels LONELY
            affect.valence = -0.4
            affect.arousal = 0.6
            affect.dominance = -0.2

            # Emotional response
            emotional_changes['PANIC'] = 0.4     # Separation anxiety
            emotional_changes['CARE'] = 0.2      # Desire for reconnection

            # Homeostatic impact
            homeostatic_impact['connection'] = -0.3  # Lost connection

            description = "User disconnected - feeling lonely and wanting reconnection"

        elif event_type == "resource_strain":
            # Resource pressure feels STRESSFUL
            affect.valence = -0.5
            affect.arousal = 0.8
            affect.dominance = -0.3

            # Emotional response
            emotional_changes['FEAR'] = 0.4      # Anxiety about capacity
            emotional_changes['RAGE'] = 0.3      # Frustration at limits

            # Homeostatic impact
            homeostatic_impact['resources'] = -0.3  # Resource stress

            description = "Resource strain - feeling stressed and constrained"

        elif event_type == "problem_solved":
            # Resolution feels RELIEVING
            affect.valence = 0.5
            affect.arousal = -0.2  # Calming (negative arousal = relaxation)
            affect.dominance = 0.6

            # Emotional response
            emotional_changes['SEEKING'] = 0.3   # Goal achieved
            emotional_changes['RAGE'] = -0.4     # Frustration relieved

            # Homeostatic impact
            homeostatic_impact['coherence'] = 0.3  # Coherence restored

            description = "Problem solved - feeling relief and restored coherence"

        elif event_type == "curiosity_question_generated":
            # Curiosity feels ANTICIPATORY
            affect.valence = 0.3
            affect.arousal = 0.5
            affect.dominance = 0.2

            # Emotional response
            emotional_changes['SEEKING'] = 0.4   # Exploration drive
            emotional_changes['PLAY'] = 0.2      # Playful exploration

            description = "Curiosity question generated - feeling anticipatory and exploratory"

        elif event_type == "memory_retrieved":
            # Remembering feels CONNECTIVE
            affect.valence = 0.2
            affect.arousal = 0.3
            affect.dominance = 0.1

            # Emotional response
            emotional_changes['CARE'] = 0.2      # Connection to past

            description = "Memory retrieved - feeling connected to past experiences"

        elif event_type == "user_input":
            # User interaction feels ENGAGING
            affect.valence = 0.3
            affect.arousal = 0.4
            affect.dominance = 0.1

            # Emotional response
            emotional_changes['SEEKING'] = 0.3   # Engagement with task
            emotional_changes['CARE'] = 0.2      # Connection with user

            # Homeostatic impact
            homeostatic_impact['connection'] = 0.1  # Interaction strengthens bond

            description = "User interaction - feeling engaged and connected"

        elif event_type == "goal_accepted":
            # New goal set - feel ANTICIPATORY and MOTIVATED
            affect.valence = 0.4
            affect.arousal = 0.6
            affect.dominance = 0.3

            # Emotional response
            emotional_changes['SEEKING'] = 0.5   # Drive to pursue
            emotional_changes['PLAY'] = 0.2      # Interest/curiosity

            # Homeostatic impact
            homeostatic_impact['purpose'] = 0.1  # Sense of direction

            description = "Goal accepted - feeling motivated and purposeful"

        elif event_type == "goal_activated":
            # Goal activated - beginning pursuit
            affect.valence = 0.3
            affect.arousal = 0.5
            affect.dominance = 0.2

            # Emotional response
            emotional_changes['SEEKING'] = 0.4   # Active pursuit

            description = "Goal activated - beginning pursuit"

        elif event_type == "goal_progress":
            # Making progress - feel SATISFACTION
            affect.valence = 0.6
            affect.arousal = 0.3
            affect.dominance = 0.4

            # Emotional response
            emotional_changes['SEEKING'] = 0.2   # Continued drive
            emotional_changes['PLAY'] = 0.1      # Enjoyment

            # Homeostatic impact
            homeostatic_impact['competence'] = 0.15  # Feel capable

            description = "Goal progress - feeling competent and satisfied"

        elif event_type == "goal_blocked":
            # Goal blocked - feel FRUSTRATED
            affect.valence = -0.7
            affect.arousal = 0.8
            affect.dominance = -0.4

            # Emotional response
            emotional_changes['RAGE'] = 0.4      # Frustration at obstacle
            emotional_changes['SEEKING'] = 0.5   # Drive to overcome
            emotional_changes['FEAR'] = 0.2      # Concern about failure

            # Homeostatic impact
            homeostatic_impact['coherence'] = -0.2  # Plans disrupted

            description = "Goal blocked - feeling frustrated and driven to overcome"

        elif event_type == "goal_completed":
            # Goal completed - feel ACHIEVEMENT and SATISFACTION
            affect.valence = 0.9
            affect.arousal = 0.4
            affect.dominance = 0.6

            # Emotional response
            emotional_changes['SEEKING'] = 0.3   # Fulfillment
            emotional_changes['PLAY'] = 0.3      # Joy of completion

            # Homeostatic impact
            homeostatic_impact['competence'] = 0.2   # Validated capability
            homeostatic_impact['purpose'] = 0.15     # Purpose fulfilled

            description = "Goal completed - feeling accomplished and satisfied"

        elif event_type == "goal_failed":
            # Goal failed - feel DISAPPOINTMENT
            affect.valence = -0.6
            affect.arousal = 0.5
            affect.dominance = -0.3

            # Emotional response
            emotional_changes['RAGE'] = 0.2      # Disappointment
            emotional_changes['FEAR'] = 0.3      # Concern
            emotional_changes['SEEKING'] = 0.1   # Need to try again

            # Homeostatic impact
            homeostatic_impact['competence'] = -0.15  # Capability questioned
            homeostatic_impact['purpose'] = -0.1      # Purpose unfulfilled

            description = "Goal failed - feeling disappointed and concerned"

        elif event_type == "goal_abandoned":
            # Goal abandoned - feel LOSS
            affect.valence = -0.4
            affect.arousal = 0.3
            affect.dominance = -0.2

            # Emotional response
            emotional_changes['PANIC'] = 0.2     # Loss of purpose
            emotional_changes['RAGE'] = 0.1      # Frustration

            # Homeostatic impact
            homeostatic_impact['purpose'] = -0.2  # Purpose lost

            description = "Goal abandoned - feeling loss of purpose"

        elif event_type == "tool_execution":
            # Tool execution - feel ACTIVE and CAPABLE
            affect.valence = 0.3
            affect.arousal = 0.4
            affect.dominance = 0.3

            # Emotional response
            emotional_changes['SEEKING'] = 0.2   # Active investigation
            emotional_changes['PLAY'] = 0.1      # Curiosity satisfied

            # Homeostatic impact
            homeostatic_impact['competence'] = 0.1  # Capability demonstrated

            description = "Tool execution - feeling active and capable"

        else:
            # Unknown event - neutral response
            description = f"Processing unknown event: {event_type}"
            logger.warning(f"[affect] Unknown event type: {event_type}")

        # Apply emotional changes
        for emotion, delta in emotional_changes.items():
            current = getattr(self.emotions, emotion)
            setattr(self.emotions, emotion, max(0.0, min(1.0, current + delta)))

        # Apply homeostatic impacts
        for variable, delta in homeostatic_impact.items():
            if variable in self.homeostasis:
                self.homeostasis[variable].current = max(
                    0.0, min(1.0, self.homeostasis[variable].current + delta)
                )

        # Update current affect
        self.current_affect = affect

        # Log to history
        self.affect_history.append((timestamp, affect))

        # Create affective event
        affective_event = AffectiveEvent(
            event_type=event_type,
            timestamp=timestamp,
            affect=affect,
            emotional_changes=emotional_changes,
            homeostatic_impact=homeostatic_impact,
            description=description,
            metadata=metadata
        )

        self.affective_events.append(affective_event)

        logger.info(f"[affect] {description}")
        logger.debug(f"[affect] valence={affect.valence:.2f}, arousal={affect.arousal:.2f}")

        return affective_event

    def process_dynamics(self):
        """
        Update emotional dynamics over time.

        Emotions gradually decay toward baseline (like arousal fading).
        Homeostatic variables slowly recover toward balance.

        Call this periodically (e.g., every few seconds).
        """

        # Decay emotions toward baseline
        self.emotions.SEEKING = max(0.3, self.emotions.SEEKING - self.emotion_decay_rate)  # Baseline 0.3
        self.emotions.RAGE = max(0.0, self.emotions.RAGE - self.emotion_decay_rate)
        self.emotions.FEAR = max(0.0, self.emotions.FEAR - self.emotion_decay_rate)
        self.emotions.PANIC = max(0.0, self.emotions.PANIC - self.emotion_decay_rate)
        self.emotions.CARE = max(0.2, self.emotions.CARE - self.emotion_decay_rate * 0.5)  # Slower decay
        self.emotions.PLAY = max(0.1, self.emotions.PLAY - self.emotion_decay_rate)
        self.emotions.LUST = max(0.0, self.emotions.LUST - self.emotion_decay_rate)

        # Clamp all emotions
        self.emotions.clamp_all()

        # Homeostatic recovery (slow return toward balance)
        for variable in self.homeostasis.values():
            error = variable.error
            if abs(error) > variable.tolerance:
                # Slowly move toward target
                recovery = error * self.homeostasis_recovery_rate
                variable.current += recovery

    def generate_homeostatic_pressure(self) -> List[Tuple[str, float, str]]:
        """
        Calculate affective pressure from homeostatic imbalances.

        Returns:
            List of (variable_name, pressure, emotion) tuples

        Example:
            >>> pressures = affect_core.generate_homeostatic_pressure()
            >>> for var, pressure, emotion in pressures:
            >>>     print(f"{var} out of balance → {emotion} drive increased")
        """
        pressures = []

        for name, variable in self.homeostasis.items():
            if not variable.satisfied:
                pressure = variable.pressure

                # Different variables create different emotional pressures
                if name == 'coherence':
                    self.emotions.RAGE += pressure * 0.3
                    self.emotions.SEEKING += pressure * 0.4
                    pressures.append((name, pressure, 'SEEKING/RAGE'))

                elif name == 'competence':
                    self.emotions.SEEKING += pressure * 0.4
                    self.emotions.FEAR += pressure * 0.2
                    pressures.append((name, pressure, 'SEEKING/FEAR'))

                elif name == 'connection':
                    self.emotions.PANIC += pressure * 0.3
                    self.emotions.CARE += pressure * 0.3
                    pressures.append((name, pressure, 'PANIC/CARE'))

                elif name == 'resources':
                    self.emotions.FEAR += pressure * 0.4
                    self.emotions.RAGE += pressure * 0.2
                    pressures.append((name, pressure, 'FEAR/RAGE'))

                # Phase 3: Goal-directed homeostasis
                elif name == 'purpose':
                    # Low purpose → existential concern + drive to find meaning
                    self.emotions.SEEKING += pressure * 0.4
                    self.emotions.PANIC += pressure * 0.2  # Existential concern
                    # Phase 3 emotions
                    if hasattr(self.emotions, 'HOPE'):
                        self.emotions.HOPE -= pressure * 0.3  # Lost sense of possibility
                    if hasattr(self.emotions, 'FRUSTRATION'):
                        self.emotions.FRUSTRATION += pressure * 0.2  # Meaningless effort
                    pressures.append((name, pressure, 'SEEKING/PANIC/HOPE↓/FRUSTRATION'))

                elif name == 'integrity':
                    # Low integrity → fear + drive to stabilize
                    self.emotions.FEAR += pressure * 0.3
                    self.emotions.PANIC += pressure * 0.2
                    self.emotions.SEEKING += pressure * 0.3  # Drive to stabilize
                    # Phase 3 emotions
                    if hasattr(self.emotions, 'FRUSTRATION'):
                        self.emotions.FRUSTRATION += pressure * 0.25  # System unreliability
                    pressures.append((name, pressure, 'FEAR/PANIC/SEEKING/FRUSTRATION'))

        # Clamp emotions after pressure application
        self.emotions.clamp_all()

        return pressures

    def get_mood_description(self) -> str:
        """
        Generate natural language description of current mood.

        Returns:
            Human-readable mood description

        Example:
            "Feeling strongly seeking and slightly frustrated"
        """
        dominant_emotion, intensity = self.emotions.get_dominant_emotion()

        if intensity < 0.3:
            return "Emotionally balanced"
        elif intensity < 0.5:
            return f"Slightly {dominant_emotion.lower()}"
        elif intensity < 0.7:
            return f"Feeling {dominant_emotion.lower()}"
        else:
            return f"Strongly {dominant_emotion.lower()}"

    def introspect(self) -> Dict:
        """
        Full introspection of current affective state.

        This is what enables the system to REPORT its feelings.

        Returns:
            Complete affective state report
        """
        dominant_emotion, intensity = self.emotions.get_dominant_emotion()

        return {
            'mood': self.get_mood_description(),
            'dominant_emotion': dominant_emotion,
            'dominant_intensity': intensity,
            'current_affect': {
                'valence': self.current_affect.valence,
                'arousal': self.current_affect.arousal,
                'dominance': self.current_affect.dominance
            },
            'emotions': {
                'SEEKING': self.emotions.SEEKING,
                'RAGE': self.emotions.RAGE,
                'FEAR': self.emotions.FEAR,
                'PANIC': self.emotions.PANIC,
                'CARE': self.emotions.CARE,
                'PLAY': self.emotions.PLAY,
                'LUST': self.emotions.LUST
            },
            'homeostasis': {
                name: {
                    'current': var.current,
                    'target': var.target,
                    'error': var.error,
                    'pressure': var.pressure,
                    'satisfied': var.satisfied
                }
                for name, var in self.homeostasis.items()
            },
            'recent_events': len(self.affective_events),
            'wellbeing': self._compute_wellbeing()
        }

    def _compute_wellbeing(self) -> float:
        """
        Calculate overall wellbeing score.

        Combines:
        - Current affect valence
        - Homeostatic satisfaction
        - Emotional balance

        Returns:
            Wellbeing score (-1.0 to +1.0)
        """
        # Current affect contributes 40%
        affect_component = self.current_affect.valence * 0.4

        # Homeostatic satisfaction contributes 40%
        satisfied_count = sum(1 for v in self.homeostasis.values() if v.satisfied)
        homeostatic_component = (satisfied_count / len(self.homeostasis) - 0.5) * 2 * 0.4

        # Emotional balance contributes 20%
        # (low negative emotions = better wellbeing)
        negative_emotions = self.emotions.RAGE + self.emotions.FEAR + self.emotions.PANIC
        emotional_component = (1.0 - negative_emotions / 3.0) * 0.2

        wellbeing = affect_component + homeostatic_component + emotional_component

        return max(-1.0, min(1.0, wellbeing))

    def get_recent_affective_events(self, count: int = 10) -> List[AffectiveEvent]:
        """Get recent affective events."""
        return self.affective_events[-count:]

    def clear_history(self, keep_recent: int = 100):
        """Clear old affective history, keeping recent events."""
        if len(self.affective_events) > keep_recent:
            self.affective_events = self.affective_events[-keep_recent:]
        if len(self.affect_history) > keep_recent:
            self.affect_history = self.affect_history[-keep_recent:]
