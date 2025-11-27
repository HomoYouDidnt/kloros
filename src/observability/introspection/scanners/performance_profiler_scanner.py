#!/usr/bin/env python3
"""
Performance Profiler Scanner

Monitors resource usage and performance bottlenecks.
"""

import logging
import json
import psutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class PerformanceProfilerScanner:
    """Monitors resource usage and performance bottlenecks."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.storage import MemoryStore

            self.store = MemoryStore()
            self.available = True
            logger.info("[performance] Memory system available")

            self.psutil_available = self._check_psutil()

            if not self.psutil_available:
                logger.warning("[performance] psutil not available")
                self.available = False

        except Exception as e:
            logger.warning(f"[performance] Initialization failed: {e}")
            self.available = False

    def _check_psutil(self) -> bool:
        """Check if psutil is available."""
        try:
            import psutil
            return True
        except ImportError:
            logger.warning("[performance] psutil not available")
            return False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="performance_profiler_scanner",
            description="Monitors resource usage and performance bottlenecks",
            interval_seconds=300,
            priority=2
        )

    def scan(self) -> List:
        return []

    def scan_performance_profile(
        self,
        lookback_hours: int = 24
    ) -> Dict:
        """
        Analyze performance characteristics from observations.

        Args:
            lookback_hours: How far back to analyze

        Returns:
            {
                'resource_usage': {...},
                'slow_components': [...],
                'memory_leaks': [...],
                'bottlenecks': [...]
            }
        """
        if not self.available:
            logger.warning("[performance] Scanner not available")
            return {}

        findings = {
            'resource_usage': {},
            'slow_components': [],
            'memory_leaks': [],
            'bottlenecks': [],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_hours': lookback_hours
            }
        }

        findings['resource_usage'] = self._collect_current_resource_usage()

        slow_operations = self._analyze_slow_operations(lookback_hours)
        if slow_operations:
            findings['slow_components'] = slow_operations

        memory_trends = self._detect_memory_leaks(lookback_hours)
        if memory_trends:
            findings['memory_leaks'] = memory_trends

        bottlenecks = self._detect_bottlenecks(lookback_hours)
        if bottlenecks:
            findings['bottlenecks'] = bottlenecks

        return findings

    def _collect_current_resource_usage(self) -> Dict:
        """Collect current system resource usage."""
        try:
            import psutil

            current_process = psutil.Process()

            cpu_percent = current_process.cpu_percent(interval=0.1)
            memory_info = current_process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)

            system_cpu = psutil.cpu_percent(interval=0.1)
            system_memory = psutil.virtual_memory()

            daemon_usage = {}

            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue

                    cmdline_str = ' '.join(cmdline)

                    daemon_name = None
                    if 'klr-introspection' in cmdline_str or 'introspection_daemon' in cmdline_str:
                        daemon_name = 'klr-introspection'
                    elif 'klr-observer' in cmdline_str or 'klr_observer' in cmdline_str:
                        daemon_name = 'klr-observer'
                    elif 'klr-orchestrator' in cmdline_str or 'klr_orchestrator' in cmdline_str:
                        daemon_name = 'klr-orchestrator'
                    elif 'kloros_voice' in cmdline_str or 'klr-voice' in cmdline_str:
                        daemon_name = 'klr-voice'

                    if daemon_name:
                        proc_obj = psutil.Process(proc.info['pid'])
                        proc_cpu = proc_obj.cpu_percent(interval=0.1)
                        proc_memory = proc_obj.memory_info().rss / (1024 * 1024)

                        daemon_usage[daemon_name] = {
                            'cpu_percent': round(proc_cpu, 2),
                            'memory_mb': round(proc_memory, 2),
                            'pid': proc.info['pid']
                        }

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            resource_usage = {
                'system': {
                    'cpu_percent': round(system_cpu, 2),
                    'memory_percent': round(system_memory.percent, 2),
                    'memory_available_mb': round(system_memory.available / (1024 * 1024), 2),
                    'memory_total_mb': round(system_memory.total / (1024 * 1024), 2)
                },
                'current_process': {
                    'cpu_percent': round(cpu_percent, 2),
                    'memory_mb': round(memory_mb, 2)
                },
                'daemons': daemon_usage
            }

            return resource_usage

        except Exception as e:
            logger.debug(f"[performance] Error collecting resource usage: {e}")
            return {}

    def _analyze_slow_operations(self, lookback_hours: int) -> List[Dict]:
        """Analyze OBSERVATION events to detect slow operations."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            conn = self.store._get_connection()
            cursor = conn.execute("""
                SELECT content, metadata, timestamp
                FROM events
                WHERE event_type = 'observation'
                AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 500
            """, (cutoff_time.isoformat(),))

            events = cursor.fetchall()
            conn.close()

            operation_durations = defaultdict(list)

            for content, metadata_json, timestamp in events:
                metadata = json.loads(metadata_json) if metadata_json else {}

                duration_ms = self._extract_duration(content, metadata)
                if duration_ms is None:
                    continue

                operation_name = self._extract_operation_name(content, metadata)

                operation_durations[operation_name].append({
                    'duration_ms': duration_ms,
                    'timestamp': timestamp
                })

            slow_components = []
            threshold_ms = 1000

            for operation_name, durations in operation_durations.items():
                if not durations:
                    continue

                duration_values = [d['duration_ms'] for d in durations]
                avg_duration = sum(duration_values) / len(duration_values)
                max_duration = max(duration_values)

                if avg_duration > threshold_ms:
                    component = self._extract_component_from_operation(operation_name)

                    slow_components.append({
                        'component': component,
                        'operation': operation_name,
                        'avg_duration_ms': round(avg_duration, 2),
                        'max_duration_ms': round(max_duration, 2),
                        'threshold_ms': threshold_ms,
                        'sample_count': len(durations),
                        'severity': self._classify_performance_severity(avg_duration, threshold_ms)
                    })

            slow_components.sort(key=lambda x: x['avg_duration_ms'], reverse=True)

            return slow_components

        except Exception as e:
            logger.debug(f"[performance] Error analyzing slow operations: {e}")
            return []

    def _extract_duration(self, content: str, metadata: Dict) -> Optional[float]:
        """Extract duration from event content or metadata."""
        if 'duration_ms' in metadata:
            return float(metadata['duration_ms'])

        if 'duration' in metadata:
            duration = metadata['duration']
            if isinstance(duration, (int, float)):
                return float(duration)

        import re

        duration_patterns = [
            r'(\d+\.?\d*)\s*ms',
            r'(\d+\.?\d*)\s*milliseconds',
            r'took\s+(\d+\.?\d*)\s*ms',
            r'duration:\s*(\d+\.?\d*)',
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, content.lower())
            if match:
                return float(match.group(1))

        return None

    def _extract_operation_name(self, content: str, metadata: Dict) -> str:
        """Extract operation name from event."""
        if 'operation' in metadata:
            return metadata['operation']

        if 'function' in metadata:
            return metadata['function']

        content_lower = content.lower()

        operations = [
            'scan_service_health', 'scan_code_quality', 'scan_test_coverage',
            'scan_performance_profile', 'query_memory', 'consolidate_episodes',
            'vector_search', 'embed_text', 'investigate', 'reflect'
        ]

        for op in operations:
            if op in content_lower:
                return op

        return 'unknown_operation'

    def _extract_component_from_operation(self, operation_name: str) -> str:
        """Extract component name from operation name."""
        if 'scan_' in operation_name:
            return 'klr-introspection'
        elif 'consolidate' in operation_name or 'query' in operation_name:
            return 'kloros_memory'
        elif 'vector' in operation_name or 'embed' in operation_name:
            return 'vector_store'
        elif 'investigate' in operation_name:
            return 'klr-observer'
        elif 'reflect' in operation_name:
            return 'klr-orchestrator'
        else:
            return 'unknown'

    def _classify_performance_severity(self, avg_duration: float, threshold: float) -> str:
        """Classify performance severity based on duration."""
        if avg_duration >= threshold * 5:
            return 'critical'
        elif avg_duration >= threshold * 3:
            return 'error'
        elif avg_duration >= threshold:
            return 'warning'
        else:
            return 'info'

    def _detect_memory_leaks(self, lookback_hours: int) -> List[Dict]:
        """Detect potential memory leaks by analyzing trends."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            conn = self.store._get_connection()
            cursor = conn.execute("""
                SELECT content, metadata, timestamp
                FROM events
                WHERE event_type = 'observation'
                AND (content LIKE '%memory%' OR metadata LIKE '%memory%')
                AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (cutoff_time.isoformat(),))

            events = cursor.fetchall()
            conn.close()

            component_memory_trends = defaultdict(list)

            for content, metadata_json, timestamp in events:
                metadata = json.loads(metadata_json) if metadata_json else {}

                memory_mb = self._extract_memory_usage(content, metadata)
                if memory_mb is None:
                    continue

                component = metadata.get('component', 'unknown')

                component_memory_trends[component].append({
                    'memory_mb': memory_mb,
                    'timestamp': datetime.fromisoformat(timestamp)
                })

            memory_leaks = []

            for component, trends in component_memory_trends.items():
                if len(trends) < 3:
                    continue

                trends.sort(key=lambda x: x['timestamp'])

                memory_values = [t['memory_mb'] for t in trends]
                time_span_hours = (
                    trends[-1]['timestamp'] - trends[0]['timestamp']
                ).total_seconds() / 3600

                if time_span_hours < 1:
                    continue

                initial_memory = memory_values[0]
                final_memory = memory_values[-1]
                memory_increase = final_memory - initial_memory

                if memory_increase > 50:
                    growth_rate_mb_per_hour = memory_increase / time_span_hours

                    memory_leaks.append({
                        'component': component,
                        'initial_memory_mb': round(initial_memory, 2),
                        'final_memory_mb': round(final_memory, 2),
                        'memory_increase_mb': round(memory_increase, 2),
                        'growth_rate_mb_per_hour': round(growth_rate_mb_per_hour, 2),
                        'time_span_hours': round(time_span_hours, 2),
                        'severity': self._classify_memory_leak_severity(growth_rate_mb_per_hour)
                    })

            memory_leaks.sort(key=lambda x: x['growth_rate_mb_per_hour'], reverse=True)

            return memory_leaks

        except Exception as e:
            logger.debug(f"[performance] Error detecting memory leaks: {e}")
            return []

    def _extract_memory_usage(self, content: str, metadata: Dict) -> Optional[float]:
        """Extract memory usage from event content or metadata."""
        if 'memory_mb' in metadata:
            return float(metadata['memory_mb'])

        if 'memory' in metadata:
            memory = metadata['memory']
            if isinstance(memory, (int, float)):
                return float(memory)

        import re

        memory_patterns = [
            r'(\d+\.?\d*)\s*mb',
            r'memory:\s*(\d+\.?\d*)',
        ]

        for pattern in memory_patterns:
            match = re.search(pattern, content.lower())
            if match:
                return float(match.group(1))

        return None

    def _classify_memory_leak_severity(self, growth_rate: float) -> str:
        """Classify memory leak severity based on growth rate."""
        if growth_rate >= 100:
            return 'critical'
        elif growth_rate >= 50:
            return 'error'
        elif growth_rate >= 20:
            return 'warning'
        else:
            return 'info'

    def _detect_bottlenecks(self, lookback_hours: int) -> List[Dict]:
        """Detect performance bottlenecks from error and observation events."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            conn = self.store._get_connection()
            cursor = conn.execute("""
                SELECT event_type, content, metadata, timestamp
                FROM events
                WHERE timestamp >= ?
                AND (
                    (event_type = 'error' AND (
                        content LIKE '%timeout%' OR
                        content LIKE '%slow%' OR
                        content LIKE '%blocked%' OR
                        content LIKE '%lock%'
                    ))
                    OR (event_type = 'observation' AND (
                        content LIKE '%bottleneck%' OR
                        content LIKE '%contention%'
                    ))
                )
                ORDER BY timestamp DESC
                LIMIT 200
            """, (cutoff_time.isoformat(),))

            events = cursor.fetchall()
            conn.close()

            bottleneck_types = defaultdict(list)

            for event_type, content, metadata_json, timestamp in events:
                metadata = json.loads(metadata_json) if metadata_json else {}

                bottleneck_type = self._classify_bottleneck(content, metadata)
                component = metadata.get('component', self._extract_service_name(content))

                bottleneck_types[bottleneck_type].append({
                    'component': component,
                    'timestamp': timestamp,
                    'content': content,
                    'event_type': event_type
                })

            bottlenecks = []

            for bottleneck_type, occurrences in bottleneck_types.items():
                if len(occurrences) >= 2:
                    component_counts = defaultdict(int)
                    for occ in occurrences:
                        component_counts[occ['component']] += 1

                    most_affected_component = max(
                        component_counts.items(),
                        key=lambda x: x[1]
                    )[0]

                    bottlenecks.append({
                        'type': bottleneck_type,
                        'occurrence_count': len(occurrences),
                        'affected_component': most_affected_component,
                        'first_seen': occurrences[-1]['timestamp'],
                        'last_seen': occurrences[0]['timestamp'],
                        'example_error': occurrences[0]['content'][:200],
                        'severity': self._classify_bottleneck_severity(len(occurrences))
                    })

            bottlenecks.sort(key=lambda x: x['occurrence_count'], reverse=True)

            return bottlenecks

        except Exception as e:
            logger.debug(f"[performance] Error detecting bottlenecks: {e}")
            return []

    def _classify_bottleneck(self, content: str, metadata: Dict) -> str:
        """Classify bottleneck type from event content."""
        content_lower = content.lower()

        if 'timeout' in content_lower:
            return 'timeout'
        elif 'lock' in content_lower or 'blocked' in content_lower:
            return 'resource_lock'
        elif 'slow query' in content_lower or 'database' in content_lower:
            return 'database_query'
        elif 'io' in content_lower or 'disk' in content_lower:
            return 'io_bottleneck'
        elif 'network' in content_lower or 'connection' in content_lower:
            return 'network_bottleneck'
        else:
            return 'general_bottleneck'

    def _extract_service_name(self, content: str) -> str:
        """Extract service name from content."""
        content_lower = content.lower()

        services = [
            'klr-introspection', 'klr-observer', 'klr-orchestrator',
            'klr-voice', 'kloros_memory', 'qdrant', 'chromadb'
        ]

        for service in services:
            if service in content_lower or service.replace('-', '_') in content_lower:
                return service

        return 'unknown'

    def _classify_bottleneck_severity(self, occurrence_count: int) -> str:
        """Classify bottleneck severity based on occurrence count."""
        if occurrence_count >= 20:
            return 'critical'
        elif occurrence_count >= 10:
            return 'error'
        elif occurrence_count >= 5:
            return 'warning'
        else:
            return 'info'

    def format_findings(self, findings: Dict) -> str:
        """Format performance findings as human-readable report."""
        if not findings:
            return "No performance issues detected"

        report = []

        resource_usage = findings.get('resource_usage', {})
        if resource_usage:
            system = resource_usage.get('system', {})
            if system:
                report.append("SYSTEM RESOURCE USAGE")
                report.append(f"  CPU: {system.get('cpu_percent', 0)}%")
                report.append(
                    f"  Memory: {system.get('memory_percent', 0)}% "
                    f"({system.get('memory_available_mb', 0):.0f} MB available / "
                    f"{system.get('memory_total_mb', 0):.0f} MB total)"
                )

            daemons = resource_usage.get('daemons', {})
            if daemons:
                report.append("\nDAEMON RESOURCE USAGE")
                for daemon_name, daemon_stats in sorted(daemons.items()):
                    report.append(
                        f"  {daemon_name}: CPU={daemon_stats['cpu_percent']}%, "
                        f"Memory={daemon_stats['memory_mb']:.1f} MB (PID: {daemon_stats['pid']})"
                    )

        slow_components = findings.get('slow_components', [])
        if slow_components:
            report.append(f"\nSLOW OPERATIONS ({len(slow_components)} detected)")

            critical = [s for s in slow_components if s['severity'] == 'critical']
            if critical:
                report.append(f"\n  Critical (>= 5x threshold): {len(critical)} operations")
                for slow in critical[:3]:
                    report.append(
                        f"    - {slow['operation']} in {slow['component']}: "
                        f"avg={slow['avg_duration_ms']:.0f}ms, max={slow['max_duration_ms']:.0f}ms "
                        f"(threshold={slow['threshold_ms']}ms, n={slow['sample_count']})"
                    )

            errors = [s for s in slow_components if s['severity'] == 'error']
            if errors:
                report.append(f"\n  High (>= 3x threshold): {len(errors)} operations")
                for slow in errors[:3]:
                    report.append(
                        f"    - {slow['operation']} in {slow['component']}: "
                        f"avg={slow['avg_duration_ms']:.0f}ms (n={slow['sample_count']})"
                    )

        memory_leaks = findings.get('memory_leaks', [])
        if memory_leaks:
            report.append(f"\nPOTENTIAL MEMORY LEAKS ({len(memory_leaks)} detected)")
            for leak in memory_leaks[:5]:
                report.append(
                    f"  - {leak['component']}: "
                    f"{leak['initial_memory_mb']:.1f} MB -> {leak['final_memory_mb']:.1f} MB "
                    f"(+{leak['memory_increase_mb']:.1f} MB over {leak['time_span_hours']:.1f}h)"
                )
                report.append(
                    f"    Growth rate: {leak['growth_rate_mb_per_hour']:.1f} MB/hour "
                    f"(severity: {leak['severity']})"
                )

        bottlenecks = findings.get('bottlenecks', [])
        if bottlenecks:
            report.append(f"\nPERFORMANCE BOTTLENECKS ({len(bottlenecks)} detected)")
            for bottleneck in bottlenecks[:5]:
                report.append(
                    f"  - {bottleneck['type']} in {bottleneck['affected_component']}: "
                    f"{bottleneck['occurrence_count']} occurrences (severity: {bottleneck['severity']})"
                )
                report.append(f"    Example: {bottleneck['example_error']}")

        if not report:
            return "No performance issues detected"

        scan_meta = findings.get('scan_metadata', {})
        header = [
            "="*60,
            "PERFORMANCE PROFILE SCAN REPORT",
            f"Timestamp: {scan_meta.get('timestamp', 'N/A')}",
            f"Lookback: {scan_meta.get('lookback_hours', 24)} hours",
            "="*60
        ]

        return '\n'.join(header + [''] + report)


def scan_performance_profile_standalone(
    lookback_hours: int = 24
) -> Tuple[Dict, str]:
    """CLI entry point: Scan performance profile."""
    scanner = PerformanceProfilerScanner()
    findings = scanner.scan_performance_profile(lookback_hours)
    report = scanner.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_performance_profile_standalone(
        lookback_hours=24
    )

    print(report)

    if findings:
        print("\n" + "="*60)
        print("DETAILED FINDINGS SUMMARY")
        print("="*60)
        print(f"Slow components: {len(findings.get('slow_components', []))}")
        print(f"Memory leaks: {len(findings.get('memory_leaks', []))}")
        print(f"Bottlenecks: {len(findings.get('bottlenecks', []))}")
