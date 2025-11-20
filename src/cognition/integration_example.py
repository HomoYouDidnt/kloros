"""
Integration Example: How to Use Active Reasoning

This shows how to integrate the deliberative layer into KLoROS's processing pipeline.

BEFORE (Passive):
    User input → LLM generation → Response → Post-hoc introspection

AFTER (Active):
    User input → Active Reasoning → Strategy Selection → LLM (with context) → Response → Monitoring

The key difference: KLoROS THINKS before acting, not just reacts.
"""

from typing import Dict, Any
from src.cognition import get_active_reasoner, StrategicApproach


def process_user_input_with_deliberation(kloros_instance, user_input: str, conversation_context: Dict = None) -> Dict[str, Any]:
    """
    Process user input with active reasoning.

    This is the new architecture that should replace direct LLM calls.

    Args:
        kloros_instance: Main KLoROS instance
        user_input: What the user said
        conversation_context: Optional conversation history

    Returns:
        Dictionary with:
        - strategy: Chosen strategic approach
        - llm_context: Context to pass to LLM
        - should_monitor: Whether execution should be monitored
        - reasoning: Why this strategy was chosen
    """

    # Step 1: Active Reasoning (NEW - this is what was missing!)
    reasoner = get_active_reasoner(kloros_instance)
    decision = reasoner.deliberate(user_input, conversation_context)

    # Step 2: Translate strategy to LLM guidance
    llm_guidance = _translate_strategy_to_llm_guidance(decision, user_input)

    # Step 3: Return decision + LLM context
    return {
        'strategy': decision.approach.value,
        'llm_context': llm_guidance,
        'should_monitor': decision.should_monitor,
        'abort_conditions': decision.abort_conditions,
        'reasoning': decision.reasoning,
        'estimated_cost': decision.estimated_fatigue_cost,
        'success_probability': decision.success_probability
    }


def _translate_strategy_to_llm_guidance(decision, user_input: str) -> Dict[str, Any]:
    """
    Translate strategic decision into LLM guidance.

    This is what gets injected into the prompt to guide the LLM's generation,
    keeping the persona prompt clean and focused on expression.
    """

    base_guidance = {
        'user_input': user_input,
        'cognitive_state': {
            'fatigue': decision.context_for_llm.get('fatigue', 0),
            'uncertainty': decision.context_for_llm.get('uncertainty', 0),
            'complexity': decision.context_for_llm.get('complexity', 'unknown')
        }
    }

    # Strategy-specific guidance
    if decision.approach == StrategicApproach.DIRECT_ANSWER:
        base_guidance['instruction'] = (
            "You have sufficient context and low uncertainty. "
            "Answer the question directly and concisely."
        )
        base_guidance['response_type'] = 'conversational'

    elif decision.approach == StrategicApproach.DIAGNOSTIC_FIRST:
        base_guidance['instruction'] = (
            "This is a complex task. Gather diagnostic information first "
            "before taking action. Use tools to understand the situation."
        )
        base_guidance['response_type'] = 'tool_use'
        base_guidance['recommended_tools'] = ['status_check', 'diagnostic', 'list']

    elif decision.approach == StrategicApproach.MINIMAL_PROBE:
        base_guidance['instruction'] = (
            "High uncertainty detected. Run the smallest possible test "
            "to reduce uncertainty before proceeding."
        )
        base_guidance['response_type'] = 'tool_use'
        base_guidance['probe_strategy'] = 'minimal'

    elif decision.approach == StrategicApproach.DECOMPOSE:
        base_guidance['instruction'] = (
            "This task is too complex to handle in one step. "
            "Break it down into smaller sub-tasks and tackle them sequentially."
        )
        base_guidance['response_type'] = 'conversational'
        base_guidance['require_breakdown'] = True

    elif decision.approach == StrategicApproach.REQUEST_CLARIFICATION:
        base_guidance['instruction'] = (
            "You have insufficient information or too much uncertainty. "
            "Ask the user ONE specific clarifying question to narrow the scope."
        )
        base_guidance['response_type'] = 'conversational'
        base_guidance['require_question'] = True

    elif decision.approach == StrategicApproach.DEFER_TO_REST:
        base_guidance['instruction'] = (
            f"Your fatigue is high ({decision.context_for_llm.get('fatigue', 0):.1%}) "
            "and this is a demanding task. Suggest deferring to a rest period, "
            "or ask if the user wants to proceed anyway with reduced quality."
        )
        base_guidance['response_type'] = 'conversational'
        base_guidance['suggest_defer'] = True

    elif decision.approach == StrategicApproach.ESCALATE_TO_USER:
        base_guidance['instruction'] = (
            "This task is safety-critical or beyond your current capability. "
            "Explain the risks and ask for explicit user confirmation before proceeding."
        )
        base_guidance['response_type'] = 'conversational'
        base_guidance['require_confirmation'] = True

    return base_guidance


# Example usage in voice processing:
"""
# OLD WAY (Passive):
def process_voice_input(kloros, user_input):
    response = kloros.llm.generate(user_input)  # Direct to LLM
    return response

# NEW WAY (Active):
def process_voice_input(kloros, user_input):
    # Step 1: Deliberate
    decision_context = process_user_input_with_deliberation(
        kloros,
        user_input,
        conversation_context=kloros.conversation_history
    )

    # Step 2: Generate with strategy context
    response = kloros.llm.generate(
        user_input,
        system_context=decision_context['llm_context']  # Guide the LLM
    )

    # Step 3: Monitor execution if needed
    if decision_context['should_monitor']:
        monitor_execution(kloros, response, decision_context['abort_conditions'])

    return response
"""
