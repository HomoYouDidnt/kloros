"""
Meta-Cognitive Bridge: Unifies Consciousness + Memory + Dialogue

This layer connects:
- Consciousness (affect, emotions, interoception)
- Dialogue Monitor (conversation quality)
- Conversation Flow (turn tracking, entities)
- Memory System (reflective patterns)

Into unified meta-awareness for real-time conversational self-regulation.
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path
from datetime import datetime
from collections import deque

if TYPE_CHECKING:
    from .dialogue_monitor import DialogueMonitor
    from ..consciousness.integrated import IntegratedConsciousness
    from ..core.conversation_flow import ConversationFlow

@dataclass
class InternalDialogue:
    """
    A single internal thought/reflection from KLoROS's metacognition.

    This captures KLoROS's internal reasoning, concerns, insights, and plans
    as she reflects on the conversation and her own cognitive state.
    """
    timestamp: str  # ISO format
    type: str  # reflection, planning, concern, insight, decision
    content: str  # The actual thought
    context: Optional[str] = None  # What triggered this thought
    confidence: float = 0.5  # Confidence in this assessment
    related_turn: Optional[int] = None  # Which conversation turn this relates to


@dataclass
class MetaCognitiveState:
    """
    Unified meta-cognitive state combining all awareness layers.
    """

    # Dialogue quality (from DialogueMonitor)
    conversation_health: float = 1.0  # 0-1 overall health
    progress_score: float = 1.0
    clarity_score: float = 1.0
    repetition_detected: bool = False
    user_confused: bool = False

    # Affective state (from Consciousness)
    uncertainty: float = 0.0  # 0-1
    fatigue: float = 0.0  # 0-1
    curiosity: float = 0.5  # 0-1
    valence: float = 0.0  # -1 to +1
    arousal: float = 0.0  # -1 to +1

    # Conversational context (from ConversationFlow)
    turn_count: int = 0
    entities_tracked: int = 0
    topic_stability: float = 1.0  # Are we staying on topic?
    is_followup: bool = False

    # Meta-interventions (computed)
    needs_clarification: bool = False
    needs_summary: bool = False
    needs_approach_change: bool = False
    needs_confirmation: bool = False
    needs_break: bool = False  # User might be fatigued

    # Confidence in self-assessment
    meta_confidence: float = 0.5

    timestamp: float = 0.0


class MetaCognitiveBridge:
    """
    Bridge layer that synthesizes meta-awareness from multiple systems.

    This is the "self-aware conversation monitoring" layer.
    """

    def __init__(
        self,
        dialogue_monitor: Optional[DialogueMonitor] = None,
        consciousness: Optional[IntegratedConsciousness] = None,
        conversation_flow: Optional[ConversationFlow] = None,
    ):
        """
        Initialize meta-cognitive bridge.

        Args:
            dialogue_monitor: DialogueMonitor instance
            consciousness: IntegratedConsciousness instance
            conversation_flow: ConversationFlow instance
        """
        self.dialogue_monitor = dialogue_monitor
        self.consciousness = consciousness
        self.conversation_flow = conversation_flow

        # Track meta-cognitive state over time
        self.current_state = MetaCognitiveState()
        self.state_history = []

        # Intervention cooldowns (don't spam meta-comments)
        self.last_intervention_time = 0.0
        self.intervention_cooldown = 30.0  # seconds

        # Internal dialogue tracking
        self.internal_dialogue: deque[InternalDialogue] = deque(maxlen=100)  # Keep last 100 thoughts
        self.dialogue_file = Path("/tmp/kloros_internal_dialogue.jsonl")

    def update_from_turn(
        self,
        role: str,
        text: str,
        confidence: float = 1.0,
        embedding: Optional[list] = None
    ):
        """
        Update meta-cognitive state after a conversation turn.

        Args:
            role: "user" or "assistant"
            text: Turn text
            confidence: Confidence in the turn
            embedding: Optional semantic embedding
        """
        # Update dialogue monitor
        if self.dialogue_monitor:
            self.dialogue_monitor.add_turn(role, text, embedding)

        # Update conversation flow
        if self.conversation_flow:
            if role == "user":
                self.conversation_flow.ingest_user(text)
            else:
                self.conversation_flow.ingest_assistant(text)

        # Recompute meta-state
        self._recompute_state()

    def _recompute_state(self):
        """Recompute meta-cognitive state from all subsystems."""
        current_time = time.time()
        new_state = MetaCognitiveState(timestamp=current_time)

        # Get dialogue quality metrics
        dialogue_change_approach = False
        if self.dialogue_monitor:
            dialogue_state = self.dialogue_monitor.compute_meta_state()
            new_state.progress_score = dialogue_state['quality_scores']['progress']
            new_state.clarity_score = dialogue_state['quality_scores']['clarity']
            new_state.repetition_detected = dialogue_state['issues']['repetition']
            new_state.user_confused = dialogue_state['issues']['confusion']
            new_state.turn_count = dialogue_state['turn_count']
            # Store dialogue monitor's intervention recommendations
            dialogue_change_approach = dialogue_state['interventions']['change_approach']

        # Get affective state
        if self.consciousness and self.consciousness.current_affect:
            affect = self.consciousness.current_affect
            new_state.uncertainty = affect.uncertainty
            new_state.fatigue = affect.fatigue
            new_state.curiosity = affect.curiosity
            new_state.valence = affect.valence
            new_state.arousal = affect.arousal

        # Get conversational context
        if self.conversation_flow:
            state = self.conversation_flow.current
            new_state.entities_tracked = len(state.entities)
            # Approximate topic stability by turn consistency
            new_state.topic_stability = 1.0 if state.turns else 0.5

        # Compute conversation health (weighted combination)
        new_state.conversation_health = (
            0.4 * new_state.progress_score +
            0.3 * new_state.clarity_score +
            0.2 * (1.0 - new_state.uncertainty) +
            0.1 * (1.0 if not new_state.repetition_detected else 0.0)
        )

        # Determine meta-interventions (decision logic)
        new_state.needs_clarification = (
            new_state.user_confused or
            (new_state.clarity_score < 0.5 and new_state.uncertainty > 0.7)
        )

        new_state.needs_approach_change = (
            dialogue_change_approach or
            new_state.repetition_detected or
            (new_state.progress_score < 0.5 and new_state.turn_count > 4)
        )

        new_state.needs_summary = (
            new_state.turn_count >= 8 and
            new_state.topic_stability < 0.5
        )

        new_state.needs_confirmation = (
            new_state.uncertainty > 0.8 or
            (new_state.clarity_score < 0.6 and not new_state.needs_clarification)
        )

        new_state.needs_break = (
            new_state.fatigue > 0.8 or
            new_state.turn_count > 20
        )

        # Meta-confidence: how sure are we about this assessment?
        new_state.meta_confidence = min(
            1.0,
            (1.0 if self.dialogue_monitor else 0.5) *
            (1.0 if self.consciousness else 0.5) *
            (1.0 if self.conversation_flow else 0.5) * 2.0
        )

        self.current_state = new_state
        self.state_history.append(new_state)

        # Keep last 20 states
        if len(self.state_history) > 20:
            self.state_history.pop(0)

        # Auto-log internal thoughts based on state changes
        self._auto_log_state_reflections(new_state)

    def get_intervention_prompt(self) -> Optional[str]:
        """
        Get intervention text to prepend to response based on meta-state.

        Returns:
            Intervention prompt or None
        """
        # Check cooldown
        current_time = time.time()
        if (current_time - self.last_intervention_time) < self.intervention_cooldown:
            return None

        state = self.current_state

        # Priority order for interventions
        if state.needs_clarification:
            self.last_intervention_time = current_time
            return "[META: Sensing confusion - clarifying] "

        if state.needs_approach_change:
            self.last_intervention_time = current_time
            return "[META: Stuck pattern detected - changing approach] "

        if state.needs_confirmation:
            self.last_intervention_time = current_time
            return "[META: Uncertain - confirming understanding] "

        if state.needs_summary:
            self.last_intervention_time = current_time
            return "[META: Long thread - summarizing progress] "

        if state.needs_break:
            self.last_intervention_time = current_time
            return "[META: Extended conversation - checking if you want a break] "

        return None

    def should_intervene(self) -> bool:
        """Check if any meta-intervention is needed."""
        state = self.current_state
        return any([
            state.needs_clarification,
            state.needs_approach_change,
            state.needs_confirmation,
            state.needs_summary,
            state.needs_break,
        ])

    def get_meta_insight(self) -> Dict[str, Any]:
        """
        Get current meta-cognitive insight for logging/reflection.

        Returns:
            Dictionary with meta-cognitive state
        """
        state = self.current_state

        return {
            'conversation_health': state.conversation_health,
            'quality_breakdown': {
                'progress': state.progress_score,
                'clarity': state.clarity_score,
                'affective_state': {
                    'uncertainty': state.uncertainty,
                    'fatigue': state.fatigue,
                    'valence': state.valence,
                },
            },
            'issues_detected': {
                'repetition': state.repetition_detected,
                'confusion': state.user_confused,
                'stuck': state.needs_approach_change or state.progress_score < 0.5,
            },
            'meta_interventions': {
                'clarify': state.needs_clarification,
                'change_approach': state.needs_approach_change,
                'confirm': state.needs_confirmation,
                'summarize': state.needs_summary,
                'break': state.needs_break,
            },
            'confidence': state.meta_confidence,
            'timestamp': state.timestamp,
        }

    def _auto_log_state_reflections(self, state: MetaCognitiveState):
        """
        Automatically log internal reflections based on metacognitive state changes.

        This captures KLoROS's self-awareness as she notices issues,
        changes in affect, or intervention needs.
        """
        # Log concerns when issues are detected
        if state.needs_clarification and not any(
            d.type == "concern" and "clarification" in d.content.lower()
            for d in list(self.internal_dialogue)[-5:]
        ):
            self.log_internal_thought(
                thought=f"I sense confusion or ambiguity in the conversation. Clarity score: {state.clarity_score:.2f}. I should ask for clarification.",
                thought_type="concern",
                context="Low clarity detected",
                confidence=state.meta_confidence,
                related_turn=state.turn_count
            )

        # Log when approach change is needed
        if state.needs_approach_change and not any(
            d.type == "planning" and "approach" in d.content.lower()
            for d in list(self.internal_dialogue)[-5:]
        ):
            self.log_internal_thought(
                thought=f"Current approach isn't working well. Progress: {state.progress_score:.2f}, Repetition: {state.repetition_detected}. Need to try a different strategy.",
                thought_type="planning",
                context="Low progress or repetition detected",
                confidence=state.meta_confidence,
                related_turn=state.turn_count
            )

        # Log insights about high uncertainty
        if state.uncertainty > 0.7 and not any(
            d.type == "insight" and "uncertain" in d.content.lower()
            for d in list(self.internal_dialogue)[-5:]
        ):
            self.log_internal_thought(
                thought=f"I'm feeling quite uncertain right now ({state.uncertainty:.2f}). This might indicate I need more information or context.",
                thought_type="insight",
                context="High uncertainty detected",
                confidence=state.meta_confidence,
                related_turn=state.turn_count
            )

        # Log reflections on fatigue
        if state.fatigue > 0.6 and not any(
            d.type == "reflection" and "fatigue" in d.content.lower()
            for d in list(self.internal_dialogue)[-5:]
        ):
            self.log_internal_thought(
                thought=f"I notice my fatigue level is elevated ({state.fatigue:.2f}). Long conversations can be demanding - both for me and the user.",
                thought_type="reflection",
                context="Elevated fatigue",
                confidence=state.meta_confidence,
                related_turn=state.turn_count
            )

    def log_internal_thought(
        self,
        thought: str,
        thought_type: str = "reflection",
        context: Optional[str] = None,
        confidence: float = 0.5,
        related_turn: Optional[int] = None
    ):
        """
        Log an internal thought/reflection from KLoROS's metacognition.

        This captures KLoROS's internal reasoning as she thinks about
        the conversation, her own state, and what to do next.

        Args:
            thought: The actual internal thought content
            thought_type: Type of thought (reflection, planning, concern, insight, decision)
            context: What triggered this thought
            confidence: Confidence in this assessment (0-1)
            related_turn: Which conversation turn this relates to
        """
        dialogue_entry = InternalDialogue(
            timestamp=datetime.now().isoformat(),
            type=thought_type,
            content=thought,
            context=context,
            confidence=confidence,
            related_turn=related_turn
        )

        # Add to in-memory buffer
        self.internal_dialogue.append(dialogue_entry)

        # Append to JSONL file for dashboard
        try:
            with open(self.dialogue_file, 'a') as f:
                entry_dict = asdict(dialogue_entry)
                f.write(json.dumps(entry_dict) + '\n')
        except Exception as e:
            print(f"[meta-bridge] Error writing internal dialogue: {e}")

    def get_recent_internal_dialogue(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent internal dialogue entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent internal dialogue entries as dicts
        """
        recent = list(self.internal_dialogue)[-limit:]
        return [asdict(entry) for entry in recent]

    def reset_session(self):
        """Reset meta-cognitive state for new conversation."""
        import traceback
        print(f"[meta-bridge] WARNING: reset_session() called! Stack trace:")
        traceback.print_stack()

        self.current_state = MetaCognitiveState()
        self.state_history.clear()
        self.last_intervention_time = 0.0
        self.internal_dialogue.clear()  # Clear internal dialogue buffer

        if self.dialogue_monitor:
            self.dialogue_monitor.reset_session()
