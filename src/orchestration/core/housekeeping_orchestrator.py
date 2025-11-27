"""
Housekeeping orchestrator for KLoROS memory system.

Thin orchestrator that coordinates housekeeping services via UMN signals.
Follows the MetaAgentKLoROS pattern for signal-based orchestration.

Signal Flow:
    Q_HOUSEKEEPING_TRIGGER
            ↓
    HousekeepingOrchestrator
            │
            ├─→ Q_HOUSEKEEPING.FILE_CLEANUP
            ├─→ Q_HOUSEKEEPING.REFLECTION
            ├─→ Q_HOUSEKEEPING.DATABASE
            ├─→ Q_HOUSEKEEPING.CONDENSE
            ├─→ Q_HOUSEKEEPING.VECTOR_EXPORT
            ├─→ Q_HOUSEKEEPING.RAG_REBUILD
            └─→ Q_HOUSEKEEPING.TTS_ANALYSIS
            ↓
    Q_HOUSEKEEPING_COMPLETE (aggregated results)
"""

import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)


@dataclass
class HousekeepingRequest:
    """Tracks a housekeeping maintenance cycle."""
    request_id: str
    start_time: float
    services_dispatched: Set[str] = field(default_factory=set)
    services_completed: Set[str] = field(default_factory=set)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class HousekeepingOrchestrator:
    """
    Thin orchestrator for housekeeping operations.

    Coordinates multiple housekeeping services via UMN signals,
    tracks completions, and aggregates results.
    """

    SERVICES = [
        ("FILE_CLEANUP", "Q_HOUSEKEEPING.FILE_CLEANUP", "Q_HOUSEKEEPING.FILE_CLEANUP.COMPLETE"),
        ("REFLECTION", "Q_HOUSEKEEPING.REFLECTION", "Q_HOUSEKEEPING.REFLECTION.COMPLETE"),
        ("DATABASE", "Q_HOUSEKEEPING.DATABASE", "Q_HOUSEKEEPING.DATABASE.COMPLETE"),
        ("CONDENSE", "Q_HOUSEKEEPING.CONDENSE", "Q_HOUSEKEEPING.CONDENSE.COMPLETE"),
        ("VECTOR_EXPORT", "Q_HOUSEKEEPING.VECTOR_EXPORT", "Q_HOUSEKEEPING.VECTOR_EXPORT.COMPLETE"),
        ("RAG_REBUILD", "Q_HOUSEKEEPING.RAG_REBUILD", "Q_HOUSEKEEPING.RAG_REBUILD.COMPLETE"),
        ("TTS_ANALYSIS", "Q_HOUSEKEEPING.TTS_ANALYSIS", "Q_HOUSEKEEPING.TTS_ANALYSIS.COMPLETE"),
    ]

    def __init__(self):
        """Initialize the housekeeping orchestrator."""
        self._umn_pub: Optional[UMNPub] = None
        self._trigger_sub: Optional[UMNSub] = None
        self._completion_subs: List[UMNSub] = []

        self._pending_requests: Dict[str, HousekeepingRequest] = {}
        self._request_timeout = 300

    def start(self) -> None:
        """Start the orchestrator and subscribe to UMN signals."""
        self._umn_pub = UMNPub()

        self._trigger_sub = UMNSub(
            topic="Q_HOUSEKEEPING_TRIGGER",
            on_json=self._handle_trigger,
            zooid_name="housekeeping_orchestrator",
            niche="orchestration"
        )

        for service_name, _, complete_topic in self.SERVICES:
            sub = UMNSub(
                topic=complete_topic,
                on_json=lambda msg, svc=service_name: self._handle_service_complete(svc, msg),
                zooid_name="housekeeping_orchestrator",
                niche="orchestration"
            )
            self._completion_subs.append(sub)

        logger.info("[housekeeping_orchestrator] Started and subscribed to UMN signals")
        logger.info(f"[housekeeping_orchestrator] Coordinating {len(self.SERVICES)} services")

    def _handle_trigger(self, msg: dict) -> None:
        """Handle housekeeping trigger signal."""
        request_id = msg.get('request_id') or str(uuid.uuid4())
        services_to_run = msg.get('facts', {}).get('services', 'all')
        operation_mode = msg.get('facts', {}).get('mode', 'full')

        logger.info(f"[housekeeping_orchestrator] Received trigger request_id={request_id}")

        request = HousekeepingRequest(
            request_id=request_id,
            start_time=time.time()
        )
        self._pending_requests[request_id] = request

        if services_to_run == 'all':
            services = self.SERVICES
        else:
            services = [s for s in self.SERVICES if s[0] in services_to_run]

        for service_name, dispatch_topic, _ in services:
            try:
                self._umn_pub.emit(
                    signal=dispatch_topic,
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'operation': operation_mode,
                        'triggered_by': 'housekeeping_orchestrator'
                    }
                )
                request.services_dispatched.add(service_name)
                logger.info(f"[housekeeping_orchestrator] Dispatched {service_name}")
            except Exception as e:
                logger.error(f"[housekeeping_orchestrator] Failed to dispatch {service_name}: {e}")
                request.errors.append(f"Dispatch failed for {service_name}: {str(e)}")

        if not request.services_dispatched:
            self._finalize_request(request_id)

    def _handle_service_complete(self, service_name: str, msg: dict) -> None:
        """Handle service completion signal."""
        request_id = msg.get('facts', {}).get('request_id', 'unknown')

        if request_id not in self._pending_requests:
            logger.warning(f"[housekeeping_orchestrator] Received completion for unknown request: {request_id}")
            return

        request = self._pending_requests[request_id]
        request.services_completed.add(service_name)

        success = msg.get('facts', {}).get('success', False)
        results = msg.get('facts', {}).get('results', {})
        error = msg.get('facts', {}).get('error')

        request.results[service_name] = {
            'success': success,
            'results': results,
            'error': error
        }

        if error:
            request.errors.append(f"{service_name}: {error}")

        logger.info(f"[housekeeping_orchestrator] {service_name} complete "
                   f"({len(request.services_completed)}/{len(request.services_dispatched)})")

        if request.services_completed >= request.services_dispatched:
            self._finalize_request(request_id)

    def _finalize_request(self, request_id: str) -> None:
        """Finalize a housekeeping request and emit completion signal."""
        if request_id not in self._pending_requests:
            return

        request = self._pending_requests.pop(request_id)
        duration = time.time() - request.start_time

        successful_services = sum(
            1 for r in request.results.values() if r.get('success', False)
        )
        total_services = len(request.services_dispatched)

        summary = {
            'request_id': request_id,
            'duration_seconds': duration,
            'services_dispatched': list(request.services_dispatched),
            'services_completed': list(request.services_completed),
            'successful_services': successful_services,
            'total_services': total_services,
            'success_rate': successful_services / total_services if total_services > 0 else 0,
            'results': request.results,
            'errors': request.errors
        }

        self._umn_pub.emit(
            signal="Q_HOUSEKEEPING_COMPLETE",
            ecosystem="orchestration",
            facts=summary
        )

        logger.info(f"[housekeeping_orchestrator] Housekeeping complete: "
                   f"{successful_services}/{total_services} services succeeded in {duration:.1f}s")

    def check_timeouts(self) -> None:
        """Check for timed-out requests (call periodically)."""
        current_time = time.time()
        timed_out = []

        for request_id, request in self._pending_requests.items():
            if current_time - request.start_time > self._request_timeout:
                pending = request.services_dispatched - request.services_completed
                request.errors.append(f"Timeout waiting for: {pending}")
                timed_out.append(request_id)

        for request_id in timed_out:
            logger.warning(f"[housekeeping_orchestrator] Request {request_id} timed out")
            self._finalize_request(request_id)

    def run_maintenance_sync(self, services: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run housekeeping synchronously (for backwards compatibility).

        Args:
            services: Optional list of service names to run, or None for all

        Returns:
            Dictionary with aggregated results
        """
        request_id = str(uuid.uuid4())

        self._umn_pub.emit(
            signal="Q_HOUSEKEEPING_TRIGGER",
            ecosystem="orchestration",
            facts={
                'request_id': request_id,
                'services': services or 'all',
                'mode': 'full'
            }
        )

        timeout = self._request_timeout * len(self.SERVICES)
        start = time.time()

        while request_id in self._pending_requests:
            time.sleep(0.5)
            self.check_timeouts()
            if time.time() - start > timeout:
                break

        return {
            'request_id': request_id,
            'status': 'completed' if request_id not in self._pending_requests else 'timeout'
        }

    def shutdown(self) -> None:
        """Shutdown the orchestrator and close subscriptions."""
        if self._trigger_sub:
            self._trigger_sub.close()

        for sub in self._completion_subs:
            sub.close()

        logger.info("[housekeeping_orchestrator] Shutdown complete")


def main():
    """Run the housekeeping orchestrator as a daemon."""
    import signal
    import sys

    orchestrator = HousekeepingOrchestrator()
    orchestrator.start()

    running = True

    def handle_signal(signum, frame):
        nonlocal running
        logger.info(f"[housekeeping_orchestrator] Received signal {signum}, shutting down...")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("[housekeeping_orchestrator] Running as daemon...")

    try:
        while running:
            time.sleep(10)
            orchestrator.check_timeouts()
    finally:
        orchestrator.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
