#!/usr/bin/env python3
"""
Self-Portrait Generator - 1-Screen Self-Awareness Summary

Integrates capability matrix, affordances, and curiosity questions into
a single, readable self-narration for KLoROS.

Governance:
- Tool-Integrity: Self-contained, testable, complete docstrings
- D-REAM-Allowed-Stack: Uses JSON, no unsafe operations
- Autonomy Level 2: Surfaces autonomous thinking to user

Purpose:
    Generate concise, readable self-awareness summary that motivates curiosity

Outcomes:
    - Single-screen summary of current state
    - Clear "I can / I can't" statements
    - Top curiosity questions
    - Proposed next actions
"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from .capability_evaluator import CapabilityEvaluator, CapabilityState
    from .affordance_registry import AffordanceRegistry
    from .curiosity_core import CuriosityCore
except ImportError:
    # Standalone execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from capability_evaluator import CapabilityEvaluator, CapabilityState
    from affordance_registry import AffordanceRegistry
    from curiosity_core import CuriosityCore

logger = logging.getLogger(__name__)


class SelfPortrait:
    """
    Generates 1-screen self-portrait for KLoROS.

    Purpose:
        Provide complete, readable self-awareness summary

    Outcomes:
        - Evaluates all capabilities
        - Computes available affordances
        - Generates top curiosity questions
        - Produces human-readable summary
    """

    def __init__(self):
        """Initialize self-portrait generator."""
        self.evaluator = CapabilityEvaluator()
        self.affordance_registry = AffordanceRegistry()
        self.curiosity_core = CuriosityCore()

        self.matrix = None
        self.affordances = None
        self.questions = None

    def generate(self) -> str:
        """
        Generate complete self-portrait.

        Returns:
            Formatted multi-line string for display
        """
        # Step 1: Evaluate capabilities
        self.matrix = self.evaluator.evaluate_all()

        # Step 2: Compute affordances
        self.affordances = self.affordance_registry.compute_affordances(self.matrix)

        # Step 3: Generate curiosity questions
        self.curiosity_core.generate_questions_from_matrix(self.matrix)
        self.questions = self.curiosity_core.get_top_questions(n=3)

        # Step 4: Build portrait
        lines = []
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + " " * 25 + "KLOROS SELF-PORTRAIT" + " " * 33 + "║")
        lines.append("║" + " " * 20 + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " * 33 + "║")
        lines.append("╠" + "═" * 78 + "╣")

        # Section 1: Capability Summary
        lines.append("║ CAPABILITY STATUS" + " " * 60 + "║")
        lines.append("║" + " " * 78 + "║")
        total = self.matrix.total_count
        ok = self.matrix.ok_count
        degraded = self.matrix.degraded_count
        missing = self.matrix.missing_count

        lines.append(f"║   Total: {total:2d}  |  ✓ OK: {ok:2d}  |  ⚠ Degraded: {degraded:2d}  |  ✗ Missing: {missing:2d}" + " " * 13 + "║")

        # Show degraded/missing if any
        if degraded > 0 or missing > 0:
            lines.append("║" + " " * 78 + "║")
            lines.append("║   Issues:" + " " * 67 + "║")
            issue_count = 0
            for cap in self.matrix.capabilities:
                if cap.state in [CapabilityState.DEGRADED, CapabilityState.MISSING] and issue_count < 3:
                    status_icon = "⚠" if cap.state == CapabilityState.DEGRADED else "✗"
                    line = f"║     {status_icon} {cap.key}: {cap.why[:50]}"
                    lines.append(line + " " * (79 - len(line)) + "║")
                    issue_count += 1

        lines.append("╠" + "═" * 78 + "╣")

        # Section 2: Affordances (I CAN / I CAN'T)
        lines.append("║ CURRENT AFFORDANCES" + " " * 58 + "║")
        lines.append("║" + " " * 78 + "║")

        available = self.affordance_registry.get_available_affordances()
        unavailable = self.affordance_registry.get_unavailable_affordances()

        # Show up to 5 available
        if available:
            lines.append("║   I CAN:" + " " * 68 + "║")
            for aff in available[:5]:
                line = f"║     ✓ {aff.description}"
                lines.append(line + " " * (79 - len(line)) + "║")
            if len(available) > 5:
                line = f"║     ... and {len(available) - 5} more"
                lines.append(line + " " * (79 - len(line)) + "║")
        else:
            lines.append("║   I CANNOT perform any affordances (all capabilities unavailable)" + " " * 8 + "║")

        # Show up to 3 unavailable
        if unavailable:
            lines.append("║" + " " * 78 + "║")
            lines.append("║   I CANNOT (top gaps):" + " " * 55 + "║")
            for aff in unavailable[:3]:
                line = f"║     ✗ {aff.description[:50]}"
                lines.append(line + " " * (79 - len(line)) + "║")
                reason_line = f"║       → {aff.reason[:48]}"
                lines.append(reason_line + " " * (79 - len(reason_line)) + "║")

        lines.append("╠" + "═" * 78 + "╣")

        # Section 3: Top Curiosity Questions
        lines.append("║ CURIOSITY QUESTIONS" + " " * 58 + "║")
        lines.append("║" + " " * 78 + "║")

        if self.questions:
            lines.append(f"║   Formed {len(self.questions)} questions. Highest value:" + " " * 32 + "║")
            for i, q in enumerate(self.questions, 1):
                ratio = q.value_estimate / max(q.cost, 0.01)
                line = f"║   {i}. [{ratio:.1f}] {q.question[:62]}"
                lines.append(line + " " * (79 - len(line)) + "║")
                if len(q.question) > 62:
                    continuation = f"║       {q.question[62:120]}"
                    lines.append(continuation + " " * (79 - len(continuation)) + "║")
        else:
            lines.append("║   No questions formed (all capabilities operational)" + " " * 24 + "║")

        lines.append("╠" + "═" * 78 + "╣")

        # Section 4: Proposed Action
        lines.append("║ NEXT ACTION" + " " * 66 + "║")
        lines.append("║" + " " * 78 + "║")

        if self.questions:
            top_q = self.questions[0]
            action_text = self._action_description(top_q)
            for line_text in action_text:
                line = f"║   {line_text}"
                lines.append(line + " " * (79 - len(line)) + "║")
        else:
            lines.append("║   All systems operational. Continuing normal operation." + " " * 17 + "║")

        lines.append("╚" + "═" * 78 + "╝")

        return "\n".join(lines)

    def _action_description(self, question) -> list:
        """
        Generate action description for top question.

        Parameters:
            question: CuriosityQuestion object

        Returns:
            List of text lines describing proposed action
        """
        lines = []

        if question.action_class.value == "explain_and_soft_fallback":
            lines.append(f"Will attempt to {question.hypothesis.lower().replace('_', ' ')}")
            lines.append(f"under 30s budget, then fall back to alternative if blocked.")

        elif question.action_class.value == "investigate":
            lines.append(f"Will investigate {question.capability_key} issue via safe probe")
            lines.append(f"(read-only checks, no system modifications).")

        elif question.action_class.value == "propose_fix":
            lines.append(f"Will analyze {question.capability_key} and propose fix for user")
            lines.append(f"approval (Autonomy Level 2: propose, not execute).")

        elif question.action_class.value == "request_user_action":
            lines.append(f"Will surface {question.capability_key} issue to user with")
            lines.append(f"specific request for action (e.g., permission grant).")

        elif question.action_class.value == "find_substitute":
            lines.append(f"Will identify alternative capability to substitute for")
            lines.append(f"{question.capability_key} and validate feasibility.")

        else:
            lines.append(f"Will address: {question.question[:65]}")

        return lines

    def write_all_artifacts(self) -> bool:
        """
        Write all artifacts to disk:
        - self_state.json
        - affordances.json
        - curiosity_feed.json

        Returns:
            True if all writes succeed, False otherwise
        """
        try:
            success = True
            success &= self.evaluator.write_state_json()
            success &= self.affordance_registry.write_affordances_json()
            success &= self.curiosity_core.write_feed_json()
            return success
        except Exception as e:
            logger.error(f"[self_portrait] Failed to write artifacts: {e}")
            return False


def main():
    """Self-test and demonstration."""
    print("=== Self-Portrait Generator Self-Test ===\n")

    portrait = SelfPortrait()
    summary = portrait.generate()

    print(summary)
    print()

    # Write artifacts
    if portrait.write_all_artifacts():
        print("✓ Wrote all artifacts (self_state.json, affordances.json, curiosity_feed.json)")
    else:
        print("✗ Failed to write some artifacts")

    return portrait


if __name__ == "__main__":
    main()
