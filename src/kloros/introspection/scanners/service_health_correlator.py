#!/usr/bin/env python3
"""
Service Health Correlator Scanner

Detects cascading failures and service dependency issues:
- Service A fails → Service B, C, D all fail
- Resource contention (multiple services fighting for same resource)
- Dependency chains (service waiting on unavailable dependency)
- Systemic failures (all services unhealthy simultaneously)

Purpose:
Identifies when a single root cause creates multiple downstream
failures. Helps KLoROS understand that 10 service failures might
actually be 1 problem, not 10 problems.

Example:
Qdrant in file mode → kloros_voice locks it → all other services
(introspection, memory, investigation) blocked from vector store.
This should surface as "1 root issue: Qdrant concurrency" not
"5 separate service failures".
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple, NamedTuple
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class ServiceHealthCorrelator:
    """Detects cascading service failures and dependency issues."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.storage import MemoryStore

            self.store = MemoryStore()
            self.available = True
            logger.info("[svc_health] ✓ Memory system available")
        except Exception as e:
            logger.warning(f"[svc_health] Memory system not available: {e}")
            self.available = False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="service_health_correlator",
            description="Detects cascading service failures and dependency issues",
            interval_seconds=300,
            priority=3
        )

    def scan(self) -> List:
        return []

    def scan_service_health(
        self,
        lookback_hours: int = 24
    ) -> Dict:
        """
        Scan for service health patterns and correlations.

        Args:
            lookback_hours: How far back to analyze

        Returns:
            Dict with:
            - cascading_failures: List of detected cascades
            - resource_contention: List of resource conflicts
            - dependency_issues: List of dependency problems
            - systemic_failures: List of whole-system failures
        """
        if not self.available:
            logger.warning("[svc_health] Memory not available")
            return {}

        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

        conn = self.store._get_connection()

        cursor = conn.execute("""
            SELECT event_type, content, metadata, timestamp
            FROM events
            WHERE timestamp >= ?
            AND event_type IN ('error', 'investigation_completed', 'service_started',
                              'service_stopped', 'investigation_triggered')
            ORDER BY timestamp ASC
        """, (cutoff_time.isoformat(),))

        events = cursor.fetchall()
        conn.close()

        if not events:
            logger.debug("[svc_health] No events found")
            return {}

        service_events = self._parse_service_events(events)

        findings = {
            'cascading_failures': self._detect_cascading_failures(service_events),
            'resource_contention': self._detect_resource_contention(service_events),
            'dependency_issues': self._detect_dependency_issues(service_events),
            'systemic_failures': self._detect_systemic_failures(service_events)
        }

        return findings

    def _parse_service_events(self, events: List[Tuple]) -> List[Dict]:
        """Parse raw events into structured service health events."""

        service_events = []

        for event_type, content, metadata_json, timestamp in events:
            metadata = json.loads(metadata_json) if metadata_json else {}

            service = self._extract_service_name(content, metadata)

            error_type = None
            if event_type == 'error':
                error_type = self._classify_error(content, metadata)
            elif event_type == 'investigation_completed':
                if 'failed' in metadata.get('conclusion', '').lower():
                    error_type = 'investigation_failed'

            service_events.append({
                'timestamp': datetime.fromisoformat(timestamp),
                'event_type': event_type,
                'service': service,
                'error_type': error_type,
                'content': content,
                'metadata': metadata
            })

        return service_events

    def _extract_service_name(self, content: str, metadata: Dict) -> str:
        """Extract service name from event."""

        if 'service' in metadata:
            return metadata['service']

        if 'component' in metadata:
            return metadata['component']

        content_lower = content.lower()
        known_services = [
            'kloros_voice', 'kloros_introspection', 'kloros_orchestrator',
            'kloros_memory', 'kloros_observer', 'qdrant', 'chromadb',
            'bioreactor', 'chembus', 'mqtt', 'http', 'spica'
        ]

        for service in known_services:
            if service in content_lower or service.replace('_', '-') in content_lower:
                return service

        return 'unknown'

    def _classify_error(self, content: str, metadata: Dict) -> str:
        """Classify error type for correlation."""

        content_lower = content.lower()

        if 'storage' in content_lower or 'already accessed' in content_lower:
            return 'resource_lock'
        elif 'connection refused' in content_lower or 'cannot connect' in content_lower:
            return 'connection_failure'
        elif 'timeout' in content_lower:
            return 'timeout'
        elif 'permission denied' in content_lower:
            return 'permission'
        elif 'not found' in content_lower or 'does not exist' in content_lower:
            return 'missing_resource'
        elif 'import' in content_lower or 'module' in content_lower:
            return 'import_error'
        else:
            return 'general_error'

    def _detect_cascading_failures(
        self,
        events: List[Dict]
    ) -> List[Dict]:
        """
        Detect cascading failures: one service fails, then others fail.

        A cascade is detected when:
        - Multiple services fail within short time window (< 5 minutes)
        - Failures share common error signature
        - Temporal ordering suggests cascade
        """
        cascades = []

        error_events = [e for e in events if e['error_type']]

        time_window = timedelta(minutes=5)

        for idx, initiating_event in enumerate(error_events):
            downstream_failures = []

            window_end = initiating_event['timestamp'] + time_window

            for later_event in error_events[idx + 1:]:
                if later_event['timestamp'] > window_end:
                    break

                if (later_event['service'] != initiating_event['service'] and
                    later_event['error_type'] == initiating_event['error_type']):

                    downstream_failures.append(later_event)

            if len(downstream_failures) >= 2:
                cascade = {
                    'initiating_service': initiating_event['service'],
                    'initiating_error': initiating_event['error_type'],
                    'initiating_time': initiating_event['timestamp'].isoformat(),
                    'affected_services': [e['service'] for e in downstream_failures],
                    'failure_count': len(downstream_failures) + 1,
                    'cascade_duration_seconds': (
                        downstream_failures[-1]['timestamp'] -
                        initiating_event['timestamp']
                    ).total_seconds(),
                    'example_error': initiating_event['content'][:200]
                }

                cascades.append(cascade)

        unique_cascades = self._deduplicate_cascades(cascades)

        return unique_cascades

    def _deduplicate_cascades(self, cascades: List[Dict]) -> List[Dict]:
        """Remove duplicate cascade detections."""

        if not cascades:
            return []

        unique = []
        seen_signatures = set()

        for cascade in cascades:
            sig = f"{cascade['initiating_service']}:{cascade['initiating_error']}"

            if sig not in seen_signatures:
                unique.append(cascade)
                seen_signatures.add(sig)

        return unique

    def _detect_resource_contention(
        self,
        events: List[Dict]
    ) -> List[Dict]:
        """
        Detect resource contention: multiple services competing for resource.

        Detects patterns like:
        - Multiple "resource_lock" errors for same resource
        - One service holding lock, others blocked
        """
        contentions = []

        lock_events = [
            e for e in events
            if e['error_type'] == 'resource_lock'
        ]

        if len(lock_events) < 2:
            return []

        resource_groups = defaultdict(list)

        for event in lock_events:
            resource = self._extract_resource_name(event['content'])
            resource_groups[resource].append(event)

        for resource, group_events in resource_groups.items():
            if len(group_events) >= 2:
                contention = {
                    'resource': resource,
                    'contending_services': list(set(e['service'] for e in group_events)),
                    'lock_attempts': len(group_events),
                    'first_seen': group_events[0]['timestamp'].isoformat(),
                    'last_seen': group_events[-1]['timestamp'].isoformat(),
                    'example_error': group_events[0]['content'][:200]
                }

                contentions.append(contention)

        return contentions

    def _extract_resource_name(self, content: str) -> str:
        """Extract resource name from lock error."""

        content_lower = content.lower()

        if 'qdrant' in content_lower:
            return 'qdrant_storage'
        elif 'chroma' in content_lower:
            return 'chromadb'
        elif 'sqlite' in content_lower or 'database' in content_lower:
            return 'database'
        elif 'file' in content_lower:
            return 'file_system'
        else:
            return 'unknown_resource'

    def _detect_dependency_issues(
        self,
        events: List[Dict]
    ) -> List[Dict]:
        """
        Detect dependency issues: service fails because dependency unavailable.

        Detects:
        - Import errors (missing Python modules)
        - Connection failures (service down)
        - Missing resources (config files, etc.)
        """
        dependency_issues = []

        dependency_error_types = [
            'import_error', 'connection_failure', 'missing_resource'
        ]

        dep_events = [
            e for e in events
            if e['error_type'] in dependency_error_types
        ]

        service_deps = defaultdict(list)

        for event in dep_events:
            service_deps[event['service']].append(event)

        for service, service_events in service_deps.items():
            if len(service_events) >= 2:
                issue = {
                    'service': service,
                    'dependency_type': service_events[0]['error_type'],
                    'failure_count': len(service_events),
                    'first_seen': service_events[0]['timestamp'].isoformat(),
                    'last_seen': service_events[-1]['timestamp'].isoformat(),
                    'example_error': service_events[0]['content'][:200]
                }

                dependency_issues.append(issue)

        return dependency_issues

    def _detect_systemic_failures(
        self,
        events: List[Dict]
    ) -> List[Dict]:
        """
        Detect systemic failures: multiple unrelated services fail together.

        Indicates whole-system problems like:
        - System resource exhaustion (OOM, disk full)
        - Network failure
        - Power/hardware issue
        """
        systemic = []

        error_events = [e for e in events if e['error_type']]

        time_window = timedelta(minutes=10)

        for idx, event in enumerate(error_events):
            window_end = event['timestamp'] + time_window

            concurrent_failures = [event]

            for later_event in error_events[idx + 1:]:
                if later_event['timestamp'] > window_end:
                    break

                if later_event['service'] != event['service']:
                    concurrent_failures.append(later_event)

            unique_services = set(e['service'] for e in concurrent_failures)

            if len(unique_services) >= 3:
                systemic.append({
                    'affected_services': list(unique_services),
                    'failure_count': len(concurrent_failures),
                    'window_start': event['timestamp'].isoformat(),
                    'window_end': window_end.isoformat(),
                    'error_types': list(set(e['error_type'] for e in concurrent_failures))
                })

        return systemic

    def format_findings(self, findings: Dict) -> str:
        """Format health correlation findings as report."""

        if not findings:
            return "✓ No service health issues detected"

        report = []

        if findings.get('cascading_failures'):
            report.append("🔴 CASCADING FAILURES DETECTED")
            for cascade in findings['cascading_failures'][:3]:
                report.append(f"\n  Initiator: {cascade['initiating_service']}")
                report.append(f"  Error: {cascade['initiating_error']}")
                report.append(f"  Affected services: {', '.join(cascade['affected_services'])}")
                report.append(f"  Total failures: {cascade['failure_count']}")
                report.append(f"  Example: {cascade['example_error']}")

        if findings.get('resource_contention'):
            report.append("\n🟠 RESOURCE CONTENTION DETECTED")
            for contention in findings['resource_contention'][:3]:
                report.append(f"\n  Resource: {contention['resource']}")
                report.append(f"  Contending services: {', '.join(contention['contending_services'])}")
                report.append(f"  Lock attempts: {contention['lock_attempts']}")
                report.append(f"  Example: {contention['example_error']}")

        if findings.get('dependency_issues'):
            report.append("\n🟡 DEPENDENCY ISSUES DETECTED")
            for issue in findings['dependency_issues'][:3]:
                report.append(f"\n  Service: {issue['service']}")
                report.append(f"  Type: {issue['dependency_type']}")
                report.append(f"  Failures: {issue['failure_count']}")

        if findings.get('systemic_failures'):
            report.append("\n🔴 SYSTEMIC FAILURES DETECTED")
            for systemic in findings['systemic_failures'][:2]:
                report.append(f"\n  Affected services: {', '.join(systemic['affected_services'])}")
                report.append(f"  Total failures: {systemic['failure_count']}")

        return '\n'.join(report) if report else "✓ No service health issues detected"


def scan_service_health(lookback_hours: int = 24) -> Tuple[Dict, str]:
    """
    Main entry point: Scan for service health correlations.

    Args:
        lookback_hours: How far back to analyze

    Returns:
        (findings_dict, formatted_report)
    """
    correlator = ServiceHealthCorrelator()
    findings = correlator.scan_service_health(lookback_hours)
    report = correlator.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_service_health(lookback_hours=72)

    print(report)
