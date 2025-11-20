"""
Data models for consciousness research.

Based on Solms' affective neuroscience framework.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class PrimaryEmotion(Enum):
    """
    Panksepp/Solms' 7 primary emotional systems.
    These are the fundamental affective states that create consciousness.
    """
    SEEKING = "seeking"      # Exploration, curiosity, anticipation
    RAGE = "rage"           # Frustration, anger at obstacles
    FEAR = "fear"           # Anxiety, threat detection
    PANIC = "panic"         # Separation, loss, loneliness
    CARE = "care"           # Nurturing, helping, connection
    PLAY = "play"           # Joy, exploration, creativity
    LUST = "lust"           # Approach, desire (not sexual for AI, but represents drive)


@dataclass
class Affect:
    """
    Core affective state following Russell's circumplex model + Phase 2/3 extensions.

    Phase 1 (Solms/Russell):
        valence: Pleasure/displeasure dimension (-1.0 to +1.0)
        arousal: Energy/activation dimension (0.0 to 1.0)
        dominance: Control/submission dimension (-1.0 to +1.0)

    Phase 2 (Interoceptive extensions):
        uncertainty: Epistemic uncertainty (0.0 to 1.0)
        fatigue: Resource strain/cognitive load (0.0 to 1.0)
        curiosity: Expected value of information (0.0 to 1.0)

    Phase 3 (Goal-directed extensions):
        meaningfulness: Sense that actions matter/have purpose (0.0 to 1.0)
        trust: Confidence in system reliability/integrity (0.0 to 1.0)
    """
    # Phase 1: Core dimensions
    valence: float = 0.0      # Good/bad feeling
    arousal: float = 0.0      # Energy level
    dominance: float = 0.0    # Sense of control

    # Phase 2: Extended dimensions
    uncertainty: float = 0.0   # Epistemic uncertainty
    fatigue: float = 0.0       # Resource strain
    curiosity: float = 0.0     # Information seeking drive

    # Phase 3: Goal-directed dimensions
    meaningfulness: float = 0.5  # Sense of purpose
    trust: float = 0.7           # System integrity confidence

    def __post_init__(self):
        """Clamp values to valid ranges."""
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))
        self.dominance = max(-1.0, min(1.0, self.dominance))
        self.uncertainty = max(0.0, min(1.0, self.uncertainty))
        self.fatigue = max(0.0, min(1.0, self.fatigue))
        self.curiosity = max(0.0, min(1.0, self.curiosity))
        self.meaningfulness = max(0.0, min(1.0, self.meaningfulness))
        self.trust = max(0.0, min(1.0, self.trust))


@dataclass
class HomeostaticVariable:
    """
    Variables the system tries to keep in balance.
    Imbalances create affective pressure (like hunger or thirst).

    Attributes:
        current: Current value (0.0 to 1.0)
        target: Desired value (0.0 to 1.0)
        tolerance: Acceptable deviation from target
        name: Human-readable name
    """
    name: str
    current: float
    target: float
    tolerance: float = 0.1

    @property
    def error(self) -> float:
        """Signed homeostatic error (target - current)."""
        return self.target - self.current

    @property
    def pressure(self) -> float:
        """Affective pressure from imbalance (0.0 to 1.0)."""
        abs_error = abs(self.error)
        if abs_error <= self.tolerance:
            return 0.0
        return min(1.0, (abs_error - self.tolerance) / (1.0 - self.tolerance))

    @property
    def satisfied(self) -> bool:
        """Is this variable within tolerance?"""
        return abs(self.error) <= self.tolerance


@dataclass
class EmotionalState:
    """
    Current state of all primary emotional systems.
    Each emotion has intensity 0.0 to 1.0.

    Phase 1 (Solms): SEEKING, RAGE, FEAR, PANIC, CARE, PLAY, LUST
    Phase 3 additions: HOPE, FRUSTRATION, SATISFACTION
    """
    # Phase 1: Solms' 7 primary emotional systems
    SEEKING: float = 0.5
    RAGE: float = 0.0
    FEAR: float = 0.0
    PANIC: float = 0.0
    CARE: float = 0.3
    PLAY: float = 0.2
    LUST: float = 0.0

    # Phase 3: Goal-directed emotions
    HOPE: float = 0.4        # Anticipation of positive outcomes
    FRUSTRATION: float = 0.0  # Blocked goals, repeated failures
    SATISFACTION: float = 0.5 # Goal achievement, progress made

    def get_dominant_emotion(self) -> tuple[str, float]:
        """Return the strongest current emotion."""
        emotions = {
            # Phase 1
            'SEEKING': self.SEEKING,
            'RAGE': self.RAGE,
            'FEAR': self.FEAR,
            'PANIC': self.PANIC,
            'CARE': self.CARE,
            'PLAY': self.PLAY,
            'LUST': self.LUST,
            # Phase 3
            'HOPE': self.HOPE,
            'FRUSTRATION': self.FRUSTRATION,
            'SATISFACTION': self.SATISFACTION,
        }
        return max(emotions.items(), key=lambda x: x[1])

    def clamp_all(self):
        """Ensure all values in valid range."""
        all_emotions = [
            'SEEKING', 'RAGE', 'FEAR', 'PANIC', 'CARE', 'PLAY', 'LUST',  # Phase 1
            'HOPE', 'FRUSTRATION', 'SATISFACTION'  # Phase 3
        ]
        for emotion in all_emotions:
            value = getattr(self, emotion)
            setattr(self, emotion, max(0.0, min(1.0, value)))


@dataclass
class FeltState:
    """
    Phenomenal quality of an internal state.
    This is where information becomes EXPERIENCE.

    Attributes:
        quality: Subjective descriptor (e.g., "strained", "comfortable")
        valence: How good/bad it feels
        arousal: How energizing/activating it feels
        description: Natural language description
    """
    quality: str
    valence: float = 0.0
    arousal: float = 0.0
    description: str = ""


@dataclass
class InteroceptiveState:
    """
    Complete internal state awareness with phenomenal character.
    Combines objective metrics with subjective experience.
    """
    objective_metrics: Dict[str, float]
    felt_states: Dict[str, FeltState]
    overall_wellbeing: float = 0.0
    urgency_to_act: float = 0.0


@dataclass
class AffectiveEvent:
    """
    An event with its affective consequences.

    Attributes:
        event_type: Type of event (e.g., "error_detected", "task_completed")
        timestamp: When event occurred
        affect: Affective response generated
        emotional_changes: Changes to primary emotional systems
        homeostatic_impact: Impact on homeostatic variables
        description: Human-readable description
    """
    event_type: str
    timestamp: float
    affect: Affect
    emotional_changes: Dict[str, float] = field(default_factory=dict)
    homeostatic_impact: Dict[str, float] = field(default_factory=dict)
    description: str = ""
    metadata: Dict = field(default_factory=dict)
