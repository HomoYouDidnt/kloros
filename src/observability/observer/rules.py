"""
Rule engine for Observer - processes events and generates intents.

Rules define:
- Pattern matching on event types
- Rate-limiting and deduplication
- Context-aware decision logic
- Intent generation criteria
"""

import re
import time
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from collections import defaultdict, deque
from pathlib import Path

from .sources import Event

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """Generated intent for orchestrator consumption."""
    intent_type: str  # "trigger_phase", "suggest", "alert"
    priority: int     # 0-10, higher = more urgent
    reason: str       # human-readable rationale
    data: Dict[str, Any]  # intent-specific payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "priority": self.priority,
            "reason": self.reason,
            "data": self.data,
            "generated_at": time.time()
        }


class RuleEngine:
    """Stateful rule engine that processes events and generates intents."""

    def __init__(self, rate_limit_window_s: int = 300):
        """
        Args:
            rate_limit_window_s: Time window for rate-limiting (default 5 minutes)
        """
        self.rate_limit_window_s = rate_limit_window_s

        # Event history for pattern detection
        self._event_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Deduplication tracking
        self._last_seen: Dict[str, float] = {}

        # Intent generation tracking
        self._last_intent: Dict[str, float] = {}

    def process(self, event: Event) -> Optional[Intent]:
        """
        Process a single event and optionally generate an intent.

        Args:
            event: Event to process

        Returns:
            Intent if rule triggered, None otherwise
        """
        # Update event history
        self._event_history[event.type].append(event)

        # Prune old events from history
        self._prune_history()

        # Check rate limiting on this event
        if self._is_rate_limited(event):
            return None

        # Apply rules in priority order
        rules = [
            self._rule_operational_error,  # FIRST: Operational errors are top priority
            self._rule_promotion_cluster,
            self._rule_phase_failure,
            self._rule_heartbeat_stall,
            self._rule_lock_contention,
            self._rule_gpu_oom,
            self._rule_vllm_oom_guard,  # Specific VLLM fix before generic dream_error
            self._rule_phase_timeout,
            self._rule_dream_error,
            self._rule_systemd_disabled,  # Audit disabled services for optimization
        ]

        for rule in rules:
            intent = rule(event)
            if intent:
                # Track intent generation
                self._last_intent[intent.intent_type] = time.time()
                logger.info(f"Rule triggered: {intent.intent_type} - {intent.reason}")
                return intent

        return None

    def _prune_history(self):
        """Remove events older than rate limit window."""
        cutoff = time.time() - self.rate_limit_window_s

        for event_type, history in self._event_history.items():
            # Remove old events from front of deque
            while history and history[0].ts < cutoff:
                history.popleft()

    def _is_rate_limited(self, event: Event) -> bool:
        """
        Check if this event should be rate-limited.

        CRITICAL: Operational and kernel errors bypass rate limiting to ensure
        cascading failures are all detected and investigated.
        """
        # NEVER rate-limit operational/kernel errors - these are critical
        if event.type in ["error_operational", "error_critical",
                          "error_kernel_operational", "error_kernel_critical"]:
            return False

        key = event.hash_key()
        last_ts = self._last_seen.get(key, 0)
        now = time.time()

        # Rate limit: same event type+key must wait at least 60s
        if now - last_ts < 60:
            return True

        self._last_seen[key] = now
        return False

    def _rule_operational_error(self, event: Event) -> Optional[Intent]:
        """
        Operational error rule: System errors → immediate curiosity investigation.

        Rationale: All operational errors (exceptions, failures, crashes) indicate
        system malfunction and require immediate investigation for root cause analysis
        and self-healing. These are TOP PRIORITY over exploratory questions.

        Priority levels:
        - error_critical / error_kernel_critical: priority 10 (absolute top, bypasses rate limiting)
        - error_operational / error_kernel_operational: priority 9 (top tier)
        """
        if event.type not in ["error_operational", "error_critical", "error_kernel_operational", "error_kernel_critical"]:
            return None

        message = event.data.get("message", "")
        unit = event.data.get("unit", "unknown")

        # Determine if this is a kernel error
        is_kernel = event.type.startswith("error_kernel")
        error_context = "kernel" if is_kernel else "service"

        # Critical errors bypass rate limiting
        if event.type in ["error_critical", "error_kernel_critical"]:
            # Force processing by clearing rate limit for this key
            key = event.hash_key()
            self._last_seen[key] = 0

            return Intent(
                intent_type="curiosity_investigate",
                priority=10,
                reason=f"CRITICAL {error_context.upper()} ERROR detected in {unit}",
                data={
                    "question": f"What caused this critical {error_context} error and how can it be prevented? What remediation steps should be taken?",
                    "question_id": f"critical_{error_context}_error_{int(time.time())}",
                    "evidence": [
                        f"Error message: {message}",
                        f"Source: {unit}",
                        f"Context: {error_context}",
                        f"Severity: CRITICAL",
                        f"Timestamp: {event.ts}"
                    ],
                    "hypothesis": f"Critical {error_context} error requires immediate investigation and automated remediation",
                    "capability_key": f"self_healing.critical_{error_context}_error",
                    "priority": "critical"
                }
            )

        # Operational errors (high priority but respect rate limiting)
        return Intent(
            intent_type="curiosity_investigate",
            priority=9,
            reason=f"Operational {error_context} error detected in {unit}",
            data={
                "question": f"What caused this {error_context} error and how can it be prevented? What remediation steps should be taken?",
                "question_id": f"{error_context}_error_{int(time.time())}",
                "evidence": [
                    f"Error message: {message}",
                    f"Source: {unit}",
                    f"Context: {error_context}",
                    f"Severity: Operational",
                    f"Timestamp: {event.ts}"
                ],
                "hypothesis": f"{error_context.capitalize()} error requires investigation and potential automated remediation",
                "capability_key": f"self_healing.{error_context}_error_analysis",
                "priority": "high"
            }
        )

    def _rule_promotion_cluster(self, event: Event) -> Optional[Intent]:
        """
        Promotion cluster rule: ≥3 promotions in 10 minutes → trigger_phase.

        Rationale: Multiple promotions indicate convergence on good candidates.
        Running PHASE can validate them under stress.
        """
        if event.type != "promotion_new":
            return None

        # Count promotion_new events in last 10 minutes
        cutoff = time.time() - 600  # 10 minutes
        recent_promotions = [
            e for e in self._event_history["promotion_new"]
            if e.ts >= cutoff
        ]

        if len(recent_promotions) >= 3:
            # Check if we've already sent this intent recently
            last_trigger = self._last_intent.get("trigger_phase_promotion_cluster", 0)
            if time.time() - last_trigger < 3600:  # 1 hour cooldown
                return None

            return Intent(
                intent_type="trigger_phase_promotion_cluster",
                priority=7,
                reason=f"Promotion cluster detected: {len(recent_promotions)} promotions in 10 minutes",
                data={
                    "promotion_count": len(recent_promotions),
                    "promotion_files": [e.data.get("path", "") for e in recent_promotions]
                }
            )

        return None

    def _rule_phase_failure(self, event: Event) -> Optional[Intent]:
        """
        PHASE failure diagnostics: failed test → suggest investigation.

        Rationale: Test failures may indicate regressions or environment issues.
        Suggest diagnostic actions to orchestrator.
        """
        if event.type not in ["phase_error", "phase_timeout"]:
            return None

        message = event.data.get("message", "")

        return Intent(
            intent_type="suggest_phase_diagnostic",
            priority=6,
            reason=f"PHASE failure detected: {event.type}",
            data={
                "event_type": event.type,
                "message": message,
                "unit": event.data.get("unit", ""),
                "suggestions": [
                    "Check /home/kloros/logs/spica-phase-test.log for details",
                    "Review recent test changes in git log",
                    "Verify PHASE heuristics state in /home/kloros/out/heuristics/"
                ]
            }
        )

    def _rule_heartbeat_stall(self, event: Event) -> Optional[Intent]:
        """
        Heartbeat stall detection: ready file mtime > 10s → suggest.

        Rationale: D-REAM runner writes ready file every cycle. If stale,
        the service may be hung or crashed.
        """
        if event.type != "dream_heartbeat":
            return None

        # Check if we've seen multiple stale heartbeats
        recent_heartbeats = [
            e for e in self._event_history["dream_heartbeat"]
            if e.ts >= time.time() - 300  # last 5 minutes
        ]

        # If no heartbeats in 5 minutes, that's suspicious
        if len(recent_heartbeats) == 0:
            return Intent(
                intent_type="alert_heartbeat_stall",
                priority=8,
                reason="D-REAM heartbeat stalled: no ready file updates in 5 minutes",
                data={
                    "last_heartbeat": event.ts,
                    "suggestions": [
                        "Check D-REAM service: systemctl status dream.service",
                        "Review D-REAM logs: journalctl -u dream.service -n 100",
                        "Verify D-REAM runner process: ps aux | grep dream.runner"
                    ]
                }
            )

        return None

    def _rule_lock_contention(self, event: Event) -> Optional[Intent]:
        """
        Lock contention spike: >10 contentions → suggest.

        Rationale: High lock contention indicates concurrent access conflicts
        or deadlock risk. May need to adjust orchestrator tick rate or D-REAM parallelism.
        """
        if event.type not in ["lock_contention", "lock_contention_high"]:
            return None

        value = event.data.get("value", 0)

        if value > 10:
            return Intent(
                intent_type="suggest_lock_optimization",
                priority=5,
                reason=f"Lock contention spike detected: {value} contentions",
                data={
                    "contention_count": value,
                    "metric": event.data.get("metric", ""),
                    "suggestions": [
                        "Review orchestrator tick frequency (currently 60s)",
                        "Check D-REAM parallelism: docker exec kloros-vllm ps aux | grep python",
                        "Analyze lock acquisition patterns in recent logs"
                    ]
                }
            )

        return None

    def _rule_gpu_oom(self, event: Event) -> Optional[Intent]:
        """
        GPU OOM: out of memory error → suggest resource adjustment.

        Rationale: OOM indicates memory pressure. May need to reduce batch size,
        model parallelism, or number of concurrent workers.
        """
        if event.type != "gpu_oom":
            return None

        message = event.data.get("message", "")

        return Intent(
            intent_type="alert_gpu_oom",
            priority=9,
            reason="GPU out of memory error detected",
            data={
                "message": message,
                "unit": event.data.get("unit", ""),
                "suggestions": [
                    "Check GPU memory usage: nvidia-smi",
                    "Review D-REAM max_parallel setting (currently 2)",
                    "Consider reducing vLLM tensor_parallel_size or max_num_seqs",
                    "Check for memory leaks in recent experiments"
                ]
            }
        )

    def _rule_vllm_oom_guard(self, event: Event) -> Optional[Intent]:
        """
        VLLM OOM Guard: VLLM allocation error with deficit → trigger config tuning.

        Rationale: VLLM allocation errors with measurable deficit can be fixed
        by adjusting gpu_memory_utilization. Extract deficit, compute minimal fix,
        and trigger D-REAM config_tuning canary to test it.

        Actuator bounds: vllm.gpu_memory_utilization ∈ [0.60, 0.90], step 0.05
        """
        if event.type != "dream_error":
            return None

        message = event.data.get("message", "")

        # Pattern: "VLLM allocation (4915MB) too small for model+cache (need 6070MB, deficit: 1155MB)"
        vllm_pattern = r"VLLM allocation \((?P<alloc_mb>\d+)MB\) too small.*need (?P<need_mb>\d+)MB.*deficit: (?P<deficit_mb>\d+)MB"
        match = re.search(vllm_pattern, message)

        if not match:
            return None

        # Extract values
        alloc_mb = int(match.group("alloc_mb"))
        need_mb = int(match.group("need_mb"))
        deficit_mb = int(match.group("deficit_mb"))

        # Check cooldown: don't spam VLLM config tuning
        last_trigger = self._last_intent.get("trigger_dream_vllm_oom", 0)
        if time.time() - last_trigger < 3600:  # 1 hour cooldown
            logger.info(f"VLLM OOM guard on cooldown (last trigger {time.time() - last_trigger:.0f}s ago)")
            return None

        # Compute seed fix: current allocation + deficit + 10% buffer
        # Assume total GPU memory is ~12GB (12288 MB) for calculation
        # Current utilization ≈ alloc_mb / total_mb
        # We need to find new utilization that gives us: alloc_mb + deficit_mb + 10% buffer

        # Conservative estimate of total GPU memory (from SPICA GPU domain context)
        total_mb_estimate = 12288  # RTX 3060 12GB

        # Current utilization (approximate)
        current_util = alloc_mb / total_mb_estimate

        # Required allocation with 10% buffer
        required_alloc_mb = need_mb * 1.10  # +10% safety buffer

        # Target utilization
        target_util = required_alloc_mb / total_mb_estimate

        # Round up to nearest 0.05 step and clamp to bounds [0.60, 0.90]
        target_util_stepped = min(0.90, max(0.60, round(target_util / 0.05) * 0.05))

        # If already at max bound, we can't fix this autonomously
        if target_util_stepped >= 0.90:
            logger.warning(f"VLLM OOM requires util={target_util:.2f}, but max bound is 0.90 - escalating to manual review")
            return Intent(
                intent_type="alert_vllm_oom_unbounded",
                priority=9,
                reason=f"VLLM OOM requires gpu_memory_utilization > max bound (need {target_util:.2f}, max 0.90)",
                data={
                    "message": message,
                    "deficit_mb": deficit_mb,
                    "alloc_mb": alloc_mb,
                    "need_mb": need_mb,
                    "computed_util": target_util,
                    "max_bound": 0.90,
                    "suggestions": [
                        "Model size exceeds single-GPU capacity at current bounds",
                        "Consider multi-GPU tensor parallelism",
                        "Or manually increase vllm.gpu_memory_utilization bound to 0.95",
                        "Or reduce vllm.max_model_len to fit within 0.90 utilization"
                    ]
                }
            )

        logger.info(f"VLLM OOM guard: deficit={deficit_mb}MB, computed target_util={target_util:.2f} → stepped={target_util_stepped:.2f}")

        return Intent(
            intent_type="trigger_dream",
            priority=7,
            reason=f"VLLM OOM guard: deficit {deficit_mb}MB → propose gpu_memory_utilization={target_util_stepped:.2f}",
            data={
                "mode": "config_tuning",
                "subsystem": "vllm",
                "seed_fix": {
                    "vllm.gpu_memory_utilization": target_util_stepped
                },
                "context": {
                    "deficit_mb": deficit_mb,
                    "alloc_mb": alloc_mb,
                    "need_mb": need_mb,
                    "current_util_est": round(current_util, 2),
                    "target_util": round(target_util, 2),
                    "model": event.data.get("unit", ""),
                    "error_message": message
                }
            }
        )

    def _rule_phase_timeout(self, event: Event) -> Optional[Intent]:
        """
        PHASE duration spike: >2 hours → suggest investigation.

        Rationale: PHASE runs should complete in under 2 hours. Extended duration
        indicates slow tests, infinite loops, or resource starvation.
        """
        if event.type != "phase_duration_high":
            return None

        duration = event.data.get("value", 0)

        return Intent(
            intent_type="suggest_phase_optimization",
            priority=6,
            reason=f"PHASE duration excessive: {duration:.0f}s ({duration/3600:.1f}h)",
            data={
                "duration_seconds": duration,
                "suggestions": [
                    "Review test selection in PHASE heuristics",
                    "Check for hanging tests: ps aux | grep pytest",
                    "Analyze test durations in PHASE report JSON",
                    "Consider adjusting pytest-xdist worker count"
                ]
            }
        )

    def _rule_dream_error(self, event: Event) -> Optional[Intent]:
        """
        D-REAM error: experiment failure → suggest diagnostic.

        Rationale: Experiment errors may indicate bugs in generated code,
        invalid configurations, or environment issues.
        """
        if event.type != "dream_error":
            return None

        message = event.data.get("message", "")

        return Intent(
            intent_type="suggest_dream_diagnostic",
            priority=5,
            reason=f"D-REAM error detected",
            data={
                "message": message,
                "unit": event.data.get("unit", ""),
                "suggestions": [
                    "Check D-REAM logs: journalctl -u dream.service -n 100",
                    "Review recent experiment configs in /home/kloros/src/dream/experiments/",
                    "Verify D-REAM promotions queue in /home/kloros/out/promotions/",
                    "Check for syntax errors in generated experiment files"
                ]
            }
        )

    def _rule_systemd_disabled(self, event: Event) -> Optional[Intent]:
        """
        Systemd disabled service/timer audit: disabled unit → investigate if needed.

        Rationale: Disabled services may be important for system function but were
        never enabled. KLoROS should investigate each disabled service to determine:
        1. What the service does
        2. If it's relevant to her immediate function
        3. If it should be enabled for optimal operation

        Priority: 5 (operational optimization, not urgent)
        """
        if event.type != "systemd_disabled":
            return None

        unit = event.data.get("unit", "unknown")
        unit_type = event.data.get("unit_type", "service")

        return Intent(
            intent_type="curiosity_investigate",
            priority=5,
            reason=f"Disabled {unit_type} audit: {unit}",
            data={
                "question": f"What does {unit} do? Is it important to my immediate function? Should I have it enabled?",
                "question_id": f"systemd_audit_{unit.replace('.', '_').replace('@', '_')}_{int(time.time())}",
                "evidence": [
                    f"Unit: {unit}",
                    f"Type: {unit_type}",
                    f"State: disabled",
                    f"Audit timestamp: {event.ts}"
                ],
                "hypothesis": f"This disabled {unit_type} may be relevant to system operation and should be evaluated for enablement",
                "capability_key": "system_audit.configuration_optimization",
                "priority": "normal"
            }
        )
