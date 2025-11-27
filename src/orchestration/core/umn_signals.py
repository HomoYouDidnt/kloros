"""
Canonical UMN Signal Definitions for KLoROS

This module defines all UMN signals used across the KLoROS orchestration system.
Each signal includes documentation of its Facts structure, emitters, and consumers.

Signal Naming Conventions:
    Q_* = Query/trigger signals (expect response from consumer daemons)
    AFFECT_* = Affective system outputs
    OBSERVATION = Raw observations from monitors
    CAPABILITY_GAP = Capability detection signals
    METRICS_* = Telemetry outputs
    USER_* = User interaction signals

Channel Classification (Phase 1 - metadata only):
    legacy  = Current pub/sub behavior (backward compatible default)
    reflex  = Fast, ordered, acknowledged (safety-critical, future)
    affect  = Modulatory, fire-and-forget (state changes, mood)
    trophic = Slow, batched, eventual consistency (telemetry, reflection)

See UMN_CHANNELS_DESIGN.md for full architecture.
"""

from enum import Enum


class ReflectionSignal(str, Enum):
    """UMN signals for reflection system orchestration."""

    TRIGGER = "Q_REFLECT_TRIGGER"
    COMPLETE = "Q_REFLECTION_COMPLETE"


class HousekeepingSignal(str, Enum):
    """UMN signals for housekeeping system orchestration."""

    TRIGGER = "Q_HOUSEKEEPING_TRIGGER"
    COMPLETE = "Q_HOUSEKEEPING_COMPLETE"


class DreamSignal(str, Enum):
    """UMN signals for D-REAM evolution system."""

    TRIGGER = "Q_DREAM_TRIGGER"
    COMPLETE = "Q_DREAM_COMPLETE"


class InvestigationSignal(str, Enum):
    """UMN signals for curiosity investigation system."""

    TRIGGER = "Q_CURIOSITY_INVESTIGATE"
    COMPLETE = "Q_INVESTIGATION_COMPLETE"
    AFFECTIVE_DEMAND = "Q_AFFECTIVE_DEMAND"


class VoiceSignal(str, Enum):
    """UMN signals for voice interaction system."""

    USER_INTERACTION = "USER_VOICE_INTERACTION"


class ObservationSignal(str, Enum):
    """UMN signals for system observation and monitoring."""

    OBSERVATION = "OBSERVATION"
    CAPABILITY_GAP = "CAPABILITY_GAP"


class MetricsSignal(str, Enum):
    """UMN signals for system metrics and telemetry."""

    SUMMARY = "METRICS_SUMMARY"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"


Q_REFLECT_TRIGGER = ReflectionSignal.TRIGGER.value
"""
Trigger reflection cycle.

Facts Structure:
    {
        "trigger_reason": str,              # Reason for reflection ("idle_period", "scheduled", "manual")
        "idle_seconds": float,              # Seconds since last user interaction (for idle triggers)
        "reflection_depth": int,            # Optional: Number of reflection phases to execute (1-4)
        "force": bool,                      # Optional: Force reflection even if interval not elapsed
    }

Emitters:
    - Voice system (during idle periods)
    - Policy engine (scheduled triggers)
    - Manual triggers (development/testing)

Consumers:
    - ReflectionConsumerDaemon: Executes reflection cycle, emits Q_REFLECTION_COMPLETE

Ecosystem: "voice" | "orchestration"
Intensity: 1.0 (standard trigger)
Channel: trophic (batchable, delayed processing acceptable)
"""

Q_REFLECTION_COMPLETE = ReflectionSignal.COMPLETE.value
"""
Reflection cycle completed.

Facts Structure:
    {
        "cycle_number": int,                # Sequential reflection cycle number
        "insights_generated": int,          # Number of insights generated this cycle
        "top_insights": List[str],          # Top N insights (summarized)
        "processing_time_ms": float,        # Time taken for reflection cycle
        "phases_executed": List[str],       # Which phases ran: ["semantic", "metacognitive", "synthesis", "optimization"]
        "stored_to_memory": bool,           # Whether insights were stored to memory system
        "error": Optional[str],             # Error message if reflection failed
    }

Emitters:
    - ReflectionConsumerDaemon: After completing reflection cycle

Consumers:
    - Alert system: Surfaces insights to user
    - D-REAM integration: Feeds reflection insights into evolution
    - Learning modules: Uses insights for self-improvement
    - Consciousness system: Updates affective state based on insights

Ecosystem: "orchestration"
Intensity: Variable (based on insight quality/urgency)
Channel: trophic (informational, eventual consistency)
"""

Q_HOUSEKEEPING_TRIGGER = HousekeepingSignal.TRIGGER.value
"""
Trigger housekeeping maintenance tasks.

Facts Structure:
    {
        "trigger_reason": str,              # Reason for housekeeping ("scheduled", "maintenance_window", "manual", "forced")
        "force": bool,                      # Skip interval check and run immediately
        "tasks": Optional[List[str]],       # Specific tasks to run (if None, run all)
        "maintenance_window": bool,         # Whether triggered during preferred maintenance window
    }

Emitters:
    - Voice system (during maintenance windows)
    - Policy engine (scheduled 24h triggers)
    - Alert system (on AFFECT_RESOURCE_STRAIN)
    - Manual triggers (development/testing)

Consumers:
    - HousekeepingDaemon: Executes maintenance tasks, emits Q_HOUSEKEEPING_COMPLETE

Ecosystem: "orchestration" | "voice"
Intensity: 1.0 (standard trigger) | 1.5 (forced/urgent)
Channel: trophic (maintenance, delayed processing acceptable)
"""

Q_HOUSEKEEPING_COMPLETE = HousekeepingSignal.COMPLETE.value
"""
Housekeeping tasks completed.

Facts Structure:
    {
        "tasks_executed": List[str],        # Names of tasks executed
        "tasks_succeeded": List[str],       # Tasks that completed successfully
        "tasks_failed": List[str],          # Tasks that failed
        "processing_time_ms": float,        # Total time for all tasks
        "space_freed_bytes": int,           # Disk space freed (if applicable)
        "files_cleaned": int,               # Number of files cleaned/removed
        "error": Optional[str],             # Error message if critical failure
    }

Emitters:
    - HousekeepingDaemon: After completing maintenance cycle

Consumers:
    - Alert system: Notifies user if maintenance freed significant space
    - Metrics aggregator: Tracks housekeeping performance over time
    - Policy engine: Adjusts housekeeping interval based on results

Ecosystem: "orchestration"
Intensity: Variable (based on urgency/results)
Channel: trophic (informational, eventual consistency)
"""

USER_VOICE_INTERACTION = VoiceSignal.USER_INTERACTION.value
"""
User spoke via voice interface.

Facts Structure:
    {
        "transcript": str,                  # What the user said (transcribed text)
        "confidence": float,                # Transcription confidence (0.0-1.0)
        "source": str,                      # "voice_input" | "wake_word"
        "wake_word_detected": bool,         # Whether wake word was detected
        "timestamp": float,                 # Unix timestamp of interaction
        "audio_duration_ms": float,         # Duration of audio input
    }

Emitters:
    - Voice system: After wake word detection and successful transcription

Consumers:
    - Consciousness system: Updates affective state on user interaction
    - Introspection daemon: Tracks user engagement patterns
    - Policy engine: Resets idle timers
    - Alert system: Clears pending alerts if user is actively engaged

Ecosystem: "voice"
Intensity: confidence score (0.0-1.0)
Channel: affect (state change, fire-and-forget)
"""

Q_DREAM_TRIGGER = DreamSignal.TRIGGER.value
"""
Trigger D-REAM (Darwinian-RZero Evolution & Anti-collapse Module) cycle.

Facts Structure:
    {
        "reason": str,                      # "periodic_optimization" | "capability_promotion" | "policy_trigger"
        "topic": str,                       # Topic area for evolution
        "promotion_count": int,             # Number of promotions triggering this cycle
        "force": bool,                      # Optional: Force execution even in maintenance mode
    }

Emitters:
    - Policy engine: Scheduled triggers
    - Promotion daemon: On capability promotions
    - Manual triggers (development/testing)

Consumers:
    - DreamConsumerDaemon: Executes D-REAM cycle, emits Q_DREAM_COMPLETE

Ecosystem: "orchestration"
Intensity: 1.0 (standard trigger)
Channel: trophic (evolution, delayed processing acceptable)
"""

Q_DREAM_COMPLETE = DreamSignal.COMPLETE.value
"""
D-REAM cycle execution completed.

Facts Structure:
    {
        "cycle_id": str,                    # Unique cycle identifier
        "execution_time_ms": float,         # Time taken for cycle
        "winners_selected": int,            # Number of tournament winners
        "capabilities_evolved": List[str],  # Capabilities that evolved
        "error": Optional[str],             # Error message if cycle failed
    }

Emitters:
    - DreamConsumerDaemon: After completing D-REAM cycle

Consumers:
    - Metrics aggregator: Tracks D-REAM performance
    - Winner deployer: Deploys evolved capabilities

Ecosystem: "orchestration"
Intensity: Variable (based on evolution significance)
Channel: trophic (informational, eventual consistency)
"""

CAPABILITY_GAP = ObservationSignal.CAPABILITY_GAP.value
"""
Capability gap detected in system.

Facts Structure:
    {
        "gap_type": str,                    # "missing" | "incomplete" | "outdated"
        "gap_name": str,                    # Name of missing/incomplete capability
        "gap_category": str,                # Category (e.g., "inference", "memory", "orchestration")
        "severity": str,                    # "low" | "medium" | "high" | "critical"
        "detection_method": str,            # How gap was detected
        "recommended_actions": List[str],   # Suggested remediation actions
    }

Emitters:
    - Introspection daemon: From capability scanners
    - Manual observations (development)

Consumers:
    - CuriosityCoreConsumerDaemon: Generates investigation questions
    - Alert system: Surfaces critical gaps

Ecosystem: "introspection"
Intensity: Variable (based on severity)
Channel: affect (low/medium severity) or reflex (critical severity)
"""

Q_CURIOSITY_INVESTIGATE = InvestigationSignal.TRIGGER.value
"""
Request investigation of a module or question.

Facts Structure:
    {
        "question": str,                    # Investigation question
        "module_path": Optional[str],       # Module to investigate
        "priority": str,                    # "low" | "medium" | "high" | "emergency"
        "source": str,                      # Who/what requested investigation
        "context": Dict[str, Any],          # Additional context for investigation
    }

Emitters:
    - CuriosityCoreConsumerDaemon: From capability gaps
    - Affective system: From AFFECT_* signals
    - Manual requests

Consumers:
    - InvestigationConsumerDaemon: Performs deep code analysis

Ecosystem: "curiosity"
Intensity: Variable (based on priority)
Channel: trophic (investigation queue, batch processing)
"""

Q_INVESTIGATION_COMPLETE = InvestigationSignal.COMPLETE.value
"""
Investigation completed.

Facts Structure:
    {
        "question": str,                    # Original question investigated
        "findings": str,                    # Investigation findings
        "confidence": float,                # Confidence in findings (0.0-1.0)
        "recommendations": List[str],       # Recommended actions
        "processing_time_ms": float,        # Time taken for investigation
    }

Emitters:
    - InvestigationConsumerDaemon: After completing investigation

Consumers:
    - CuriosityCore: Updates question status
    - Alert system: Surfaces important findings

Ecosystem: "curiosity"
Intensity: Variable (based on finding importance)
Channel: trophic (results, eventual consistency)
"""

Q_AFFECTIVE_DEMAND = InvestigationSignal.AFFECTIVE_DEMAND.value
"""
Affective system demand signal.

Facts Structure:
    {
        "demand_type": str,              # Type of affective demand
        "priority": str,                 # "low" | "medium" | "high" | "urgent"
        "source": str,                   # System requesting investigation
        "context": Dict[str, Any],       # Additional context
    }

Emitters:
    - Affective system: On emotional state changes requiring investigation
    - Consciousness system: On significant affective events

Consumers:
    - InvestigationConsumerDaemon: Investigates affective demands

Ecosystem: "affect"
Intensity: Variable (based on priority)
Channel: affect (low/medium/high priority) or reflex (urgent priority)
"""

OBSERVATION = ObservationSignal.OBSERVATION.value
"""
Raw system observation.

Facts Structure:
    {
        "source": str,                      # Observation source
        "observation_type": str,            # Type of observation
        "data": Dict[str, Any],             # Observation data
        "timestamp": float,                 # Unix timestamp
    }

Emitters:
    - Various system monitors
    - Performance trackers
    - Resource monitors

Consumers:
    - Introspection daemon: Processes observations into capability gaps
    - Metrics aggregator: Tracks system metrics

Ecosystem: "observation"
Intensity: Variable
Channel: trophic (high-frequency, batchable)
"""

METRICS_SUMMARY = MetricsSignal.SUMMARY.value
"""
Periodic metrics summary from daemon.

Facts Structure:
    {
        "daemon_name": str,                 # Name of daemon emitting metrics
        "uptime_seconds": float,            # How long daemon has been running
        "signals_processed": int,           # Number of signals processed
        "errors_count": int,                # Number of errors encountered
        "last_processing_time_ms": float,   # Time of last processing operation
        "custom_metrics": Dict[str, Any],   # Daemon-specific metrics
    }

Emitters:
    - All consumer daemons: Every 5 minutes

Consumers:
    - Metrics aggregator: Tracks daemon health
    - Alert system: Surfaces daemon failures

Ecosystem: "orchestration"
Intensity: 0.5 (informational)
Channel: trophic (periodic telemetry, batchable)
"""

SYSTEM_HEALTH = MetricsSignal.SYSTEM_HEALTH.value
"""
System health monitoring signal.

Facts Structure:
    {
        "component": str,                   # Component name
        "health_status": str,               # "healthy" | "degraded" | "critical"
        "metrics": Dict[str, Any],          # Health metrics
        "issues": List[str],                # List of detected issues
    }

Emitters:
    - CuriosityCoreConsumerDaemon: Periodic health checks
    - Various monitoring systems

Consumers:
    - Alert system: Surfaces critical health issues
    - Introspection daemon: Triggers deeper investigation

Ecosystem: "orchestration"
Intensity: Variable (based on health status)
Channel: affect (healthy/degraded) or reflex (critical)
"""


__all__ = [
    "ReflectionSignal",
    "HousekeepingSignal",
    "DreamSignal",
    "InvestigationSignal",
    "VoiceSignal",
    "ObservationSignal",
    "MetricsSignal",
    "Q_REFLECT_TRIGGER",
    "Q_REFLECTION_COMPLETE",
    "Q_HOUSEKEEPING_TRIGGER",
    "Q_HOUSEKEEPING_COMPLETE",
    "USER_VOICE_INTERACTION",
    "Q_DREAM_TRIGGER",
    "Q_DREAM_COMPLETE",
    "CAPABILITY_GAP",
    "Q_CURIOSITY_INVESTIGATE",
    "Q_INVESTIGATION_COMPLETE",
    "Q_AFFECTIVE_DEMAND",
    "OBSERVATION",
    "METRICS_SUMMARY",
    "SYSTEM_HEALTH",
]
