"""
Goal System Data Models

Defines goals with homeostatic integration and neurochemical hooks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import time


class GoalState(Enum):
    """Goal lifecycle states."""
    PENDING = "pending"       # Accepted but not started
    ACTIVE = "active"         # Currently pursuing
    PROGRESSING = "progressing"  # Making progress
    BLOCKED = "blocked"       # Encountering obstacles
    PAUSED = "paused"         # Temporarily suspended
    COMPLETED = "completed"   # Successfully finished
    ABANDONED = "abandoned"   # Gave up
    FAILED = "failed"         # Could not complete


@dataclass
class GoalProperties:
    """Properties that determine goal value and priority."""
    alignment_with_purpose: float = 0.5   # How well aligned with identity (0-1)
    novelty: float = 0.5                   # How novel/interesting (0-1)
    difficulty: float = 0.5                # Estimated difficulty (0-1)
    impact: float = 0.5                    # Expected impact magnitude (0-1)
    urgency: float = 0.5                   # Time pressure (0-1)


@dataclass
class NeurochemicalState:
    """
    Future hook: Local neurochemical state per goal.

    Currently unused but provides attachment point for Phase 4
    neurochemical integration. Will eventually model dopamine/serotonin/cortisol
    dynamics with proper decay and reuptake kinetics.
    """
    # Neurotransmitter concentrations (0-1 normalized)
    dopamine: float = 0.0      # Reward/motivation signal
    serotonin: float = 0.0     # Confidence/stability signal
    cortisol: float = 0.0      # Stress/urgency signal

    # Prediction state for reward prediction error
    expected_progress_rate: float = 0.0   # Expected progress per unit time
    prediction_error: float = 0.0         # Actual - expected progress

    # Decay parameters (future use)
    dopamine_half_life: float = 0.95      # Per-tick decay
    serotonin_half_life: float = 0.98
    cortisol_half_life: float = 0.92

    # Timestamp for decay calculations (future use)
    last_updated: float = field(default_factory=time.time)


@dataclass
class Goal:
    """
    Represents a goal with affective consequences.

    Goals create homeostatic pressure → emotions → behavioral modulation.

    Design Philosophy:
        - Each goal is a homeostatic variable (progress → target)
        - Progress changes generate affective events
        - Future neurochemical state tracks reward signals
        - Simple numerical dynamics initially (no full kinetics yet)
    """
    id: str                           # Unique identifier
    description: str                  # Human-readable goal description

    # Goal state
    state: GoalState = GoalState.PENDING
    progress: float = 0.0             # 0.0 to 1.0 completion

    # Properties affecting motivational value
    properties: GoalProperties = field(default_factory=GoalProperties)

    # Homeostatic integration
    homeostatic_target: float = 1.0
    """
    Target progress for this goal in [0.0, 1.0].
    Normally 1.0 (fully complete), but allows partial
    completion to count as "enough" in special cases.
    """
    homeostatic_tolerance: float = 0.0
    """
    Acceptable deviation from target before pressure kicks in.
    Usually 0.0 (must complete exactly), but can be raised
    for "good enough" goals.
    """

    # Temporal tracking
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    last_updated: float = field(default_factory=time.time)

    # Progress history for computing deltas
    progress_history: List[Tuple[float, float]] = field(default_factory=list)  # [(timestamp, progress), ...]

    # Neurochemical state (future hook - Phase 4)
    neuro: NeurochemicalState = field(default_factory=NeurochemicalState)

    # Parent/child relationships for hierarchical goals
    parent_id: Optional[str] = None
    subgoal_ids: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict = field(default_factory=dict)

    @property
    def progress_delta(self) -> float:
        """
        Calculate recent progress change.

        Returns:
            Change in progress since last update
        """
        if len(self.progress_history) < 2:
            return 0.0

        recent_timestamp, recent_progress = self.progress_history[-1]
        prev_timestamp, prev_progress = self.progress_history[-2]

        return recent_progress - prev_progress

    @property
    def progress_rate(self) -> float:
        """
        Calculate progress rate (progress per second).

        Returns:
            Progress change per second
        """
        if len(self.progress_history) < 2:
            return 0.0

        recent_timestamp, recent_progress = self.progress_history[-1]
        prev_timestamp, prev_progress = self.progress_history[-2]

        time_delta = recent_timestamp - prev_timestamp
        if time_delta < 0.01:  # Avoid division by zero
            return 0.0

        return (recent_progress - prev_progress) / time_delta

    @property
    def is_active(self) -> bool:
        """Is this goal currently being pursued?"""
        return self.state in {GoalState.ACTIVE, GoalState.PROGRESSING, GoalState.BLOCKED}

    @property
    def is_complete(self) -> bool:
        """Is this goal finished?"""
        return self.state in {GoalState.COMPLETED, GoalState.ABANDONED, GoalState.FAILED}

    @property
    def homeostatic_error(self) -> float:
        """
        Homeostatic error: target - current.

        Positive = not yet complete, negative = overshot (rare)
        """
        return self.homeostatic_target - self.progress

    @property
    def homeostatic_pressure(self) -> float:
        """
        Affective pressure from goal incompletion (0.0 to 1.0).

        Follows same formula as consciousness homeostatic variables:
        - Within tolerance → 0.0 pressure
        - Outside tolerance → scaled pressure up to 1.0
        """
        abs_error = abs(self.homeostatic_error)
        if abs_error <= self.homeostatic_tolerance:
            return 0.0

        # Scale pressure from tolerance edge to maximum
        # Safety: prevent division by zero if tolerance = 1.0
        denom = max(1e-6, 1.0 - self.homeostatic_tolerance)
        return min(1.0, (abs_error - self.homeostatic_tolerance) / denom)

    def update_progress(self, new_progress: float, auto_state_update: bool = True):
        """
        Update progress and record in history.

        Args:
            new_progress: New progress value (0.0 to 1.0)
            auto_state_update: Automatically update state based on progress
        """
        now = time.time()

        # Seed progress history on first update so deltas are well-defined
        if not self.progress_history:
            self.progress_history.append((now, self.progress))

        old_progress = self.progress
        self.progress = max(0.0, min(1.0, new_progress))
        self.progress_history.append((now, self.progress))
        self.last_updated = now

        # Update state based on progress
        if auto_state_update:
            if self.progress >= 1.0 and self.state != GoalState.COMPLETED:
                self.state = GoalState.COMPLETED
                self.completed_at = now
            elif self.progress_delta > 0.05:
                # Making good progress
                self.state = GoalState.PROGRESSING
            elif abs(self.progress_delta) < 0.01 and self.state == GoalState.ACTIVE:
                # Stagnant - keep current state (don't auto-mark as blocked)
                pass

        # Update prediction error (future neurochemical hook)
        if self.neuro.expected_progress_rate > 0:
            time_delta = now - self.progress_history[-2][0] if len(self.progress_history) > 1 else 1.0
            expected_delta = self.neuro.expected_progress_rate * time_delta
            actual_delta = self.progress_delta
            self.neuro.prediction_error = actual_delta - expected_delta

            # Future: This prediction error will drive dopamine spikes
            # dopamine_spike = prediction_error * dopaminergic_gain
            # self.neuro.dopamine += dopamine_spike

    def activate(self):
        """Mark goal as active and start pursuing."""
        if self.state == GoalState.PENDING:
            self.state = GoalState.ACTIVE
            self.activated_at = time.time()

    def block(self, reason: Optional[str] = None):
        """Mark goal as blocked."""
        self.state = GoalState.BLOCKED
        if reason:
            self.metadata['block_reason'] = reason

    def pause(self):
        """Temporarily pause goal pursuit."""
        if self.is_active:
            self.state = GoalState.PAUSED

    def resume(self):
        """Resume paused goal."""
        if self.state == GoalState.PAUSED:
            self.state = GoalState.ACTIVE

    def abandon(self, reason: Optional[str] = None):
        """Give up on goal."""
        self.state = GoalState.ABANDONED
        self.completed_at = time.time()
        if reason:
            self.metadata['abandon_reason'] = reason

    def fail(self, reason: Optional[str] = None):
        """Mark goal as failed."""
        self.state = GoalState.FAILED
        self.completed_at = time.time()
        if reason:
            self.metadata['failure_reason'] = reason

    def add_subgoal(self, subgoal_id: str):
        """Add a subgoal to this goal's hierarchy."""
        if subgoal_id not in self.subgoal_ids:
            self.subgoal_ids.append(subgoal_id)

    def remove_subgoal(self, subgoal_id: str):
        """Remove a subgoal from this goal's hierarchy."""
        if subgoal_id in self.subgoal_ids:
            self.subgoal_ids.remove(subgoal_id)

    def to_dict(self) -> Dict:
        """Serialize goal to dictionary."""
        return {
            'id': self.id,
            'description': self.description,
            'state': self.state.value,
            'progress': self.progress,
            'properties': {
                'alignment_with_purpose': self.properties.alignment_with_purpose,
                'novelty': self.properties.novelty,
                'difficulty': self.properties.difficulty,
                'impact': self.properties.impact,
                'urgency': self.properties.urgency,
            },
            'homeostatic_target': self.homeostatic_target,
            'homeostatic_tolerance': self.homeostatic_tolerance,
            'homeostatic_pressure': self.homeostatic_pressure,
            'created_at': self.created_at,
            'activated_at': self.activated_at,
            'completed_at': self.completed_at,
            'last_updated': self.last_updated,
            'progress_delta': self.progress_delta,
            'progress_rate': self.progress_rate,
            'parent_id': self.parent_id,
            'subgoal_ids': self.subgoal_ids,
            'metadata': self.metadata,
        }
