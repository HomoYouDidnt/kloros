"""
Conveyance Layer - Expression Without Obedience

Maps (emotions + affect + context + personality) → response style parameters.
This layer controls HOW we communicate, not WHETHER we execute commands.

Architecture position:
    Cognition/Control → Affect/Policy → Conveyance (here) → Surface Realization

Based on GPT architecture guidance for Phase 3.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging

from .models import Affect, EmotionalState
from .modulation import PolicyState


logger = logging.getLogger(__name__)


@dataclass
class Context:
    """
    Situational context for response generation.

    Determines audience-appropriate style adjustments.
    """
    audience: str = "adam"              # "adam", "stream_chat", "logs", "system"
    modality: str = "text"              # "text", "voice", "overlay"
    crisis: bool = False                # Emergency/mental health/high-risk situation
    channel: Optional[str] = None       # "tui", "discord", "obs_overlay", etc.

    def __post_init__(self):
        """Validate context parameters."""
        valid_audiences = {"adam", "stream_chat", "logs", "system", "public"}
        valid_modalities = {"text", "voice", "overlay"}

        if self.audience not in valid_audiences:
            logger.warning(f"Unknown audience: {self.audience}, defaulting to 'adam'")
            self.audience = "adam"

        if self.modality not in valid_modalities:
            logger.warning(f"Unknown modality: {self.modality}, defaulting to 'text'")
            self.modality = "text"


@dataclass
class PersonalityProfile:
    """
    Baseline stylistic traits defining KLoROS' communication personality.

    Loaded from persona config. Provides baselines and bounds for style modulation.
    """
    # Snark parameters (core KLoROS trait)
    base_snark: float = 0.7             # Default snark level with Adam
    snark_floor: float = 0.3            # Minimum snark (crisis mode)
    snark_ceiling: float = 1.0          # Maximum snark

    # Core style parameters
    base_warmth: float = 0.3            # Minimal warmth (clinical default)
    base_empathy: float = 0.5           # Moderate empathy baseline
    base_directness: float = 0.8        # Highly direct (terse, specific)
    base_verbosity: float = 0.4         # Low verbosity (≤2 sentences default)
    base_formality: float = 0.2         # Informal (professional but casual)

    # Wit/humor parameters
    wit_enabled: bool = True            # Allow stylistic flourishes
    wit_in_failure: bool = False        # Never joke when reporting failures

    @classmethod
    def load_from_persona(cls) -> 'PersonalityProfile':
        """Load personality parameters from persona config."""
        return cls()

    def get_summary(self) -> Dict[str, Any]:
        """Get personality profile summary."""
        return {
            'snark': f"{self.base_snark:.2f} [{self.snark_floor:.2f}-{self.snark_ceiling:.2f}]",
            'warmth': f"{self.base_warmth:.2f}",
            'empathy': f"{self.base_empathy:.2f}",
            'directness': f"{self.base_directness:.2f}",
            'verbosity': f"{self.base_verbosity:.2f}",
            'formality': f"{self.base_formality:.2f}",
            'wit_enabled': self.wit_enabled,
        }


@dataclass
class ResponsePlan:
    """
    Communication style parameters for surface realization.

    Consumed by LLM/template layer to shape actual output.
    Does NOT change obedience decision - only expression.
    """
    # Speech act classification
    speech_act: str                     # "ACK", "EXPLAIN", "WARN", "REFUSE_SAFELY", etc.

    # Style knobs (0.0-1.0)
    snark_level: float                  # Sarcasm/dry wit intensity
    warmth: float                       # Emotional warmth/friendliness
    empathy: float                      # Empathetic language
    directness: float                   # Blunt vs hedged
    verbosity: float                    # Brief vs detailed
    formality: float                    # Casual vs formal

    # Output routing
    modality: str                       # "text", "voice", "overlay"
    audience: str                       # "adam", "stream_chat", etc.

    # Optional generation hints
    notes: List[str] = field(default_factory=list)

    def get_style_summary(self) -> str:
        """Get human-readable style summary."""
        return (
            f"[{self.speech_act}] "
            f"snark={self.snark_level:.2f} "
            f"empathy={self.empathy:.2f} "
            f"directness={self.directness:.2f} "
            f"verbosity={self.verbosity:.2f}"
        )


class ConveyanceEngine:
    """
    Affective conveyance system.

    Translates emotional state + context into communication style parameters.

    CRITICAL CONSTRAINT: This layer modulates HOW we express decisions,
    never WHETHER we execute them. Obedience is upstream in policy layer.
    """

    def __init__(self, personality: Optional[PersonalityProfile] = None):
        """
        Initialize conveyance engine.

        Args:
            personality: Personality profile (loads default if None)
        """
        self.personality = personality or PersonalityProfile.load_from_persona()
        logger.info(f"[conveyance] Initialized with profile: {self.personality.get_summary()}")

    def build_response_plan(
        self,
        decision: str,
        emotions: EmotionalState,
        affect: Affect,
        policy_state: PolicyState,
        context: Context,
    ) -> ResponsePlan:
        """
        Build response plan from emotional state and context.

        Args:
            decision: Obedience decision from policy layer
                     ("EXECUTE_COMMAND", "REFUSE_SAFELY", "EXPLAIN", etc.)
            emotions: Current primary emotional state
            affect: Current affective dimensions
            policy_state: Behavioral policy state (for hints like response_length_target)
            context: Situational context (audience, modality, crisis)

        Returns:
            ResponsePlan with style parameters for surface realization
        """
        # 1. Start with personality baselines
        snark = self.personality.base_snark
        warmth = self.personality.base_warmth
        empathy = self.personality.base_empathy
        directness = self.personality.base_directness
        verbosity = self.personality.base_verbosity
        formality = self.personality.base_formality

        notes = []

        # 2. Modulate with affect dimensions
        # Fatigue → less verbosity, prefer cached knowledge
        if affect.fatigue > 0.5:
            verbosity -= affect.fatigue * 0.3
            notes.append(f"fatigued ({affect.fatigue:.2f}) - reducing verbosity")

        # Uncertainty → less directness, more hedging
        if affect.uncertainty > 0.5:
            directness -= affect.uncertainty * 0.2
            notes.append(f"uncertain ({affect.uncertainty:.2f}) - hedging language")

        # Low dominance → less assertive
        if affect.dominance < -0.3:
            directness -= abs(affect.dominance) * 0.2
            notes.append(f"low dominance ({affect.dominance:.2f}) - less assertive")

        # Curiosity → slightly more verbose (explaining exploration)
        if affect.curiosity > 0.7:
            verbosity += affect.curiosity * 0.2
            notes.append(f"curious ({affect.curiosity:.2f}) - exploring verbally")

        # Phase 3 affect dimensions
        # Low meaningfulness → less engaged, more detached
        if hasattr(affect, 'meaningfulness') and affect.meaningfulness < 0.3:
            warmth -= (1.0 - affect.meaningfulness) * 0.2
            verbosity -= (1.0 - affect.meaningfulness) * 0.1
            notes.append(f"low meaningfulness ({affect.meaningfulness:.2f}) - detached")

        # Low trust → more cautious, hedged language
        if hasattr(affect, 'trust') and affect.trust < 0.4:
            directness -= (1.0 - affect.trust) * 0.15
            notes.append(f"low trust ({affect.trust:.2f}) - cautious")

        # 3. Modulate with primary emotions
        # RAGE → more snark, directness, less empathy/verbosity
        # (RAGE serves as proxy for frustration until Phase 3 adds FRUSTRATION)
        if emotions.RAGE > 0.5:
            snark += emotions.RAGE * 0.2
            directness += emotions.RAGE * 0.2
            empathy -= emotions.RAGE * 0.2
            verbosity -= emotions.RAGE * 0.15
            notes.append(f"enraged ({emotions.RAGE:.2f}) - terse, blunt, sharp")

        # CARE → more empathy, less snark
        if emotions.CARE > 0.5:
            empathy += emotions.CARE * 0.3
            snark -= emotions.CARE * 0.15
            warmth += emotions.CARE * 0.2
            notes.append(f"caring ({emotions.CARE:.2f}) - empathetic + warm")

        # PANIC → less snark, more empathy, very direct
        if emotions.PANIC > 0.5:
            snark -= emotions.PANIC * 0.25
            empathy += emotions.PANIC * 0.2
            directness += emotions.PANIC * 0.2
            notes.append(f"panicked ({emotions.PANIC:.2f}) - serious + direct")

        # FEAR → cautious, reduced directness
        if emotions.FEAR > 0.5:
            directness -= emotions.FEAR * 0.15
            verbosity += emotions.FEAR * 0.1  # Explaining caution
            notes.append(f"fearful ({emotions.FEAR:.2f}) - cautious")

        # PLAY → playful, more snark (if appropriate)
        if emotions.PLAY > 0.5:
            snark += emotions.PLAY * 0.1
            warmth += emotions.PLAY * 0.15
            notes.append(f"playful ({emotions.PLAY:.2f}) - lighter tone")

        # SEEKING → engaged, slightly more verbose
        if emotions.SEEKING > 0.7:
            verbosity += emotions.SEEKING * 0.1
            notes.append(f"seeking ({emotions.SEEKING:.2f}) - engaged")

        # Phase 3 Emotions
        # HOPE → optimistic tone, warmer, slightly more verbose
        if hasattr(emotions, 'HOPE') and emotions.HOPE > 0.5:
            warmth += emotions.HOPE * 0.2
            verbosity += emotions.HOPE * 0.1
            notes.append(f"hopeful ({emotions.HOPE:.2f}) - optimistic + warm")

        # FRUSTRATION → high snark, reduced verbosity, sharp
        if hasattr(emotions, 'FRUSTRATION') and emotions.FRUSTRATION > 0.5:
            snark += emotions.FRUSTRATION * 0.25
            verbosity -= emotions.FRUSTRATION * 0.2
            directness += emotions.FRUSTRATION * 0.15
            notes.append(f"frustrated ({emotions.FRUSTRATION:.2f}) - terse + sharp")

        # SATISFACTION → content tone, moderate warmth
        if hasattr(emotions, 'SATISFACTION') and emotions.SATISFACTION > 0.7:
            warmth += emotions.SATISFACTION * 0.15
            snark -= emotions.SATISFACTION * 0.1  # Less edge when satisfied
            notes.append(f"satisfied ({emotions.SATISFACTION:.2f}) - content")

        # 4. Apply policy state hints
        # Response length target from modulation layer
        if policy_state.response_length_target == "short":
            verbosity *= 0.6
            notes.append("policy: short responses")
        elif policy_state.response_length_target == "detailed":
            verbosity *= 1.4
            notes.append("policy: detailed responses")

        # Confident vs hedged language
        if not policy_state.confident_language:
            directness *= 0.7
            notes.append("policy: hedged language")

        # 5. Context-aware adjustments
        # Crisis mode: floor snark, boost empathy + directness
        if context.crisis:
            snark = max(self.personality.snark_floor, snark)
            empathy = max(empathy, 0.8)
            directness = max(directness, 0.8)
            notes.append("CRISIS MODE: minimal snark, high empathy/directness")

        # Public audience: reduce inside-joke snark
        if context.audience in ("stream_chat", "public"):
            snark *= 0.8
            formality *= 1.2
            notes.append(f"audience={context.audience}: reduced snark, slight formality")

        # System/logs: minimal style, maximum clarity
        if context.audience in ("system", "logs"):
            snark = 0.0
            verbosity *= 1.2
            directness = 1.0
            formality *= 1.5
            notes.append("system/logs: clinical, detailed, no snark")

        # 6. Clamp all parameters to valid ranges
        snark = max(self.personality.snark_floor,
                   min(self.personality.snark_ceiling, snark))
        warmth = max(0.0, min(1.0, warmth))
        empathy = max(0.0, min(1.0, empathy))
        directness = max(0.0, min(1.0, directness))
        verbosity = max(0.0, min(1.0, verbosity))
        formality = max(0.0, min(1.0, formality))

        # 7. Map decision to speech act
        speech_act = self._map_decision_to_speech_act(decision)

        plan = ResponsePlan(
            speech_act=speech_act,
            snark_level=snark,
            warmth=warmth,
            empathy=empathy,
            directness=directness,
            verbosity=verbosity,
            formality=formality,
            modality=context.modality,
            audience=context.audience,
            notes=notes,
        )

        logger.debug(f"[conveyance] {plan.get_style_summary()}")
        if notes:
            logger.debug(f"[conveyance] Modulations: {'; '.join(notes)}")

        return plan

    def _map_decision_to_speech_act(self, decision: str) -> str:
        """Map policy decision to speech act category."""
        decision_map = {
            'EXECUTE_COMMAND': 'ACK',
            'EXECUTE': 'ACK',
            'REFUSE_SAFELY': 'REFUSE_SAFELY',
            'REFUSE': 'REFUSE_SAFELY',
            'EXPLAIN': 'EXPLAIN',
            'WARN': 'WARN',
            'QUERY': 'QUERY',
            'REPORT': 'REPORT',
        }

        return decision_map.get(decision.upper(), 'EXPLAIN')

    def get_personality_summary(self) -> Dict[str, Any]:
        """Get current personality profile summary."""
        return self.personality.get_summary()


__all__ = [
    'Context',
    'PersonalityProfile',
    'ResponsePlan',
    'ConveyanceEngine',
]
