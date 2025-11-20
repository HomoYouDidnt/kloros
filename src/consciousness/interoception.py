"""
Interoception Module - Collecting Internal Signals

This module collects low-hanging, model-agnostic signals about the system's
internal state. These signals feed into the appraisal system to generate
affective states.

Based on GPT suggestions for Phase 2B.
"""

import time
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque


@dataclass
class InteroceptiveSignals:
    """
    Collection of internal state signals.

    Contains both normalized signals (0-1 range) for affect processing,
    and raw values for precise threshold checks and evidence building.
    """
    # Task signals
    success_rate: float = 0.5           # Recent task success rate
    error_rate: float = 0.0             # Recent error rate
    retry_count: int = 0                # Number of retries on current task
    tool_call_latency: float = 0.0      # Current tool latency (normalized)
    queue_backlog: float = 0.0          # Task queue backlog (normalized)

    # Task counters (raw values for precise thresholds)
    task_successes: int = 0             # Recent successful tasks
    task_failures: int = 0              # Recent failed tasks
    exceptions: int = 0                 # Recent exception count

    # Learning signals
    novelty_score: float = 0.0          # How novel is current situation
    surprise: float = 0.0               # Prediction error magnitude
    confidence: float = 0.5             # Self-rated confidence (0-1)

    # Resource signals (normalized)
    token_budget_pressure: float = 0.0  # How tight is token budget
    context_length_pressure: float = 0.0 # Context window usage
    cache_hit_rate: float = 0.0         # Memory cache efficiency
    memory_pressure: float = 0.0        # RAM/storage pressure

    # Resource signals (raw values for precise tracking)
    token_usage: Optional[int] = None   # Current token usage
    token_budget: Optional[int] = None  # Total token budget
    context_length: Optional[int] = None # Current context length
    context_max: Optional[int] = None   # Maximum context length

    # Stability signals
    exception_rate: float = 0.0         # Recent exception frequency
    timeout_rate: float = 0.0           # Recent timeout frequency
    truncation_rate: float = 0.0        # Output truncation frequency

    # Social/interaction signals
    user_correction_count: int = 0      # Recent corrections received
    user_praise_count: int = 0          # Recent praise received
    interaction_frequency: float = 0.0  # How often user interacts

    # Timestamp
    timestamp: float = field(default_factory=time.time)


class InteroceptiveMonitor:
    """
    Monitors internal state signals over time.

    Uses exponential moving averages to smooth jitter and
    maintain running statistics for normalization.
    """

    def __init__(self, alpha: float = 0.2):
        """
        Initialize interoceptive monitor.

        Args:
            alpha: EMA smoothing factor (0-1). Lower = more smoothing.
        """
        self.alpha = alpha

        # Current smoothed signals
        self.current_signals = InteroceptiveSignals()

        # Running min/max for normalization
        self.signal_mins: Dict[str, float] = {}
        self.signal_maxs: Dict[str, float] = {}

        # History for computing rates
        self.success_history: deque = deque(maxlen=20)
        self.error_history: deque = deque(maxlen=20)
        self.exception_history: deque = deque(maxlen=20)
        self.timeout_history: deque = deque(maxlen=20)
        self.truncation_history: deque = deque(maxlen=20)

        # Counters for current episode
        self.current_retry_count = 0
        self.user_corrections_recent = 0
        self.user_praise_recent = 0

        # Timestamps for rate calculations
        self.last_interaction_time = time.time()
        self.interaction_times: deque = deque(maxlen=10)

    def normalize_signal(self, signal_name: str, value: float,
                         min_val: float = 0.0, max_val: float = 1.0) -> float:
        """
        Normalize signal to [0, 1] using running min/max.

        Args:
            signal_name: Name of signal for tracking stats
            value: Raw signal value
            min_val: Expected minimum value
            max_val: Expected maximum value

        Returns:
            Normalized value in [0, 1]
        """
        # Update running stats
        if signal_name not in self.signal_mins:
            self.signal_mins[signal_name] = min_val
            self.signal_maxs[signal_name] = max_val

        self.signal_mins[signal_name] = min(self.signal_mins[signal_name], value)
        self.signal_maxs[signal_name] = max(self.signal_maxs[signal_name], value)

        # Normalize
        range_val = self.signal_maxs[signal_name] - self.signal_mins[signal_name]
        if range_val < 1e-6:
            return 0.5  # No variance, return middle

        normalized = (value - self.signal_mins[signal_name]) / range_val
        return max(0.0, min(1.0, normalized))

    def smooth_signal(self, current: float, new_value: float) -> float:
        """
        Apply exponential moving average smoothing.

        Args:
            current: Current smoothed value
            new_value: New raw value

        Returns:
            Smoothed value
        """
        return self.alpha * new_value + (1 - self.alpha) * current

    def record_task_outcome(self, success: bool, retries: int = 0):
        """Record outcome of a task."""
        self.success_history.append(1.0 if success else 0.0)
        self.error_history.append(0.0 if success else 1.0)
        self.current_retry_count = retries

        # Update rates
        if len(self.success_history) > 0:
            self.current_signals.success_rate = sum(self.success_history) / len(self.success_history)
            self.current_signals.error_rate = sum(self.error_history) / len(self.error_history)

        # Update raw counts
        self.current_signals.task_successes = int(sum(self.success_history))
        self.current_signals.task_failures = int(sum(self.error_history))

        self.current_signals.retry_count = retries

    def record_exception(self):
        """Record an exception occurrence."""
        self.exception_history.append(1.0)
        if len(self.exception_history) > 0:
            self.current_signals.exception_rate = sum(self.exception_history) / len(self.exception_history)
            # Update raw exception count
            self.current_signals.exceptions = int(sum(self.exception_history))

    def record_timeout(self):
        """Record a timeout occurrence."""
        self.timeout_history.append(1.0)
        if len(self.timeout_history) > 0:
            self.current_signals.timeout_rate = sum(self.timeout_history) / len(self.timeout_history)

    def record_truncation(self):
        """Record an output truncation."""
        self.truncation_history.append(1.0)
        if len(self.truncation_history) > 0:
            self.current_signals.truncation_rate = sum(self.truncation_history) / len(self.truncation_history)

    def update_tool_latency(self, latency_seconds: float, baseline: float = 1.0):
        """
        Update tool call latency signal.

        Args:
            latency_seconds: Actual latency in seconds
            baseline: Expected baseline latency for normalization
        """
        normalized_latency = self.normalize_signal('latency', latency_seconds, 0.0, baseline * 3.0)
        self.current_signals.tool_call_latency = self.smooth_signal(
            self.current_signals.tool_call_latency,
            normalized_latency
        )

    def update_resource_pressure(self,
                                  token_usage: Optional[int] = None,
                                  token_budget: Optional[int] = None,
                                  context_length: Optional[int] = None,
                                  context_max: Optional[int] = None,
                                  memory_mb: Optional[float] = None):
        """
        Update resource pressure signals.

        Args:
            token_usage: Current token usage
            token_budget: Total token budget
            context_length: Current context length
            context_max: Maximum context length
            memory_mb: Current memory usage in MB
        """
        # Store raw values for precise threshold checks
        if token_usage is not None:
            self.current_signals.token_usage = token_usage
        if token_budget is not None:
            self.current_signals.token_budget = token_budget
        if context_length is not None:
            self.current_signals.context_length = context_length
        if context_max is not None:
            self.current_signals.context_max = context_max

        # Calculate normalized pressure values
        if token_usage is not None and token_budget is not None and token_budget > 0:
            token_pressure = token_usage / token_budget
            self.current_signals.token_budget_pressure = self.smooth_signal(
                self.current_signals.token_budget_pressure,
                min(1.0, token_pressure)
            )

        if context_length is not None and context_max is not None and context_max > 0:
            context_pressure = context_length / context_max
            self.current_signals.context_length_pressure = self.smooth_signal(
                self.current_signals.context_length_pressure,
                min(1.0, context_pressure)
            )

        if memory_mb is not None:
            # Normalize against 1GB = high pressure
            memory_pressure = min(1.0, memory_mb / 1024.0)
            self.current_signals.memory_pressure = self.smooth_signal(
                self.current_signals.memory_pressure,
                memory_pressure
            )

    def update_learning_signals(self,
                                 novelty: Optional[float] = None,
                                 surprise: Optional[float] = None,
                                 confidence: Optional[float] = None):
        """
        Update learning-related signals.

        Args:
            novelty: Novelty score (0-1)
            surprise: Surprise/prediction error (0-1)
            confidence: Self-rated confidence (0-1)
        """
        if novelty is not None:
            self.current_signals.novelty_score = self.smooth_signal(
                self.current_signals.novelty_score,
                max(0.0, min(1.0, novelty))
            )

        if surprise is not None:
            self.current_signals.surprise = self.smooth_signal(
                self.current_signals.surprise,
                max(0.0, min(1.0, surprise))
            )

        if confidence is not None:
            self.current_signals.confidence = self.smooth_signal(
                self.current_signals.confidence,
                max(0.0, min(1.0, confidence))
            )

    def record_user_correction(self):
        """Record a user correction ("that's wrong", etc.)."""
        self.user_corrections_recent += 1
        self.current_signals.user_correction_count = self.user_corrections_recent

    def record_user_praise(self):
        """Record user praise/thanks."""
        self.user_praise_recent += 1
        self.current_signals.user_praise_count = self.user_praise_recent

    def record_user_interaction(self):
        """Record a user interaction for frequency tracking."""
        current_time = time.time()
        self.interaction_times.append(current_time)

        # Calculate interaction frequency (interactions per minute)
        if len(self.interaction_times) >= 2:
            time_span = self.interaction_times[-1] - self.interaction_times[0]
            if time_span > 0:
                freq = len(self.interaction_times) / (time_span / 60.0)
                self.current_signals.interaction_frequency = self.smooth_signal(
                    self.current_signals.interaction_frequency,
                    min(1.0, freq / 10.0)  # Normalize: 10 interactions/min = 1.0
                )

        self.last_interaction_time = current_time

    def update_cache_metrics(self, hits: int, total: int):
        """
        Update cache hit rate.

        Args:
            hits: Number of cache hits
            total: Total cache lookups
        """
        if total > 0:
            hit_rate = hits / total
            self.current_signals.cache_hit_rate = self.smooth_signal(
                self.current_signals.cache_hit_rate,
                hit_rate
            )

    def decay_episode_counters(self, decay_rate: float = 0.1):
        """
        Decay episodic counters (e.g., corrections, praise).
        Call this periodically to prevent old counts from dominating.

        Args:
            decay_rate: How much to decay per call
        """
        self.user_corrections_recent = int(self.user_corrections_recent * (1 - decay_rate))
        self.user_praise_recent = int(self.user_praise_recent * (1 - decay_rate))
        self.current_retry_count = int(self.current_retry_count * (1 - decay_rate))

    def get_current_signals(self) -> InteroceptiveSignals:
        """Get current snapshot of interoceptive signals."""
        signals = InteroceptiveSignals()

        # Copy all current values
        signals.success_rate = self.current_signals.success_rate
        signals.error_rate = self.current_signals.error_rate
        signals.retry_count = self.current_signals.retry_count
        signals.tool_call_latency = self.current_signals.tool_call_latency
        signals.queue_backlog = self.current_signals.queue_backlog

        # Copy raw task counters
        signals.task_successes = self.current_signals.task_successes
        signals.task_failures = self.current_signals.task_failures
        signals.exceptions = self.current_signals.exceptions

        signals.novelty_score = self.current_signals.novelty_score
        signals.surprise = self.current_signals.surprise
        signals.confidence = self.current_signals.confidence

        signals.token_budget_pressure = self.current_signals.token_budget_pressure
        signals.context_length_pressure = self.current_signals.context_length_pressure
        signals.cache_hit_rate = self.current_signals.cache_hit_rate
        signals.memory_pressure = self.current_signals.memory_pressure

        # Copy raw resource values
        signals.token_usage = self.current_signals.token_usage
        signals.token_budget = self.current_signals.token_budget
        signals.context_length = self.current_signals.context_length
        signals.context_max = self.current_signals.context_max

        signals.exception_rate = self.current_signals.exception_rate
        signals.timeout_rate = self.current_signals.timeout_rate
        signals.truncation_rate = self.current_signals.truncation_rate

        signals.user_correction_count = self.current_signals.user_correction_count
        signals.user_praise_count = self.current_signals.user_praise_count
        signals.interaction_frequency = self.current_signals.interaction_frequency

        signals.timestamp = time.time()

        return signals

    def get_signal_summary(self) -> Dict[str, float]:
        """
        Get summary of key signals for reporting.

        Returns:
            Dictionary of signal name -> value
        """
        signals = self.get_current_signals()
        return {
            'success_rate': signals.success_rate,
            'error_rate': signals.error_rate,
            'surprise': signals.surprise,
            'confidence': signals.confidence,
            'token_pressure': signals.token_budget_pressure,
            'context_pressure': signals.context_length_pressure,
            'memory_pressure': signals.memory_pressure,
            'stability': 1.0 - (signals.exception_rate + signals.timeout_rate) / 2.0,
            'user_satisfaction': (signals.user_praise_count - signals.user_correction_count) / 10.0,
        }
