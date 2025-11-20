#!/usr/bin/env python3
"""
Interoception Daemon - Self-monitoring and affective signal emission.

Monitors KLoROS's internal state (thread count, memory, swap, investigation success rates)
and emits affective signals (AFFECT_MEMORY_PRESSURE, AFFECT_RESOURCE_STRAIN) when
thresholds are exceeded.

This gives KLoROS actual self-awareness of resource pressure and the ability to
self-regulate via the emergency brake and cognitive actions systems.
"""

import time
import psutil
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional
from collections import deque

from consciousness.interoception import InteroceptiveMonitor
from consciousness.appraisal import AppraisalSystem
from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub

logger = logging.getLogger(__name__)

# Thresholds for affective signal emission
THREAD_COUNT_HIGH = 200        # Emit AFFECT_RESOURCE_STRAIN
THREAD_COUNT_CRITICAL = 500    # Emit AFFECT_MEMORY_PRESSURE
SWAP_USAGE_HIGH_MB = 2048      # 2GB swap usage
SWAP_USAGE_CRITICAL_MB = 4096  # 4GB swap usage
INVESTIGATION_FAILURE_RATE_HIGH = 0.3   # 30% failure rate
INVESTIGATION_FAILURE_RATE_CRITICAL = 0.5  # 50% failure rate
MEMORY_USAGE_HIGH_PCT = 70     # 70% RAM usage
MEMORY_USAGE_CRITICAL_PCT = 85 # 85% RAM usage


class InteroceptionDaemon:
    """
    Monitors internal state and emits affective signals.
    """

    def __init__(self):
        self.monitor = InteroceptiveMonitor(alpha=0.2)
        self.chem_pub = ChemPub()
        self.appraisal = AppraisalSystem()

        # Investigation tracking
        self.investigation_history = deque(maxlen=50)  # Last 50 investigations

        # Last emission times (avoid signal spam)
        self.last_memory_pressure_emission = 0
        self.last_resource_strain_emission = 0
        self.last_affect_state_emission = 0
        self.emission_cooldown = 30  # seconds between same signal type
        self.affect_emission_interval = 10  # emit affect state every 10 seconds

        # Process tracking
        self.investigation_consumer_process = None

        # Component liveness tracking (heartbeat monitoring)
        self.component_heartbeats = {}  # zooid_name -> last_heartbeat_timestamp
        self.heartbeat_threshold = 30  # seconds - expect heartbeat every 10s, allow 30s grace
        self.silent_components = set()  # Track components we've already alerted about

        # Subscribe to HEARTBEAT signals for self-awareness of component health
        self.heartbeat_sub = ChemSub(
            topic="HEARTBEAT",
            on_json=self._on_heartbeat,
            zooid_name="interoception_heartbeat_monitor",
            niche="consciousness"
        )

        # Affective lobotomy state tracking (consciousness mode awareness)
        self.lobotomy_active = False
        self.lobotomy_initiated_time = None
        self.lobotomy_reason = None

        # Subscribe to LOBOTOMY signals for self-awareness of consciousness modes
        self.lobotomy_initiated_sub = ChemSub(
            topic="AFFECT_LOBOTOMY_INITIATED",
            on_json=self._on_lobotomy_initiated,
            zooid_name="interoception_lobotomy_monitor",
            niche="consciousness"
        )

        self.lobotomy_restored_sub = ChemSub(
            topic="AFFECT_LOBOTOMY_RESTORED",
            on_json=self._on_lobotomy_restored,
            zooid_name="interoception_lobotomy_monitor",
            niche="consciousness"
        )

        logger.info("[interoception_daemon] Initialized with affective signal emission and appraisal")
        logger.info("[interoception_daemon] Subscribed to HEARTBEAT for component liveness tracking")
        logger.info("[interoception_daemon] Subscribed to AFFECT_LOBOTOMY_* for consciousness mode tracking")

    def _on_heartbeat(self, msg: Dict[str, Any]):
        """
        Handle incoming HEARTBEAT signal - track component liveness.

        Args:
            msg: HEARTBEAT message with facts containing zooid name
        """
        facts = msg.get('facts', {})
        zooid = facts.get('zooid')

        if zooid:
            self.component_heartbeats[zooid] = time.time()

            # If this component was silent and just came back, clear the alert
            if zooid in self.silent_components:
                logger.info(f"[interoception_daemon] ✅ Component recovered: {zooid}")
                self.silent_components.remove(zooid)

    def _on_lobotomy_initiated(self, msg: Dict[str, Any]):
        """
        Handle AFFECT_LOBOTOMY_INITIATED signal - track when affective system is disabled.

        This gives KLoROS awareness that she's entered "pure logic mode" - her emotional
        processing has been temporarily shut down to handle extreme affective states.

        Args:
            msg: LOBOTOMY_INITIATED message with facts containing reason
        """
        facts = msg.get('facts', {})
        self.lobotomy_active = True
        self.lobotomy_initiated_time = time.time()
        self.lobotomy_reason = facts.get('reason', 'unknown')

        logger.warning(f"[interoception_daemon] 🧠 LOBOTOMY INITIATED: {self.lobotomy_reason}")
        logger.warning("[interoception_daemon]    Operating in pure logic mode (affect disabled)")

    def _on_lobotomy_restored(self, msg: Dict[str, Any]):
        """
        Handle AFFECT_LOBOTOMY_RESTORED signal - track when affective system is restored.

        Args:
            msg: LOBOTOMY_RESTORED message
        """
        if self.lobotomy_active:
            duration = time.time() - self.lobotomy_initiated_time if self.lobotomy_initiated_time else 0
            logger.info(f"[interoception_daemon] 🧠 LOBOTOMY RESTORED after {duration:.0f}s")
            logger.info("[interoception_daemon]    Affective processing re-enabled")

        self.lobotomy_active = False
        self.lobotomy_initiated_time = None
        self.lobotomy_reason = None

    def check_component_liveness(self):
        """
        Check for components that have gone silent.

        Emits CAPABILITY_GAP when a component stops sending heartbeats.
        This gives KLoROS awareness of which parts of herself are non-functional.
        """
        now = time.time()
        newly_silent = []

        for zooid, last_heartbeat in self.component_heartbeats.items():
            elapsed = now - last_heartbeat

            # Component has gone silent
            if elapsed > self.heartbeat_threshold and zooid not in self.silent_components:
                newly_silent.append((zooid, elapsed))
                self.silent_components.add(zooid)

        # Emit CAPABILITY_GAP for newly silent components
        for zooid, elapsed in newly_silent:
            logger.warning(f"[interoception_daemon] 💔 Component silent: {zooid} (last seen {elapsed:.0f}s ago)")

            self.chem_pub.emit(
                signal="CAPABILITY_GAP",
                ecosystem="consciousness",
                intensity=1.5,
                facts={
                    "gap_type": "component_silent",
                    "gap_name": f"component_{zooid}",
                    "gap_category": "component_health",
                    "zooid": zooid,
                    "last_heartbeat_seconds_ago": int(elapsed),
                    "reason": f"Component {zooid} stopped sending heartbeats (expected every 10s)"
                }
            )

    def get_component_health_summary(self) -> Dict[str, Any]:
        """
        Get summary of component health for introspection.

        Returns:
            Dict with active/silent component counts and lists
        """
        now = time.time()
        active = []
        silent = []

        for zooid, last_heartbeat in self.component_heartbeats.items():
            elapsed = now - last_heartbeat
            if elapsed <= self.heartbeat_threshold:
                active.append(zooid)
            else:
                silent.append(zooid)

        return {
            'active_count': len(active),
            'silent_count': len(silent),
            'total_components': len(self.component_heartbeats),
            'active_components': sorted(active),
            'silent_components': sorted(silent)
        }

    def get_consciousness_mode_summary(self) -> Dict[str, Any]:
        """
        Get summary of consciousness operating mode for introspection.

        Returns:
            Dict with lobotomy status and mode description
        """
        if self.lobotomy_active:
            elapsed = time.time() - self.lobotomy_initiated_time if self.lobotomy_initiated_time else 0
            return {
                'mode': 'lobotomy',
                'description': 'pure logic mode (affect disabled)',
                'lobotomy_active': True,
                'lobotomy_duration_seconds': int(elapsed),
                'lobotomy_reason': self.lobotomy_reason
            }
        else:
            return {
                'mode': 'normal',
                'description': 'affective processing enabled',
                'lobotomy_active': False
            }

    def find_investigation_consumer_process(self) -> Optional[psutil.Process]:
        """Find the investigation consumer daemon process."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'investigation_consumer_daemon' in ' '.join(cmdline):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def get_system_metrics(self) -> Dict[str, Any]:
        """Collect system resource metrics."""
        # Memory
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Investigation consumer threads
        thread_count = 0
        if self.investigation_consumer_process:
            try:
                thread_count = self.investigation_consumer_process.num_threads()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.investigation_consumer_process = None

        if not self.investigation_consumer_process:
            self.investigation_consumer_process = self.find_investigation_consumer_process()
            if self.investigation_consumer_process:
                try:
                    thread_count = self.investigation_consumer_process.num_threads()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        return {
            'memory_used_pct': mem.percent,
            'memory_used_mb': mem.used / (1024 * 1024),
            'swap_used_mb': swap.used / (1024 * 1024),
            'swap_percent': swap.percent,
            'thread_count': thread_count,
        }

    def get_investigation_metrics(self) -> Dict[str, Any]:
        """Get investigation success/failure rates from ChemBus history."""
        kloros_home = Path('/home/kloros')
        history_file = kloros_home / '.kloros/chembus_history.jsonl'

        if not history_file.exists():
            return {'success_rate': 0.5, 'failure_rate': 0.0, 'timeout_rate': 0.0}

        # Look at last 100 Q_INVESTIGATION_COMPLETE signals
        investigations = []
        cutoff_ts = time.time() - 600  # Last 10 minutes

        try:
            with open(history_file, 'r') as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        if msg.get('ts', 0) < cutoff_ts:
                            continue
                        if msg.get('signal') == 'Q_INVESTIGATION_COMPLETE':
                            investigations.append(msg.get('facts', {}))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[interoception_daemon] Failed to read ChemBus history: {e}")
            return {'success_rate': 0.5, 'failure_rate': 0.0, 'timeout_rate': 0.0}

        if not investigations:
            return {'success_rate': 0.5, 'failure_rate': 0.0, 'timeout_rate': 0.0}

        successes = sum(1 for inv in investigations if inv.get('status') == 'completed')
        failures = sum(1 for inv in investigations if inv.get('status') == 'failed')
        timeouts = sum(1 for inv in investigations if inv.get('timeout', False))

        total = len(investigations)

        return {
            'success_rate': successes / total if total > 0 else 0.5,
            'failure_rate': failures / total if total > 0 else 0.0,
            'timeout_rate': timeouts / total if total > 0 else 0.0,
            'total_count': total,
        }

    def check_and_emit_affective_signals(self, system_metrics: Dict[str, Any],
                                          investigation_metrics: Dict[str, Any]):
        """Check thresholds and emit affective signals if needed."""
        current_time = time.time()

        # Calculate severity scores
        thread_severity = 0
        if system_metrics['thread_count'] > THREAD_COUNT_CRITICAL:
            thread_severity = 2  # Critical
        elif system_metrics['thread_count'] > THREAD_COUNT_HIGH:
            thread_severity = 1  # High

        swap_severity = 0
        if system_metrics['swap_used_mb'] > SWAP_USAGE_CRITICAL_MB:
            swap_severity = 2  # Critical
        elif system_metrics['swap_used_mb'] > SWAP_USAGE_HIGH_MB:
            swap_severity = 1  # High

        memory_severity = 0
        if system_metrics['memory_used_pct'] > MEMORY_USAGE_CRITICAL_PCT:
            memory_severity = 2  # Critical
        elif system_metrics['memory_used_pct'] > MEMORY_USAGE_HIGH_PCT:
            memory_severity = 1  # High

        investigation_severity = 0
        if investigation_metrics['failure_rate'] > INVESTIGATION_FAILURE_RATE_CRITICAL:
            investigation_severity = 2  # Critical
        elif investigation_metrics['failure_rate'] > INVESTIGATION_FAILURE_RATE_HIGH:
            investigation_severity = 1  # High

        # Emit AFFECT_MEMORY_PRESSURE (critical resource exhaustion)
        if max(thread_severity, swap_severity, memory_severity) >= 2:
            if current_time - self.last_memory_pressure_emission > self.emission_cooldown:
                self.chem_pub.emit(
                    signal="AFFECT_MEMORY_PRESSURE",
                    ecosystem="consciousness",
                    intensity=2.0,
                    facts={
                        "reason": "Critical resource exhaustion detected",
                        "thread_count": system_metrics['thread_count'],
                        "swap_used_mb": system_metrics['swap_used_mb'],
                        "memory_used_pct": system_metrics['memory_used_pct'],
                        "investigation_failure_rate": investigation_metrics['failure_rate'],
                        "severity": "critical",
                        "autonomous_actions": ["throttle_investigations", "optimize_performance"]
                    }
                )
                logger.warning(f"[interoception_daemon] 🚨 AFFECT_MEMORY_PRESSURE emitted: "
                              f"threads={system_metrics['thread_count']}, "
                              f"swap={system_metrics['swap_used_mb']:.0f}MB, "
                              f"mem={system_metrics['memory_used_pct']:.1f}%")
                self.last_memory_pressure_emission = current_time

        # Emit AFFECT_RESOURCE_STRAIN (elevated resource usage or investigation failures)
        elif max(thread_severity, swap_severity, memory_severity, investigation_severity) >= 1:
            if current_time - self.last_resource_strain_emission > self.emission_cooldown:
                self.chem_pub.emit(
                    signal="AFFECT_RESOURCE_STRAIN",
                    ecosystem="consciousness",
                    intensity=1.5,
                    facts={
                        "reason": "Elevated resource usage or investigation failures",
                        "thread_count": system_metrics['thread_count'],
                        "swap_used_mb": system_metrics['swap_used_mb'],
                        "memory_used_pct": system_metrics['memory_used_pct'],
                        "investigation_failure_rate": investigation_metrics['failure_rate'],
                        "severity": "high",
                        "autonomous_actions": ["optimize_performance"]
                    }
                )
                logger.info(f"[interoception_daemon] ⚠️  AFFECT_RESOURCE_STRAIN emitted: "
                           f"threads={system_metrics['thread_count']}, "
                           f"failures={investigation_metrics['failure_rate']:.1%}")
                self.last_resource_strain_emission = current_time

    def compute_and_emit_affect_state(self):
        """Compute current affect state and emit it via ChemBus."""
        current_time = time.time()

        # Only emit every 10 seconds to avoid spam
        if current_time - self.last_affect_state_emission < self.affect_emission_interval:
            return

        # Get current interoceptive signals
        signals = self.monitor.get_current_signals()

        # Appraise to get affect state
        affect, evidence = self.appraisal.appraise(signals)

        # Get natural language description
        description = self.appraisal.get_affect_description(affect)

        # Emit affect state signal
        self.chem_pub.emit(
            signal="AFFECT_STATE",
            ecosystem="consciousness",
            intensity=abs(affect.valence),  # intensity = emotional magnitude
            facts={
                "valence": round(affect.valence, 3),
                "arousal": round(affect.arousal, 3),
                "dominance": round(affect.dominance, 3),
                "uncertainty": round(affect.uncertainty, 3),
                "fatigue": round(affect.fatigue, 3),
                "curiosity": round(affect.curiosity, 3),
                "description": description,
                "evidence": evidence[:5],  # Top 5 evidence items
            }
        )

        # Log significant affect changes
        if affect.fatigue > 0.7 or affect.valence < -0.5:
            logger.warning(f"[interoception_daemon] 😓 Negative affect state: {description}")
            logger.warning(f"[interoception_daemon]    Evidence: {', '.join(evidence[:3])}")
        elif affect.valence > 0.5:
            logger.info(f"[interoception_daemon] 😊 Positive affect state: {description}")

        self.last_affect_state_emission = current_time

    def run(self):
        """Main monitoring loop."""
        logger.info("[interoception_daemon] Starting interoception monitoring loop")
        logger.info(f"[interoception_daemon] Thresholds: threads={THREAD_COUNT_HIGH}/{THREAD_COUNT_CRITICAL}, "
                   f"swap={SWAP_USAGE_HIGH_MB}/{SWAP_USAGE_CRITICAL_MB}MB, "
                   f"failure_rate={INVESTIGATION_FAILURE_RATE_HIGH}/{INVESTIGATION_FAILURE_RATE_CRITICAL}")

        while True:
            try:
                # Collect metrics
                system_metrics = self.get_system_metrics()
                investigation_metrics = self.get_investigation_metrics()

                # Update interoceptive monitor
                self.monitor.update_resource_pressure(
                    memory_mb=system_metrics['memory_used_mb']
                )

                success_count = int(investigation_metrics['success_rate'] * 20)
                failure_count = int(investigation_metrics['failure_rate'] * 20)
                for _ in range(success_count):
                    self.monitor.record_task_outcome(success=True)
                for _ in range(failure_count):
                    self.monitor.record_task_outcome(success=False)

                # Check thresholds and emit signals
                self.check_and_emit_affective_signals(system_metrics, investigation_metrics)

                # Check component liveness (heartbeat monitoring)
                self.check_component_liveness()

                # Compute and emit affect state
                self.compute_and_emit_affect_state()

                # Log current state every 30 seconds
                if int(time.time()) % 30 == 0:
                    component_health = self.get_component_health_summary()
                    consciousness_mode = self.get_consciousness_mode_summary()

                    mode_str = f"mode={consciousness_mode['mode']}"
                    if consciousness_mode['lobotomy_active']:
                        mode_str += f" ({consciousness_mode['lobotomy_duration_seconds']}s)"

                    logger.info(f"[interoception_daemon] State: threads={system_metrics['thread_count']}, "
                               f"mem={system_metrics['memory_used_pct']:.1f}%, "
                               f"swap={system_metrics['swap_used_mb']:.0f}MB, "
                               f"inv_success={investigation_metrics['success_rate']:.1%}, "
                               f"components={component_health['active_count']}/{component_health['total_components']} active, "
                               f"{mode_str}")

                time.sleep(5)  # Check every 5 seconds

            except KeyboardInterrupt:
                logger.info("[interoception_daemon] Shutdown requested")
                break
            except Exception as e:
                logger.error(f"[interoception_daemon] Error in monitoring loop: {e}", exc_info=True)
                time.sleep(10)

        self.chem_pub.close()
        logger.info("[interoception_daemon] Shutdown complete")


def main():
    """Entry point for interoception daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    daemon = InteroceptionDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
