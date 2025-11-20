#!/usr/bin/env python3
"""
Affordance Registry - Derives Abilities from Capabilities

Translates low-level capabilities into high-level affordances (abilities).

Governance:
- Tool-Integrity: Self-contained, testable, complete docstrings
- D-REAM-Allowed-Stack: Uses JSON, no unsafe operations

Purpose:
    Enable "I can X" statements by deriving affordances from capability state

Outcomes:
    - Maps capabilities to affordances
    - Generates "I can / I can't" statements
    - Provides clear user-facing ability descriptions
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Set, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

try:
    from .capability_evaluator import CapabilityMatrix, CapabilityState
except ImportError:
    # Standalone execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from capability_evaluator import CapabilityMatrix, CapabilityState

logger = logging.getLogger(__name__)


@dataclass
class Affordance:
    """A derived ability from one or more capabilities."""
    name: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    available: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "available": self.available,
            "reason": self.reason
        }


class AffordanceRegistry:
    """
    Derives high-level affordances from low-level capabilities.

    Purpose:
        Translate technical capability status into user-friendly "I can X" statements

    Outcomes:
        - Computes available affordances from capability matrix
        - Generates missing affordance explanations
        - Enables natural language self-awareness
    """

    # Affordance mapping: affordance_name → (description, required_capabilities)
    AFFORDANCE_MAP = {
        "transcribe_live": (
            "Transcribe speech in real-time",
            ["audio.input", "stt.vosk"]
        ),
        "detect_wakeword": (
            "Detect wake words in audio stream",
            ["audio.input"]
        ),
        "text_to_speech": (
            "Convert text to synthesized speech",
            ["audio.output", "tts.piper"]
        ),
        "persist_session": (
            "Save conversation state to memory",
            ["memory.sqlite"]
        ),
        "log_event": (
            "Record events to structured log",
            ["memory.sqlite", "xai.tracing"]
        ),
        "semantic_search": (
            "Search memory using semantic similarity",
            ["memory.chroma", "rag.retrieval"]
        ),
        "fetch_docs": (
            "Retrieve documents from internet",
            ["network.http_out"]
        ),
        "post_webhook": (
            "Send HTTP POST requests to webhooks",
            ["network.http_out"]
        ),
        "generate_response": (
            "Generate natural language responses",
            ["llm.ollama"]
        ),
        "reason_deeply": (
            "Perform deep reasoning with extended context",
            ["llm.ollama", "rag.retrieval"]
        ),
        "optimize_self": (
            "Evolve and optimize system parameters",
            ["dream.evolution"]
        ),
        "create_tool": (
            "Synthesize new introspection tools",
            ["tools.synthesis", "llm.ollama"]
        ),
        "diagnose_system": (
            "Perform comprehensive system diagnostics",
            ["tools.introspection"]
        ),
        "browse_web": (
            "Navigate and extract web content",
            ["agent.browser", "network.http_out"]
        ),
        "execute_code": (
            "Run code in safe sandbox",
            ["agent.dev"]
        ),
        "explain_decision": (
            "Provide reasoning trace for decisions",
            ["xai.tracing"]
        ),
        "ask_questions": (
            "Generate curiosity-driven questions",
            ["reasoning.curiosity", "tools.introspection"]
        ),
        "propose_improvement": (
            "Propose system improvements autonomously",
            ["reasoning.autonomy", "reasoning.curiosity"]
        ),
        "self_heal": (
            "Automatically recover from degraded states",
            ["reasoning.autonomy", "tools.introspection"]
        ),
    }

    def __init__(self):
        """Initialize affordance registry."""
        self.affordances: List[Affordance] = []

    def compute_affordances(self, matrix: CapabilityMatrix) -> List[Affordance]:
        """
        Compute available affordances from capability matrix.

        Parameters:
            matrix: CapabilityMatrix with evaluated capabilities

        Returns:
            List of Affordance objects with availability status
        """
        # Build capability status map
        cap_status = {
            cap.key: cap.state
            for cap in matrix.capabilities
        }

        affordances = []
        for aff_name, (description, required_caps) in self.AFFORDANCE_MAP.items():
            # Check if all required capabilities are OK
            missing_caps = []
            degraded_caps = []
            for cap_key in required_caps:
                status = cap_status.get(cap_key, CapabilityState.UNKNOWN)
                if status == CapabilityState.MISSING:
                    missing_caps.append(cap_key)
                elif status == CapabilityState.DEGRADED:
                    degraded_caps.append(cap_key)

            if not missing_caps and not degraded_caps:
                # All capabilities OK
                affordances.append(Affordance(
                    name=aff_name,
                    description=description,
                    required_capabilities=required_caps,
                    available=True,
                    reason="All required capabilities operational"
                ))
            else:
                # Some capabilities missing or degraded
                reasons = []
                if missing_caps:
                    reasons.append(f"missing: {', '.join(missing_caps)}")
                if degraded_caps:
                    reasons.append(f"degraded: {', '.join(degraded_caps)}")

                affordances.append(Affordance(
                    name=aff_name,
                    description=description,
                    required_capabilities=required_caps,
                    available=False,
                    reason=" | ".join(reasons)
                ))

        self.affordances = affordances
        return affordances

    def get_available_affordances(self) -> List[Affordance]:
        """
        Get list of available affordances.

        Returns:
            List of available Affordance objects
        """
        return [aff for aff in self.affordances if aff.available]

    def get_unavailable_affordances(self) -> List[Affordance]:
        """
        Get list of unavailable affordances.

        Returns:
            List of unavailable Affordance objects
        """
        return [aff for aff in self.affordances if not aff.available]

    def get_statement(self) -> str:
        """
        Generate "I can / I can't" statement.

        Returns:
            Human-readable statement of available and unavailable affordances
        """
        available = self.get_available_affordances()
        unavailable = self.get_unavailable_affordances()

        lines = []

        if available:
            lines.append("I CAN:")
            for aff in available:
                lines.append(f"  ✓ {aff.description}")
        else:
            lines.append("I CANNOT perform any affordances (all capabilities unavailable)")

        if unavailable:
            lines.append("")
            lines.append("I CANNOT:")
            for aff in unavailable:
                lines.append(f"  ✗ {aff.description}")
                lines.append(f"     Reason: {aff.reason}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert affordance registry to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "affordances": [aff.to_dict() for aff in self.affordances],
            "available_count": len(self.get_available_affordances()),
            "unavailable_count": len(self.get_unavailable_affordances()),
            "timestamp": datetime.now().isoformat()
        }

    def write_affordances_json(self, path: Optional[Path] = None) -> bool:
        """
        Write affordances to JSON file.

        Parameters:
            path: Output path (default: /home/kloros/.kloros/affordances.json)

        Returns:
            True if successful, False otherwise
        """
        if path is None:
            path = Path("/home/kloros/.kloros/affordances.json")

        try:
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON
            with open(path, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)

            logger.info(f"[affordance_registry] Wrote affordances to {path}")
            return True

        except Exception as e:
            logger.error(f"[affordance_registry] Failed to write affordances: {e}")
            return False


def main():
    """Self-test and demonstration."""
    print("=== Affordance Registry Self-Test ===\n")

    # Load capability matrix
    try:
        from .capability_evaluator import CapabilityEvaluator
    except ImportError:
        from capability_evaluator import CapabilityEvaluator

    evaluator = CapabilityEvaluator()
    matrix = evaluator.evaluate_all()

    # Compute affordances
    registry = AffordanceRegistry()
    affordances = registry.compute_affordances(matrix)

    print(f"Total affordances: {len(affordances)}")
    print(f"Available: {len(registry.get_available_affordances())}")
    print(f"Unavailable: {len(registry.get_unavailable_affordances())}")
    print()

    print(registry.get_statement())
    print()

    # Write affordances file
    if registry.write_affordances_json():
        print("✓ Wrote affordances.json")
    else:
        print("✗ Failed to write affordances.json")

    return registry


if __name__ == "__main__":
    main()
