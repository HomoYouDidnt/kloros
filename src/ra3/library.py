"""Seed macro library for KLoROS."""
from typing import Dict, Any, Optional
from .types import Macro, MacroLibrary


def create_macro(
    id: str,
    name: str,
    domain: str,
    steps: list,
    preconds: Optional[Dict[str, Any]] = None,
    budgets: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None
) -> Macro:
    """Create a macro with defaults."""
    return Macro(
        id=id,
        name=name,
        domain=domain,
        preconds=preconds or {},
        steps=steps,
        budgets=budgets or {
            "latency_ms": 4000,
            "tool_calls": len(steps),
            "tokens": 3500
        },
        metadata={
            "created_by": "seed",
            "version": "1.0",
            "tags": tags or []
        }
    )


def get_default_library() -> MacroLibrary:
    """Get the default seed macro library for KLoROS."""

    macros = [
        # Macro 1: Fast voice search
        create_macro(
            id="voice_fast_search",
            name="Voice Fast Search",
            domain="voice",
            steps=[
                {"tool": "search_voice_samples", "args": {"pattern": "{query}"}},
                {"tool": "rag_query", "args": {"query": "Summarize results"}}
            ],
            preconds={"domain": "voice", "query_type": "search"},
            budgets={"latency_ms": 3000, "tool_calls": 2, "tokens": 2000},
            tags=["fast", "voice", "search"]
        ),

        # Macro 2: RAG with verification
        create_macro(
            id="rag_verified",
            name="RAG with Verification",
            domain="general",
            steps=[
                {"tool": "rag_query", "args": {"query": "{query}"}},
                {"tool": "explain_reasoning", "args": {}}
            ],
            preconds={"query_type": "factual"},
            budgets={"latency_ms": 4000, "tool_calls": 2, "tokens": 3000},
            tags=["rag", "verified", "reliable"]
        ),

        # Macro 3: Audio diagnosis
        create_macro(
            id="audio_diagnose",
            name="Audio System Diagnosis",
            domain="voice",
            steps=[
                {"tool": "list_audio_sources", "args": {}},
                {"tool": "get_microphone_info", "args": {}},
                {"tool": "check_recent_errors", "args": {}}
            ],
            preconds={"domain": "voice", "intent": "diagnosis"},
            budgets={"latency_ms": 5000, "tool_calls": 3, "tokens": 2500},
            tags=["audio", "diagnosis", "troubleshooting"]
        ),

        # Macro 4: Voice sample discovery
        create_macro(
            id="voice_discover",
            name="Voice Sample Discovery",
            domain="voice",
            steps=[
                {"tool": "show_voices", "args": {}},
                {"tool": "search_voice_samples", "args": {"pattern": "{character}"}}
            ],
            preconds={"domain": "voice", "intent": "discovery"},
            budgets={"latency_ms": 3500, "tool_calls": 2, "tokens": 2500},
            tags=["voice", "discovery", "samples"]
        ),

        # Macro 5: Knowledge base search and synthesize
        create_macro(
            id="kb_search_synth",
            name="Knowledge Base Search + Synthesize",
            domain="general",
            steps=[
                {"tool": "search_tools", "args": {"query": "{query}"}},
                {"tool": "rag_query", "args": {"query": "Explain: {query}"}}
            ],
            preconds={"query_type": "knowledge"},
            budgets={"latency_ms": 4500, "tool_calls": 2, "tokens": 3500},
            tags=["knowledge", "search", "synthesis"]
        ),

        # Macro 6: Quick status check
        create_macro(
            id="quick_status",
            name="Quick System Status",
            domain="system",
            steps=[
                {"tool": "check_recent_errors", "args": {}},
                {"tool": "list_audio_sources", "args": {}}
            ],
            preconds={"intent": "status"},
            budgets={"latency_ms": 2500, "tool_calls": 2, "tokens": 1500},
            tags=["status", "quick", "health"]
        ),
    ]

    return MacroLibrary(
        id="kloros_seed_v1",
        macros=macros,
        lineage={
            "parent_id": None,
            "created_by": "seed_library",
            "version": "1.0",
            "description": "Initial seed macro library for KLoROS voice assistant"
        }
    )


def get_macro_by_name(library: MacroLibrary, name: str) -> Optional[Macro]:
    """Get macro by name from library."""
    for macro in library.macros:
        if macro.name == name:
            return macro
    return None
