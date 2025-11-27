"""RAG backend adapter for emitting heal events."""

from typing import Optional
from ..events import mk_event


def emit_synth_timeout(heal_bus, query: str, timeout_s: int):
    """Emit event when tool synthesis times out.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        query: Query that triggered synthesis
        timeout_s: Timeout value that was exceeded
    """
    print(f"[emit_synth_timeout] Called: heal_bus={heal_bus is not None}, query={query[:50] if query else None}, timeout={timeout_s}s")

    if not heal_bus:
        print(f"[emit_synth_timeout] ⚠️ heal_bus is None, event NOT emitted")
        return

    event = mk_event(
        source="rag",
        kind="synthesis_timeout",
        severity="error",
        query=query,
        timeout_s=timeout_s
    )

    print(f"[emit_synth_timeout] ✅ Emitting event: {event.source}.{event.kind} (id={event.id})")
    heal_bus.emit(event)
    print(f"[emit_synth_timeout] Event emitted to bus")


def emit_quota_exceeded(heal_bus, query: str):
    """Emit event when quota/rate limit exceeded.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        query: Query that triggered quota check
    """
    print(f"[emit_quota_exceeded] Called: heal_bus={heal_bus is not None}, query={query[:50] if query else None}")

    if not heal_bus:
        print(f"[emit_quota_exceeded] ⚠️ heal_bus is None, event NOT emitted")
        return

    event = mk_event(
        source="rag",
        kind="quota_exceeded",
        severity="error",
        query=query
    )

    print(f"[emit_quota_exceeded] ✅ Emitting event: {event.source}.{event.kind} (id={event.id})")
    heal_bus.emit(event)
    print(f"[emit_quota_exceeded] Event emitted to bus")


def emit_rag_error(heal_bus, query: str, error: Exception):
    """Emit event when RAG processing fails with an error.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        query: Query that triggered RAG processing
        error: Exception that occurred during RAG processing
    """
    error_type = type(error).__name__
    error_msg = str(error)
    print(f"[emit_rag_error] Called: heal_bus={heal_bus is not None}, query={query[:50] if query else None}, error={error_type}: {error_msg[:100]}")

    if not heal_bus:
        print(f"[emit_rag_error] ⚠️ heal_bus is None, event NOT emitted")
        return

    event = mk_event(
        source="rag",
        kind="processing_error",
        severity="error",
        query=query,
        error_type=error_type,
        error_message=error_msg
    )

    print(f"[emit_rag_error] ✅ Emitting event: {event.source}.{event.kind} (id={event.id})")
    heal_bus.emit(event)
    print(f"[emit_rag_error] Event emitted to bus")
