"""
Introspection persistence for KLoROS memory system.

Stores ReflectionInsight objects as memory events so they can be retrieved
in future conversations for meta-cognitive continuity.

Governance: Tool-Integrity + Introspective-Precision compliant
"""

import json
from typing import List, Optional
from src.cognition.mind.reflection.models.reflection_models import ReflectionInsight, InsightType


def persist_reflection_insight(memory_logger, insight: ReflectionInsight) -> None:
    """
    Persist a ReflectionInsight to the memory system.

    Args:
        memory_logger: MemoryLogger instance from memory_enhanced
        insight: ReflectionInsight object to persist

    Raises:
        Exception: If logging fails (gracefully handled by caller)
    """
    if not memory_logger:
        return

    # Convert insight to JSON-serializable format
    insight_data = {
        "reflection_cycle": insight.reflection_cycle,
        "insight_type": insight.insight_type.value if isinstance(insight.insight_type, InsightType) else str(insight.insight_type),
        "phase": insight.phase,
        "title": insight.title,
        "content": insight.content,
        "confidence": insight.confidence,
        "confidence_level": insight.confidence_level.value if hasattr(insight.confidence_level, 'value') else str(insight.confidence_level),
        "keywords": insight.keywords,
        "related_conversations": insight.related_conversations,
        "source_events_count": insight.source_events_count,
        "processing_time_ms": insight.processing_time_ms,
    }

    # Add supporting data if present
    if insight.supporting_data:
        # Truncate large supporting data
        truncated_data = {}
        for key, value in insight.supporting_data.items():
            if isinstance(value, str) and len(value) > 500:
                truncated_data[key] = value[:500] + "... (truncated)"
            else:
                truncated_data[key] = value
        insight_data["supporting_data"] = truncated_data

    # Log as cognitive event
    from src.kloros_memory.models import EventType
    memory_logger.log_event(
        event_type=EventType.REFLECTION_INSIGHT,
        content=insight.title,
        metadata=insight_data
    )


def persist_real_time_introspection(memory_logger, trigger_type: str, details: dict) -> None:
    """
    Persist real-time introspection triggers to memory.

    Args:
        memory_logger: MemoryLogger instance
        trigger_type: Type of introspection trigger (e.g., "USER_CONFUSION", "REPEATED_QUESTION")
        details: Dict with trigger-specific details

    Examples:
        persist_real_time_introspection(
            memory_logger,
            "USER_CONFUSION",
            {
                "indicators": ["question_mark_density", "negation_words"],
                "confidence": 0.75,
                "recommended_action": "clarify_last_response"
            }
        )
    """
    if not memory_logger:
        return

    from src.kloros_memory.models import EventType
    memory_logger.log_event(
        event_type=EventType.REAL_TIME_INTROSPECTION,
        content=f"Introspection trigger: {trigger_type}",
        metadata={
            "trigger_type": trigger_type,
            **details
        }
    )


def retrieve_relevant_insights(memory_retriever, query: str, limit: int = 5) -> List[dict]:
    """
    Retrieve relevant reflection insights from memory.

    Args:
        memory_retriever: ContextRetriever instance
        query: User query or conversation context
        limit: Maximum number of insights to retrieve

    Returns:
        List of insight dicts with content and metadata
    """
    if not memory_retriever:
        return []

    # Retrieve events of type REFLECTION_INSIGHT
    try:
        from src.kloros_memory.models import Event, EventType

        # Get recent insights (last 7 days)
        store = memory_retriever.store
        start_time = time.time() - (168 * 3600)  # 7 days ago
        recent_events = store.get_events(
            event_type=EventType.REFLECTION_INSIGHT,
            start_time=start_time,
            limit=100
        )

        # Score and filter reflection insights
        insights = []
        query_lower = query.lower()

        for event in recent_events:
            # Extract metadata
            metadata = event.metadata or {}
            keywords = metadata.get("keywords", [])

            # Simple relevance scoring based on keywords
            relevance = 0.0
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    relevance += 0.2

            # Boost recent insights
            age_hours = (time.time() - event.timestamp) / 3600
            recency_factor = 1.0 / (1.0 + age_hours / 24.0)  # Decay over days
            relevance += recency_factor * 0.3

            # Boost high-confidence insights
            confidence = metadata.get("confidence", 0.5)
            relevance += confidence * 0.2

            insights.append({
                "content": event.content,
                "title": metadata.get("title", ""),
                "insight_type": metadata.get("insight_type", ""),
                "confidence": confidence,
                "keywords": keywords,
                "relevance": relevance,
                "timestamp": event.timestamp
            })

        # Sort by relevance and return top N
        insights.sort(key=lambda x: x["relevance"], reverse=True)
        return insights[:limit]

    except Exception as e:
        print(f"[introspection] Failed to retrieve insights: {e}")
        return []


def format_insights_for_prompt(insights: List[dict]) -> str:
    """
    Format retrieved insights for inclusion in LLM prompt.

    Args:
        insights: List of insight dicts from retrieve_relevant_insights()

    Returns:
        Formatted string for prompt injection
    """
    if not insights:
        return ""

    lines = ["Past reflections and learnings:"]

    for i, insight in enumerate(insights, 1):
        title = insight.get("title", "Unnamed insight")
        content = insight.get("content", "")
        confidence = insight.get("confidence", 0.0)

        # Truncate long content
        if len(content) > 200:
            content = content[:200] + "..."

        lines.append(f"{i}. [{title}] (confidence: {confidence:.1f})")
        lines.append(f"   {content}")

    return "\n".join(lines)


# =============================================================================
# Integration Hook for Real-Time Introspection
# =============================================================================

def hook_real_time_introspection_to_memory(kloros_instance):
    """
    Hook real-time introspection system to persist insights to memory.

    This wraps the HybridIntrospectionManager to log all triggers as events.

    Args:
        kloros_instance: KLoROS voice instance with memory_enhanced and introspection_manager
    """
    if not hasattr(kloros_instance, "introspection_manager"):
        return

    if not hasattr(kloros_instance, "memory_enhanced"):
        return

    if not kloros_instance.memory_enhanced or not kloros_instance.memory_enhanced.enable_memory:
        return

    introspection_mgr = kloros_instance.introspection_manager
    memory_logger = kloros_instance.memory_enhanced.memory_logger

    # Wrap trigger handlers to persist to memory
    original_handle_trigger = introspection_mgr.handle_trigger

    def wrapped_handle_trigger(trigger, conversation_state):
        """Wrapped trigger handler that persists to memory."""
        # Call original handler
        response = original_handle_trigger(trigger, conversation_state)

        # Persist trigger to memory
        try:
            persist_real_time_introspection(
                memory_logger,
                trigger.trigger_type.value if hasattr(trigger.trigger_type, 'value') else str(trigger.trigger_type),
                {
                    "confidence": trigger.confidence,
                    "context": trigger.context,
                    "recommended_actions": trigger.recommended_actions
                }
            )
        except Exception as e:
            print(f"[introspection] Failed to persist trigger: {e}")

        return response

    # Replace handler
    introspection_mgr.handle_trigger = wrapped_handle_trigger

    print("[introspection] ✓ Real-time introspection hooked to memory persistence")


# =============================================================================
# Integration Hook for Periodic Reflection
# =============================================================================

def hook_periodic_reflection_to_memory(kloros_instance):
    """
    Hook periodic reflection system to persist insights to memory.

    This wraps the ReflectionManager to log all insights as events.

    Args:
        kloros_instance: KLoROS voice instance with reflection system
    """
    if not hasattr(kloros_instance, "memory_enhanced"):
        return

    if not kloros_instance.memory_enhanced or not kloros_instance.memory_enhanced.enable_memory:
        return

    # TODO: Implement when periodic reflection manager is integrated
    # For now, this is a placeholder for future integration

    print("[introspection] ⚠️ Periodic reflection persistence not yet implemented")
