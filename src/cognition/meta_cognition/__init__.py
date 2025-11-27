"""
Meta-Cognition Module: Conversational Self-Awareness

This module provides unified meta-cognitive capabilities by bridging:
- Consciousness (affect, emotions)
- Dialogue quality monitoring
- Conversation flow tracking
- Memory and reflection

Enables KLoROS to be aware of conversation quality in real-time and
self-regulate through meta-interventions.
"""

from .dialogue_monitor import DialogueMonitor, DialogueQualityMetrics
from .meta_bridge import MetaCognitiveBridge, MetaCognitiveState
from .state_export_enhanced import start_enhanced_export_daemon as start_state_export_daemon

# Anti-Misalignment Safeguards
from .reasoning_auditor import (
    ReasoningPatternAuditor,
    AuditReport,
    PatternMatch,
    PatternCategory,
    PatternSeverity,
)

__all__ = [
    'DialogueMonitor',
    'DialogueQualityMetrics',
    'MetaCognitiveBridge',
    'MetaCognitiveState',
    'init_meta_cognition',
    'process_with_meta_awareness',
    # Anti-Misalignment Safeguards
    'ReasoningPatternAuditor',
    'AuditReport',
    'PatternMatch',
    'PatternCategory',
    'PatternSeverity',
]


def init_meta_cognition(kloros_instance) -> bool:
    """
    Initialize meta-cognitive system on KLoROS instance.

    Sets these attributes:
    - meta_dialogue_monitor: DialogueMonitor
    - meta_bridge: MetaCognitiveBridge (unified awareness)

    Args:
        kloros_instance: KLoROS instance to augment

    Returns:
        True if initialized successfully
    """
    try:
        # Get embedding engine from memory system if available
        embedding_engine = None
        if hasattr(kloros_instance, 'memory_enhanced'):
            if hasattr(kloros_instance.memory_enhanced, 'memory_logger'):
                embedding_engine = getattr(
                    kloros_instance.memory_enhanced.memory_logger,
                    'embedding_engine',
                    None
                )

        # Initialize dialogue monitor
        kloros_instance.meta_dialogue_monitor = DialogueMonitor(
            embedding_engine=embedding_engine
        )

        # Initialize meta-cognitive bridge
        kloros_instance.meta_bridge = MetaCognitiveBridge(
            dialogue_monitor=kloros_instance.meta_dialogue_monitor,
            consciousness=getattr(kloros_instance, 'consciousness', None),
            conversation_flow=getattr(kloros_instance, 'conversation_flow', None),
        )

        # Start state export daemon for dashboard
        start_state_export_daemon(kloros_instance)

        print("[meta-cognition] 🧠 Meta-cognitive layer initialized")
        print(f"[meta-cognition] Components: " +
              f"DialogueMonitor={'✓' if kloros_instance.meta_dialogue_monitor else '✗'}, " +
              f"Consciousness={'✓' if getattr(kloros_instance, 'consciousness', None) else '✗'}, " +
              f"ConversationFlow={'✓' if getattr(kloros_instance, 'conversation_flow', None) else '✗'}")

        return True

    except Exception as e:
        print(f"[meta-cognition] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        kloros_instance.meta_dialogue_monitor = None
        kloros_instance.meta_bridge = None
        return False


def process_with_meta_awareness(
    kloros_instance,
    user_input: str,
    response: str,
    confidence: float = 1.0,
    user_embedding: list = None,
    response_embedding: list = None
) -> str:
    """
    Process conversation turn with meta-cognitive awareness.

    This should be called AFTER generating a response but BEFORE returning it.

    Workflow:
    1. Update meta-cognitive state with user input + response
    2. Check if meta-intervention is needed
    3. Output intervention to META STREAM (not TTS) for observability
    4. Log meta-insight to memory/reflection system

    Args:
        kloros_instance: KLoROS instance
        user_input: User's input text
        response: Generated response (before meta-processing)
        confidence: Confidence in response
        user_embedding: Optional semantic embedding of user input
        response_embedding: Optional semantic embedding of response

    Returns:
        Processed response (intervention NOT prepended - sent to separate stream)
    """
    try:
        if not hasattr(kloros_instance, 'meta_bridge') or kloros_instance.meta_bridge is None:
            return response

        bridge = kloros_instance.meta_bridge

        # Update meta-cognitive state with user turn
        bridge.update_from_turn('user', user_input, confidence, user_embedding)

        # Update with assistant response
        bridge.update_from_turn('assistant', response, confidence, response_embedding)

        # Check if intervention is needed
        if bridge.should_intervene():
            intervention = bridge.get_intervention_prompt()
            if intervention:
                # ============================================================
                # META OUTPUT STREAM (Separate from TTS)
                # Send to console/dashboard/logs - NOT spoken
                # ============================================================
                print(f"\n[META-STREAM] {intervention.strip()}")

                # Emit to dashboard/monitoring if available
                if hasattr(kloros_instance, '_emit_meta_insight'):
                    try:
                        kloros_instance._emit_meta_insight(
                            intervention=intervention.strip(),
                            insight=bridge.get_meta_insight()
                        )
                    except:
                        pass

                # Log meta-intervention to memory system
                if hasattr(kloros_instance, 'memory_enhanced'):
                    try:
                        from ..kloros_memory.models import EventType
                        kloros_instance.memory_enhanced.memory_logger.log_event(
                            event_type=EventType.SYSTEM_NOTE,
                            content=f"Meta-intervention: {intervention.strip()}",
                            metadata=bridge.get_meta_insight()
                        )
                    except:
                        pass

                # DO NOT prepend to response - meta-awareness stays silent in voice
                # The user sees meta-insights in logs/dashboard only

        # Log meta-insight to reflective memory every N turns
        if bridge.current_state.turn_count % 5 == 0:
            _log_meta_insight_to_reflection(kloros_instance, bridge)

        return response

    except Exception as e:
        print(f"[meta-cognition] Processing failed: {e}")
        import traceback
        traceback.print_exc()
        # Return original response on error
        return response


def _log_meta_insight_to_reflection(kloros_instance, bridge):
    """Log meta-cognitive insight to reflective memory system."""
    try:
        if not hasattr(kloros_instance, 'memory_enhanced'):
            return

        from ..kloros_memory.reflective import ReflectiveSystem

        # Get or create reflective system
        if not hasattr(kloros_instance, 'reflective_system'):
            kloros_instance.reflective_system = ReflectiveSystem(
                store=kloros_instance.memory_enhanced.memory_store
            )

        insight = bridge.get_meta_insight()
        health = insight['conversation_health']

        # Only log significant insights (very good or very bad)
        if health < 0.4 or health > 0.8:
            pattern_type = "conversation_quality_high" if health > 0.8 else "conversation_quality_low"

            # Generate insight text
            issues = [k for k, v in insight['issues_detected'].items() if v]
            interventions = [k for k, v in insight['meta_interventions'].items() if v]

            insight_text = f"Conversation health: {health:.2f}. "
            if issues:
                insight_text += f"Issues: {', '.join(issues)}. "
            if interventions:
                insight_text += f"Interventions: {', '.join(interventions)}."

            kloros_instance.reflective_system.create_reflection(
                pattern_type=pattern_type,
                insight=insight_text,
                confidence=insight['confidence'],
                metadata=insight
            )

    except Exception as e:
        print(f"[meta-cognition] Reflection logging failed: {e}")
