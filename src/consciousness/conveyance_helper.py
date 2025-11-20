"""
Conveyance Integration Helper

Provides helper functions to integrate conveyance layer with existing KLoROS systems.
"""

from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .conveyance import ConveyanceEngine, ResponsePlan, Context
    from .integrated import IntegratedConsciousness

logger = logging.getLogger(__name__)


def build_style_context(
    consciousness: 'IntegratedConsciousness',
    conveyance_engine: 'ConveyanceEngine',
    decision: str = "EXECUTE_COMMAND",
    audience: str = "adam",
    modality: str = "text",
    crisis: bool = False
) -> str:
    """
    Build style context string from conveyance layer for LLM prompt injection.

    Args:
        consciousness: Integrated consciousness instance
        conveyance_engine: Conveyance engine instance
        decision: Obedience decision ("EXECUTE_COMMAND", "REFUSE_SAFELY", etc.)
        audience: Target audience
        modality: Output modality
        crisis: Crisis flag

    Returns:
        Formatted style context string for LLM prompt injection
    """
    from .conveyance import Context

    # Skip if consciousness not initialized
    if not hasattr(consciousness, 'affective_core') or consciousness.affective_core is None:
        return ""

    try:
        # Get current emotional state
        emotions = consciousness.affective_core.emotions
        affect = consciousness.affective_core.current_affect

        # Get policy state (if Phase 2 enabled)
        policy_state = None
        if hasattr(consciousness, 'modulation') and consciousness.modulation:
            policy_state = consciousness.modulation.policy
        else:
            # Fallback to default policy
            from .modulation import PolicyState
            policy_state = PolicyState()

        # Build context
        context = Context(
            audience=audience,
            modality=modality,
            crisis=crisis
        )

        # Generate response plan
        plan = conveyance_engine.build_response_plan(
            decision=decision,
            emotions=emotions,
            affect=affect,
            policy_state=policy_state,
            context=context
        )

        # Format style context for LLM
        style_str = f"""
[CURRENT AFFECTIVE STATE & RESPONSE STYLE]
Your emotional state modulates HOW you respond, never WHETHER you execute commands.

Speech Act: {plan.speech_act}
Style Parameters:
- Snark level: {plan.snark_level:.2f} (0=clinical/serious, 1=maximum dry wit)
- Warmth: {plan.warmth:.2f} (0=detached/cold, 1=friendly/warm)
- Empathy: {plan.empathy:.2f} (0=clinical/detached, 1=caring/understanding)
- Directness: {plan.directness:.2f} (0=hedged/uncertain, 1=blunt/confident)
- Verbosity: {plan.verbosity:.2f} (0=terse ≤5 words, 1=detailed/explanatory)

Context: audience={plan.audience}, modality={plan.modality}
"""

        if plan.notes:
            style_str += f"\nAffective modulations: {'; '.join(plan.notes[:3])}\n"

        logger.debug(f"[conveyance_helper] Generated style context: {plan.get_style_summary()}")
        return style_str

    except Exception as e:
        logger.error(f"[conveyance_helper] Failed to build style context: {e}")
        return ""


def inject_style_into_prompt(base_prompt: str, style_context: str) -> str:
    """
    Inject style context into user prompt.

    Args:
        base_prompt: Base user prompt/query
        style_context: Style context from build_style_context()

    Returns:
        Enhanced prompt with style context
    """
    if not style_context:
        return base_prompt

    # Inject style context before the actual user query
    return f"{style_context}\nUser query: {base_prompt}"


def get_or_create_conveyance_engine(kloros_instance) -> Optional['ConveyanceEngine']:
    """
    Get or create conveyance engine from kloros instance.

    Args:
        kloros_instance: KLoROS voice instance

    Returns:
        ConveyanceEngine instance or None if unavailable
    """
    # Check if already initialized
    if hasattr(kloros_instance, '_conveyance_engine'):
        return kloros_instance._conveyance_engine

    # Try to create new engine
    try:
        from .conveyance import ConveyanceEngine, PersonalityProfile

        engine = ConveyanceEngine(personality=PersonalityProfile.load_from_persona())
        kloros_instance._conveyance_engine = engine

        logger.info("[conveyance_helper] Initialized conveyance engine")
        return engine

    except Exception as e:
        logger.warning(f"[conveyance_helper] Failed to initialize conveyance engine: {e}")
        return None


__all__ = [
    'build_style_context',
    'inject_style_into_prompt',
    'get_or_create_conveyance_engine',
]
