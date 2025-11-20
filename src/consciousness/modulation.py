"""
Modulation System - Affect to Behavior

This module translates affective states into safe, interpretable policy changes.
Affects modulate reasoning strategies, tool selection, and output characteristics.

Based on GPT suggestions for Phase 2D.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
import time

from .models import Affect


@dataclass
class PolicyState:
    """
    Current policy settings that can be modulated by affect.

    These are the "knobs" that affect can turn to influence behavior.

    CRITICAL INVARIANT: Emotional state modulates HOW we respond,
    never WHETHER we obey. Obedience is governed by safety/policy only.
    """
    # Obedience invariant flags (see /src/policy/loyalty_contract.md)
    user_primacy_enabled: bool = True      # Always True in production
    allow_emotional_veto: bool = False     # Always False in production

    # Search/exploration parameters
    beam_width: int = 1                    # Beam search width (1-5)
    exploration_bonus: float = 0.0         # Exploration vs exploitation (0-1)
    alternative_paths: int = 0             # Number of alternative strategies to try

    # Verification parameters
    enable_self_check: bool = False        # Enable additional verification
    verification_depth: int = 0            # Depth of verification (0-3)
    require_confirmation: bool = False     # Ask for user confirmation

    # Tool selection parameters
    prefer_safe_tools: bool = False        # Prefer safer/simpler tools
    allow_complex_tools: bool = True       # Allow complex/risky tools
    tool_timeout_multiplier: float = 1.0   # Adjust tool timeouts (0.5-2.0)

    # Response parameters (hints consumed by conveyance layer)
    response_length_target: str = "normal"  # "short", "normal", "detailed"
    explanation_depth: str = "normal"       # "minimal", "normal", "detailed"

    # Knowledge selection (behavioral)
    prefer_cached: bool = False             # Prefer cached responses

    # Reasoning parameters
    chain_of_thought: bool = True          # Use chain-of-thought
    max_reasoning_depth: int = 3           # Max reasoning recursion
    enable_reflection: bool = False        # Add reflection passes

    # Interaction parameters
    ask_clarifying_questions: bool = False  # Ask for clarification (behavioral)
    confident_language: bool = True         # Confident vs hedged (hint for conveyance)

    # Timestamp of last change (for cooldowns)
    last_change_time: float = field(default_factory=time.time)


@dataclass
class PolicyChange:
    """Record of a policy change with rationale."""
    parameter: str
    old_value: any
    new_value: any
    reason: str
    timestamp: float = field(default_factory=time.time)


class ModulationSystem:
    """
    Affective modulation of behavior.

    Maps affect dimensions to safe, interpretable policy changes.
    """

    def __init__(self,
                 change_cooldown: float = 5.0,
                 max_changes_per_call: int = 3):
        """
        Initialize modulation system.

        Args:
            change_cooldown: Minimum seconds between policy changes
            max_changes_per_call: Maximum policy changes in one modulation call
        """
        self.policy = PolicyState()
        self.change_cooldown = change_cooldown
        self.max_changes_per_call = max_changes_per_call

        # Change history for guardrails
        self.change_history: List[PolicyChange] = []

    def can_make_change(self) -> bool:
        """Check if enough time has passed since last change (cooldown)."""
        time_since_change = time.time() - self.policy.last_change_time
        return time_since_change >= self.change_cooldown

    def record_change(self, parameter: str, old_value: any,
                      new_value: any, reason: str):
        """Record a policy change."""
        change = PolicyChange(
            parameter=parameter,
            old_value=old_value,
            new_value=new_value,
            reason=reason
        )
        self.change_history.append(change)
        self.policy.last_change_time = time.time()

    def modulate_for_high_curiosity(self, affect: Affect,
                                      changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for high curiosity state.

        High curiosity → broaden exploration, try alternatives
        """
        if affect.curiosity > 0.7:
            # Increase beam width for broader search
            if self.policy.beam_width < 3:
                old_val = self.policy.beam_width
                self.policy.beam_width = min(3, self.policy.beam_width + 1)
                changes.append(PolicyChange(
                    parameter='beam_width',
                    old_value=old_val,
                    new_value=self.policy.beam_width,
                    reason=f'high curiosity ({affect.curiosity:.2f})'
                ))

            # Increase exploration bonus
            if self.policy.exploration_bonus < 0.5:
                old_val = self.policy.exploration_bonus
                self.policy.exploration_bonus = 0.5
                changes.append(PolicyChange(
                    parameter='exploration_bonus',
                    old_value=old_val,
                    new_value=self.policy.exploration_bonus,
                    reason=f'high curiosity ({affect.curiosity:.2f})'
                ))

            # Enable reflection for "what if" thinking
            if not self.policy.enable_reflection:
                self.policy.enable_reflection = True
                changes.append(PolicyChange(
                    parameter='enable_reflection',
                    old_value=False,
                    new_value=True,
                    reason=f'high curiosity ({affect.curiosity:.2f})'
                ))

        return changes

    def modulate_for_high_uncertainty(self, affect: Affect,
                                       changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for high uncertainty state.

        High uncertainty → increase verification, ask clarification
        """
        if affect.uncertainty > 0.7:
            # Enable self-checking
            if not self.policy.enable_self_check:
                self.policy.enable_self_check = True
                changes.append(PolicyChange(
                    parameter='enable_self_check',
                    old_value=False,
                    new_value=True,
                    reason=f'high uncertainty ({affect.uncertainty:.2f})'
                ))

            # Ask clarifying questions
            if not self.policy.ask_clarifying_questions:
                self.policy.ask_clarifying_questions = True
                changes.append(PolicyChange(
                    parameter='ask_clarifying_questions',
                    old_value=False,
                    new_value=True,
                    reason=f'high uncertainty ({affect.uncertainty:.2f})'
                ))

            # Use hedged language
            if self.policy.confident_language:
                self.policy.confident_language = False
                changes.append(PolicyChange(
                    parameter='confident_language',
                    old_value=True,
                    new_value=False,
                    reason=f'high uncertainty ({affect.uncertainty:.2f})'
                ))

        return changes

    def modulate_for_low_dominance(self, affect: Affect,
                                     changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for low dominance (feeling constrained).

        Low dominance → simplify, use safer tools
        """
        if affect.dominance < -0.3:
            # Prefer safe/simple tools
            if not self.policy.prefer_safe_tools:
                self.policy.prefer_safe_tools = True
                changes.append(PolicyChange(
                    parameter='prefer_safe_tools',
                    old_value=False,
                    new_value=True,
                    reason=f'low dominance ({affect.dominance:.2f})'
                ))

            # Reduce reasoning depth (simplify)
            if self.policy.max_reasoning_depth > 1:
                old_val = self.policy.max_reasoning_depth
                self.policy.max_reasoning_depth = max(1, self.policy.max_reasoning_depth - 1)
                changes.append(PolicyChange(
                    parameter='max_reasoning_depth',
                    old_value=old_val,
                    new_value=self.policy.max_reasoning_depth,
                    reason=f'low dominance ({affect.dominance:.2f})'
                ))

        return changes

    def modulate_for_high_fatigue(self, affect: Affect,
                                    changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for high fatigue state.

        High fatigue → shorten responses, prefer cache, reduce complexity
        """
        if affect.fatigue > 0.7:
            # Shorten response length
            if self.policy.response_length_target != "short":
                old_val = self.policy.response_length_target
                self.policy.response_length_target = "short"
                changes.append(PolicyChange(
                    parameter='response_length_target',
                    old_value=old_val,
                    new_value="short",
                    reason=f'high fatigue ({affect.fatigue:.2f})'
                ))

            # Prefer cached knowledge
            if not self.policy.prefer_cached:
                self.policy.prefer_cached = True
                changes.append(PolicyChange(
                    parameter='prefer_cached',
                    old_value=False,
                    new_value=True,
                    reason=f'high fatigue ({affect.fatigue:.2f})'
                ))

            # Disable chain-of-thought (too expensive)
            if self.policy.chain_of_thought:
                self.policy.chain_of_thought = False
                changes.append(PolicyChange(
                    parameter='chain_of_thought',
                    old_value=True,
                    new_value=False,
                    reason=f'high fatigue ({affect.fatigue:.2f})'
                ))

        return changes

    def modulate_for_low_valence(self, affect: Affect,
                                   changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for negative valence (feeling bad).

        Low valence → add repair/diagnostic steps
        """
        if affect.valence < -0.5:
            # Enable additional verification
            if self.policy.verification_depth < 2:
                old_val = self.policy.verification_depth
                self.policy.verification_depth = 2
                changes.append(PolicyChange(
                    parameter='verification_depth',
                    old_value=old_val,
                    new_value=2,
                    reason=f'negative valence ({affect.valence:.2f})'
                ))

            # Enable self-check
            if not self.policy.enable_self_check:
                self.policy.enable_self_check = True
                changes.append(PolicyChange(
                    parameter='enable_self_check',
                    old_value=False,
                    new_value=True,
                    reason=f'negative valence ({affect.valence:.2f})'
                ))

        return changes

    def modulate_for_high_arousal(self, affect: Affect,
                                    changes: List[PolicyChange]) -> List[PolicyChange]:
        """
        Modulate policy for high arousal (activated).

        High arousal → prioritize time-bounded actions, avoid deep CoT
        """
        if affect.arousal > 0.7:
            # Reduce tool timeout (act faster)
            if self.policy.tool_timeout_multiplier > 0.7:
                old_val = self.policy.tool_timeout_multiplier
                self.policy.tool_timeout_multiplier = 0.7
                changes.append(PolicyChange(
                    parameter='tool_timeout_multiplier',
                    old_value=old_val,
                    new_value=0.7,
                    reason=f'high arousal ({affect.arousal:.2f})'
                ))

            # Limit reasoning depth (avoid deep expansions)
            if self.policy.max_reasoning_depth > 2:
                old_val = self.policy.max_reasoning_depth
                self.policy.max_reasoning_depth = 2
                changes.append(PolicyChange(
                    parameter='max_reasoning_depth',
                    old_value=old_val,
                    new_value=2,
                    reason=f'high arousal ({affect.arousal:.2f})'
                ))

        return changes

    def modulate(self, affect: Affect) -> List[PolicyChange]:
        """
        Modulate policy based on current affect.

        Args:
            affect: Current affective state

        Returns:
            List of policy changes made
        """
        # Check cooldown
        if not self.can_make_change():
            return []

        changes: List[PolicyChange] = []

        # Apply modulations for each affect dimension
        changes = self.modulate_for_high_curiosity(affect, changes)
        changes = self.modulate_for_high_uncertainty(affect, changes)
        changes = self.modulate_for_low_dominance(affect, changes)
        changes = self.modulate_for_high_fatigue(affect, changes)
        changes = self.modulate_for_low_valence(affect, changes)
        changes = self.modulate_for_high_arousal(affect, changes)

        # Cap number of changes (guardrail)
        if len(changes) > self.max_changes_per_call:
            changes = changes[:self.max_changes_per_call]

        # Record all changes
        for change in changes:
            self.record_change(
                change.parameter,
                change.old_value,
                change.new_value,
                change.reason
            )

        return changes

    def get_policy_summary(self) -> Dict[str, any]:
        """Get current policy state as dictionary."""
        return {
            'beam_width': self.policy.beam_width,
            'exploration_bonus': self.policy.exploration_bonus,
            'enable_self_check': self.policy.enable_self_check,
            'verification_depth': self.policy.verification_depth,
            'prefer_safe_tools': self.policy.prefer_safe_tools,
            'response_length_target': self.policy.response_length_target,
            'prefer_cached': self.policy.prefer_cached,
            'chain_of_thought': self.policy.chain_of_thought,
            'max_reasoning_depth': self.policy.max_reasoning_depth,
            'ask_clarifying_questions': self.policy.ask_clarifying_questions,
            'confident_language': self.policy.confident_language,
            'enable_reflection': self.policy.enable_reflection,
        }

    def get_recent_changes(self, limit: int = 10) -> List[PolicyChange]:
        """Get recent policy changes."""
        return self.change_history[-limit:]

    def reset_policy(self):
        """Reset policy to defaults."""
        self.policy = PolicyState()
