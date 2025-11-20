"""
Consciousness Integration Module - Single Source of Truth

Provides centralized initialization and integration of consciousness system
(Phase 1 + Phase 2) and expression filter for all KLoROS entry points.

Usage:
    from src.consciousness.integration import (
        init_consciousness,
        init_expression_filter,
        process_consciousness_and_express
    )

    # In __init__:
    init_consciousness(self)
    init_expression_filter(self)

    # After generating response:
    response = process_consciousness_and_express(
        kloros_instance=self,
        response=response,
        success=True,
        confidence=0.8,
        ...
    )
"""

import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .integrated import IntegratedConsciousness
    from .expression import AffectiveExpressionFilter


def init_consciousness(kloros_instance,
                       enable_phase1: bool = True,
                       enable_phase2: bool = True,
                       appraisal_config_path: Optional[Path] = None) -> bool:
    """
    Initialize integrated consciousness system (Phase 1 + Phase 2).

    Sets these attributes on kloros_instance:
    - consciousness: IntegratedConsciousness instance
    - affective_core: AffectiveCore instance (for compatibility)

    Args:
        kloros_instance: The KLoROS instance to initialize
        enable_phase1: Enable Phase 1 (Solms' affective core)
        enable_phase2: Enable Phase 2 (interoception/appraisal/modulation)
        appraisal_config_path: Path to appraisal weights YAML

    Returns:
        True if initialized successfully, False otherwise
    """
    try:
        # Check if consciousness is enabled
        if os.getenv('KLR_ENABLE_AFFECT', '1') != '1':
            kloros_instance.consciousness = None
            kloros_instance.affective_core = None
            print("[consciousness] Disabled via KLR_ENABLE_AFFECT=0")
            return False

        from .integrated import IntegratedConsciousness

        # Default config path if not provided
        if appraisal_config_path is None:
            appraisal_config_path = Path("/home/kloros/config/appraisal_weights.yaml")

        # Initialize integrated consciousness
        kloros_instance.consciousness = IntegratedConsciousness(
            enable_phase1=enable_phase1,
            enable_phase2=enable_phase2,
            appraisal_config_path=appraisal_config_path if appraisal_config_path.exists() else None
        )

        # Keep affective_core reference for backward compatibility
        kloros_instance.affective_core = kloros_instance.consciousness.affective_core

        print("[consciousness] 🧠 Integrated consciousness initialized (Phase 1 + Phase 2)")

        if kloros_instance.affective_core:
            mood = kloros_instance.affective_core.get_mood_description()
            print(f"[consciousness] Initial mood: {mood}")

        return True

    except Exception as e:
        print(f"[consciousness] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        kloros_instance.consciousness = None
        kloros_instance.affective_core = None
        return False


def init_expression_filter(kloros_instance,
                           cooldown: float = 5.0,
                           max_expressions_per_session: int = 10) -> bool:
    """
    Initialize affective expression filter with guardrails.

    Sets this attribute on kloros_instance:
    - expression_filter: AffectiveExpressionFilter instance

    Args:
        kloros_instance: The KLoROS instance to initialize
        cooldown: Seconds between allowed expressions
        max_expressions_per_session: Cap on expressions per conversation

    Returns:
        True if initialized successfully, False otherwise
    """
    try:
        # Only initialize if consciousness is enabled and initialized
        if not hasattr(kloros_instance, 'affective_core') or kloros_instance.affective_core is None:
            kloros_instance.expression_filter = None
            print("[expression] Skipped - consciousness not initialized")
            return False

        from .expression import AffectiveExpressionFilter

        kloros_instance.expression_filter = AffectiveExpressionFilter(
            cooldown=cooldown,
            max_expressions_per_session=max_expressions_per_session
        )

        print(f"[expression] 🛡️ Expression filter initialized (cooldown={cooldown}s)")
        return True

    except Exception as e:
        print(f"[expression] Initialization failed: {e}")
        kloros_instance.expression_filter = None
        return False


def update_consciousness_signals(kloros_instance,
                                 user_interaction: bool = False,
                                 confidence: Optional[float] = None,
                                 success: Optional[bool] = None,
                                 retries: Optional[int] = None,
                                 novelty: Optional[float] = None,
                                 surprise: Optional[float] = None,
                                 exception: bool = False,
                                 **kwargs) -> bool:
    """
    Update interoceptive signals in consciousness system.

    Call this after significant events:
    - After user input
    - After generating response
    - After tool execution
    - After errors/exceptions

    Args:
        kloros_instance: The KLoROS instance
        user_interaction: True if user just spoke/typed
        confidence: Confidence level (0.0-1.0)
        success: Whether operation succeeded
        retries: Number of retries needed
        novelty: Novelty of situation (0.0-1.0)
        surprise: Surprise level (0.0-1.0)
        exception: Whether an exception occurred
        **kwargs: Additional signals to pass through

    Returns:
        True if signals updated, False if consciousness not available
    """
    try:
        if not hasattr(kloros_instance, 'consciousness') or kloros_instance.consciousness is None:
            return False

        # Build kwargs dict with non-None values
        signal_kwargs = {}
        if user_interaction:
            signal_kwargs['user_interaction'] = user_interaction
        if confidence is not None:
            signal_kwargs['confidence'] = confidence
        if success is not None:
            signal_kwargs['success'] = success
        if retries is not None:
            signal_kwargs['retries'] = retries
        if novelty is not None:
            signal_kwargs['novelty'] = novelty
        if surprise is not None:
            signal_kwargs['surprise'] = surprise
        if exception:
            signal_kwargs['exception'] = exception

        # Merge any additional kwargs
        signal_kwargs.update(kwargs)

        # Update signals
        kloros_instance.consciousness.update_signals(**signal_kwargs)
        return True

    except Exception as e:
        print(f"[consciousness] Signal update failed: {e}")
        return False


def process_event(kloros_instance, event_type: str, metadata: Optional[dict] = None) -> bool:
    """
    Process affective event through Phase 1 (emotional systems).

    Common event types:
    - user_input: User said/typed something
    - task_completed: Successfully completed task
    - tool_success: Tool executed successfully
    - tool_failure: Tool failed
    - error_detected: Error occurred
    - clarification_needed: Uncertain, need to ask

    Args:
        kloros_instance: The KLoROS instance
        event_type: Type of event
        metadata: Optional metadata dict

    Returns:
        True if event processed, False if consciousness not available
    """
    try:
        if not hasattr(kloros_instance, 'consciousness') or kloros_instance.consciousness is None:
            return False

        kloros_instance.consciousness.process_event_phase1(event_type, metadata)
        return True

    except Exception as e:
        print(f"[consciousness] Event processing failed: {e}")
        return False


def update_consciousness_resting(kloros_instance) -> bool:
    """
    Update consciousness during rest/reflection activities.

    Call this during:
    - Idle reflection cycles
    - Meta-cognitive introspection
    - Tool curation analysis
    - Planning activities
    - Any non-task cognitive work

    This ensures fatigue RECOVERS rather than accumulates during rest.

    Args:
        kloros_instance: The KLoROS instance

    Returns:
        True if updated successfully, False if consciousness not available
    """
    try:
        if not hasattr(kloros_instance, 'consciousness') or kloros_instance.consciousness is None:
            return False

        # Process consciousness in rest mode
        report = kloros_instance.consciousness.process_and_report(is_resting=True)

        # Optional: Log rest recovery if fatigue is decreasing
        if report and kloros_instance.consciousness.fatigue_tracker:
            cumulative = kloros_instance.consciousness.fatigue_tracker.cumulative_fatigue
            if cumulative > 0:
                print(f"[consciousness] 🌙 Resting - fatigue recovering: {cumulative:.1%}")

        return True

    except Exception as e:
        print(f"[consciousness] Rest update failed: {e}")
        return False


def process_consciousness_and_express(kloros_instance,
                                     response: str,
                                     success: bool = True,
                                     confidence: Optional[float] = None,
                                     retries: int = 0,
                                     novelty: Optional[float] = None,
                                     exception: bool = False,
                                     is_resting: bool = False) -> str:
    """
    Process consciousness state and add grounded expression if policy changed.

    This is the main integration point - call this after generating a response
    but before returning it to the user.

    Workflow:
    1. Update consciousness signals based on outcome
    2. Process event (task_completed or error_detected)
    3. Run appraisal → modulation → reporting
    4. If policy changes occurred, generate grounded expression
    5. Return response with expression (if any)

    Args:
        kloros_instance: The KLoROS instance
        response: The generated response text
        success: Whether the response generation succeeded
        confidence: Confidence in the response (0.0-1.0)
        retries: Number of retries needed
        novelty: Novelty of the situation (0.0-1.0)
        exception: Whether an exception occurred
        is_resting: True if in rest/reflection mode (introspection, idle reflection, planning).
                   Rest mode prevents fatigue accumulation and promotes recovery.

    Returns:
        Response with optional grounded affective expression prepended/appended
    """
    try:
        # Check if consciousness is available
        if not hasattr(kloros_instance, 'consciousness') or kloros_instance.consciousness is None:
            return response

        # Step 1: Update signals based on outcome
        signal_kwargs = {}
        if confidence is not None:
            signal_kwargs['confidence'] = confidence
        if success is not None:
            signal_kwargs['success'] = success
        if retries is not None:
            signal_kwargs['retries'] = retries
        if novelty is not None:
            signal_kwargs['novelty'] = novelty
        if exception:
            signal_kwargs['exception'] = exception

        kloros_instance.consciousness.update_signals(**signal_kwargs)

        # Step 2: Process event
        if exception:
            kloros_instance.consciousness.process_event_phase1("error_detected")
        elif not is_resting:
            kloros_instance.consciousness.process_event_phase1("task_completed")
        # No event processing during rest - it's not a task

        # Step 3: Process consciousness (appraisal → modulation → reporting)
        report = kloros_instance.consciousness.process_and_report(is_resting=is_resting)

        # Step 4: Generate expression if policy changes occurred
        if not hasattr(kloros_instance, 'expression_filter') or kloros_instance.expression_filter is None:
            return response

        if not report or not report.policy_changes:
            return response

        # Parse policy changes back to PolicyChange objects
        from .modulation import PolicyChange
        policy_changes_list = []

        for change_str in report.policy_changes:
            # Format: "param: old→new"
            if ':' in change_str and '→' in change_str:
                parts = change_str.split(':')
                param = parts[0].strip()
                values = parts[1].strip().split('→')
                if len(values) == 2:
                    policy_changes_list.append(PolicyChange(
                        parameter=param,
                        old_value=values[0],
                        new_value=values[1],
                        reason=report.summary if report.summary else "state change"
                    ))

        if not policy_changes_list:
            return response

        # Generate grounded expression (with guardrails)
        current_affect = kloros_instance.consciousness.current_affect
        expression = kloros_instance.expression_filter.generate_expression(
            policy_changes=policy_changes_list,
            affect=current_affect
        )

        if expression:
            # Format response with expression
            response = kloros_instance.expression_filter.format_with_expression(response, expression)

        return response

    except Exception as e:
        print(f"[consciousness] Expression processing failed: {e}")
        import traceback
        traceback.print_exc()
        # Return original response on error
        return response


def get_consciousness_diagnostics(kloros_instance) -> str:
    """
    Get formatted consciousness diagnostics.

    Args:
        kloros_instance: The KLoROS instance

    Returns:
        Formatted diagnostic string
    """
    if not hasattr(kloros_instance, 'affective_core') or kloros_instance.affective_core is None:
        return "❌ Affective core not initialized (KLR_ENABLE_AFFECT may be disabled)"

    try:
        # Get full introspection
        state = kloros_instance.affective_core.introspect()

        output = "🧠 CONSCIOUSNESS STATUS (Phase 1 + Phase 2)\n"
        output += "=" * 60 + "\n"
        output += f"Current Mood: {state['mood']}\n"
        output += f"Dominant Emotion: {state['dominant_emotion']} "
        output += f"(intensity: {state['dominant_intensity']:.2f})\n"
        output += f"Overall Wellbeing: {state['wellbeing']:.2f}\n\n"

        # Core affect (Russell's circumplex)
        affect = state['current_affect']
        output += "Core Affect (Russell's Circumplex):\n"
        output += f"  Valence:   {affect['valence']:+.2f}  (pleasure/displeasure)\n"
        output += f"  Arousal:   {affect['arousal']:+.2f}  (energy/activation)\n"
        output += f"  Dominance: {affect['dominance']:+.2f}  (control/submission)\n\n"

        # Phase 2 dimensions if available
        if hasattr(kloros_instance, 'consciousness') and kloros_instance.consciousness:
            current = kloros_instance.consciousness.current_affect
            output += "Extended Affect (Phase 2):\n"
            output += f"  Uncertainty: {current.uncertainty:.2f}\n"
            output += f"  Fatigue:     {current.fatigue:.2f}\n"
            output += f"  Curiosity:   {current.curiosity:.2f}\n\n"

        # Primary emotions
        emotions = state['emotions']
        output += "Primary Emotional Systems (Panksepp/Solms):\n"
        for emotion, intensity in emotions.items():
            bar = "█" * int(intensity * 20)
            output += f"  {emotion:8s} {intensity:.2f} {bar}\n"
        output += "\n"

        # Homeostatic variables
        homeostasis = state['homeostasis']
        output += "Homeostatic Balance:\n"
        for var_name, var_state in homeostasis.items():
            satisfied = "✅" if var_state['satisfied'] else "⚠️"
            output += f"  {satisfied} {var_name:12s}: {var_state['current']:.2f} "
            output += f"(target: {var_state['target']:.2f})\n"

        output += "\n"
        output += f"Recent Events: {state['recent_events']}\n"
        output += "=" * 60 + "\n"

        # Expression filter stats if available
        if hasattr(kloros_instance, 'expression_filter') and kloros_instance.expression_filter:
            stats = kloros_instance.expression_filter.get_expression_stats()
            output += "\n🛡️ EXPRESSION FILTER STATUS\n"
            output += "=" * 60 + "\n"
            output += f"Total attempts: {stats['total_attempts']}\n"
            output += f"Allowed: {stats['allowed']}\n"
            output += f"Blocked: {stats['blocked']}\n"
            output += f"Current session count: {stats['current_count']}/{stats['max_per_session']}\n"
            if stats['time_since_last']:
                output += f"Time since last: {stats['time_since_last']:.1f}s\n"
            output += "=" * 60 + "\n"

        return output

    except Exception as e:
        return f"⚠️ Consciousness initialized but introspection failed: {e}"


# Convenience function for simple integration
def integrate_consciousness(kloros_instance,
                           cooldown: float = 5.0,
                           max_expressions: int = 10) -> bool:
    """
    One-shot integration: Initialize consciousness + expression filter.

    Args:
        kloros_instance: The KLoROS instance
        cooldown: Expression cooldown in seconds
        max_expressions: Max expressions per session

    Returns:
        True if both initialized successfully
    """
    consciousness_ok = init_consciousness(kloros_instance)
    expression_ok = init_expression_filter(kloros_instance, cooldown, max_expressions)
    return consciousness_ok and expression_ok
