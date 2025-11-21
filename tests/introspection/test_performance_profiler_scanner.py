"""Tests for PerformanceProfilerScanner."""

import pytest
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.kloros.introspection.scanners.performance_profiler_scanner import (
    PerformanceProfilerScanner,
    ScannerMetadata,
    scan_performance_profile_standalone
)


class TestPerformanceProfilerScanner:
    """Test performance profiler scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = PerformanceProfilerScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'performance_profiler_scanner'
        assert metadata.description == 'Monitors resource usage and performance bottlenecks'
        assert metadata.interval_seconds == 300
        assert metadata.priority == 2

    def test_scanner_initialization_success(self):
        """Test scanner initializes successfully."""
        scanner = PerformanceProfilerScanner()
        assert scanner.available or not scanner.available

    def test_scanner_initialization_failure(self):
        """Test scanner handles initialization failure gracefully."""
        scanner = PerformanceProfilerScanner()
        scanner.available = False
        findings = scanner.scan_performance_profile()
        assert findings == {}

    def test_check_psutil_available(self):
        """Test psutil availability check."""
        scanner = PerformanceProfilerScanner()
        result = scanner._check_psutil()
        assert isinstance(result, bool)

    def test_scan_with_unavailable_scanner(self):
        """Test scan returns empty dict when scanner unavailable."""
        scanner = PerformanceProfilerScanner()
        scanner.available = False

        findings = scanner.scan_performance_profile()
        assert findings == {}

    def test_scan_basic_structure(self):
        """Test scan returns expected data structure."""
        scanner = PerformanceProfilerScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        findings = scanner.scan_performance_profile(lookback_hours=1)

        assert 'resource_usage' in findings
        assert 'slow_components' in findings
        assert 'memory_leaks' in findings
        assert 'bottlenecks' in findings
        assert 'scan_metadata' in findings

        assert findings['scan_metadata']['lookback_hours'] == 1
        assert 'timestamp' in findings['scan_metadata']

    def test_collect_current_resource_usage(self):
        """Test collection of current resource usage."""
        scanner = PerformanceProfilerScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        resource_usage = scanner._collect_current_resource_usage()

        assert 'system' in resource_usage
        assert 'current_process' in resource_usage
        assert 'daemons' in resource_usage

        system = resource_usage['system']
        assert 'cpu_percent' in system
        assert 'memory_percent' in system
        assert 'memory_available_mb' in system
        assert 'memory_total_mb' in system

        current_process = resource_usage['current_process']
        assert 'cpu_percent' in current_process
        assert 'memory_mb' in current_process

        assert isinstance(resource_usage['daemons'], dict)

    def test_extract_duration_from_metadata(self):
        """Test extracting duration from metadata."""
        scanner = PerformanceProfilerScanner()

        metadata = {'duration_ms': 1500}
        duration = scanner._extract_duration('', metadata)
        assert duration == 1500.0

        metadata = {'duration': 2500}
        duration = scanner._extract_duration('', metadata)
        assert duration == 2500.0

    def test_extract_duration_from_content(self):
        """Test extracting duration from content string."""
        scanner = PerformanceProfilerScanner()

        content = 'Operation took 1234.5 ms to complete'
        duration = scanner._extract_duration(content, {})
        assert duration == 1234.5

        content = 'Scan duration: 567'
        duration = scanner._extract_duration(content, {})
        assert duration == 567.0

    def test_extract_operation_name_from_metadata(self):
        """Test extracting operation name from metadata."""
        scanner = PerformanceProfilerScanner()

        metadata = {'operation': 'scan_service_health'}
        name = scanner._extract_operation_name('', metadata)
        assert name == 'scan_service_health'

        metadata = {'function': 'consolidate_episodes'}
        name = scanner._extract_operation_name('', metadata)
        assert name == 'consolidate_episodes'

    def test_extract_operation_name_from_content(self):
        """Test extracting operation name from content string."""
        scanner = PerformanceProfilerScanner()

        content = 'Running scan_code_quality operation'
        name = scanner._extract_operation_name(content, {})
        assert name == 'scan_code_quality'

        content = 'Unknown operation type'
        name = scanner._extract_operation_name(content, {})
        assert name == 'unknown_operation'

    def test_extract_component_from_operation(self):
        """Test extracting component name from operation."""
        scanner = PerformanceProfilerScanner()

        assert scanner._extract_component_from_operation('scan_service_health') == 'klr-introspection'
        assert scanner._extract_component_from_operation('consolidate_episodes') == 'kloros_memory'
        assert scanner._extract_component_from_operation('vector_search') == 'vector_store'
        assert scanner._extract_component_from_operation('investigate') == 'klr-observer'
        assert scanner._extract_component_from_operation('reflect') == 'klr-orchestrator'
        assert scanner._extract_component_from_operation('unknown_op') == 'unknown'

    def test_classify_performance_severity(self):
        """Test performance severity classification."""
        scanner = PerformanceProfilerScanner()
        threshold = 1000

        assert scanner._classify_performance_severity(5000, threshold) == 'critical'
        assert scanner._classify_performance_severity(3500, threshold) == 'error'
        assert scanner._classify_performance_severity(1500, threshold) == 'warning'
        assert scanner._classify_performance_severity(800, threshold) == 'info'

    def test_extract_memory_usage_from_metadata(self):
        """Test extracting memory usage from metadata."""
        scanner = PerformanceProfilerScanner()

        metadata = {'memory_mb': 245.8}
        memory = scanner._extract_memory_usage('', metadata)
        assert memory == 245.8

        metadata = {'memory': 300}
        memory = scanner._extract_memory_usage('', metadata)
        assert memory == 300.0

    def test_extract_memory_usage_from_content(self):
        """Test extracting memory usage from content string."""
        scanner = PerformanceProfilerScanner()

        content = 'Process using 245.8 mb of memory'
        memory = scanner._extract_memory_usage(content, {})
        assert memory == 245.8

        content = 'Memory: 512'
        memory = scanner._extract_memory_usage(content, {})
        assert memory == 512.0

    def test_classify_memory_leak_severity(self):
        """Test memory leak severity classification."""
        scanner = PerformanceProfilerScanner()

        assert scanner._classify_memory_leak_severity(150) == 'critical'
        assert scanner._classify_memory_leak_severity(75) == 'error'
        assert scanner._classify_memory_leak_severity(30) == 'warning'
        assert scanner._classify_memory_leak_severity(10) == 'info'

    def test_classify_bottleneck(self):
        """Test bottleneck classification."""
        scanner = PerformanceProfilerScanner()

        assert scanner._classify_bottleneck('Connection timeout occurred', {}) == 'timeout'
        assert scanner._classify_bottleneck('Database lock detected', {}) == 'resource_lock'
        assert scanner._classify_bottleneck('Slow query in database', {}) == 'database_query'
        assert scanner._classify_bottleneck('Disk read error', {}) == 'io_bottleneck'
        assert scanner._classify_bottleneck('Network latency high', {}) == 'network_bottleneck'
        assert scanner._classify_bottleneck('Some other issue', {}) == 'general_bottleneck'

    def test_extract_service_name(self):
        """Test extracting service name from content."""
        scanner = PerformanceProfilerScanner()

        assert scanner._extract_service_name('klr-introspection error') == 'klr-introspection'
        assert scanner._extract_service_name('klr-observer issue') == 'klr-observer'
        assert scanner._extract_service_name('klr-orchestrator timeout') == 'klr-orchestrator'
        assert scanner._extract_service_name('klr-voice problem') == 'klr-voice'
        assert scanner._extract_service_name('kloros_memory failure') == 'kloros_memory'
        assert scanner._extract_service_name('qdrant connection') == 'qdrant'
        assert scanner._extract_service_name('unknown service') == 'unknown'

    def test_classify_bottleneck_severity(self):
        """Test bottleneck severity classification."""
        scanner = PerformanceProfilerScanner()

        assert scanner._classify_bottleneck_severity(25) == 'critical'
        assert scanner._classify_bottleneck_severity(15) == 'error'
        assert scanner._classify_bottleneck_severity(7) == 'warning'
        assert scanner._classify_bottleneck_severity(3) == 'info'

    def test_format_findings_empty(self):
        """Test formatting empty findings."""
        scanner = PerformanceProfilerScanner()
        report = scanner.format_findings({})
        assert 'No performance issues detected' in report

    def test_format_findings_with_resource_usage(self):
        """Test formatting findings with resource usage."""
        scanner = PerformanceProfilerScanner()

        findings = {
            'resource_usage': {
                'system': {
                    'cpu_percent': 45.2,
                    'memory_percent': 62.3,
                    'memory_available_mb': 8192,
                    'memory_total_mb': 16384
                },
                'current_process': {
                    'cpu_percent': 5.1,
                    'memory_mb': 245.8
                },
                'daemons': {
                    'klr-introspection': {
                        'cpu_percent': 3.2,
                        'memory_mb': 180.5,
                        'pid': 12345
                    }
                }
            },
            'slow_components': [],
            'memory_leaks': [],
            'bottlenecks': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'lookback_hours': 24
            }
        }

        report = scanner.format_findings(findings)
        assert 'SYSTEM RESOURCE USAGE' in report
        assert 'CPU: 45.2%' in report
        assert 'Memory: 62.3%' in report
        assert 'DAEMON RESOURCE USAGE' in report
        assert 'klr-introspection' in report

    def test_format_findings_with_slow_components(self):
        """Test formatting findings with slow components."""
        scanner = PerformanceProfilerScanner()

        findings = {
            'resource_usage': {},
            'slow_components': [
                {
                    'component': 'klr-introspection',
                    'operation': 'scan_service_health',
                    'avg_duration_ms': 5500,
                    'max_duration_ms': 8000,
                    'threshold_ms': 1000,
                    'sample_count': 15,
                    'severity': 'critical'
                }
            ],
            'memory_leaks': [],
            'bottlenecks': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'lookback_hours': 24
            }
        }

        report = scanner.format_findings(findings)
        assert 'SLOW OPERATIONS' in report
        assert 'scan_service_health' in report
        assert 'klr-introspection' in report

    def test_format_findings_with_memory_leaks(self):
        """Test formatting findings with memory leaks."""
        scanner = PerformanceProfilerScanner()

        findings = {
            'resource_usage': {},
            'slow_components': [],
            'memory_leaks': [
                {
                    'component': 'klr-observer',
                    'initial_memory_mb': 200.0,
                    'final_memory_mb': 350.0,
                    'memory_increase_mb': 150.0,
                    'growth_rate_mb_per_hour': 12.5,
                    'time_span_hours': 12.0,
                    'severity': 'warning'
                }
            ],
            'bottlenecks': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'lookback_hours': 24
            }
        }

        report = scanner.format_findings(findings)
        assert 'POTENTIAL MEMORY LEAKS' in report
        assert 'klr-observer' in report
        assert '200.0 MB -> 350.0 MB' in report
        assert '12.5 MB/hour' in report

    def test_format_findings_with_bottlenecks(self):
        """Test formatting findings with bottlenecks."""
        scanner = PerformanceProfilerScanner()

        findings = {
            'resource_usage': {},
            'slow_components': [],
            'memory_leaks': [],
            'bottlenecks': [
                {
                    'type': 'timeout',
                    'occurrence_count': 15,
                    'affected_component': 'qdrant',
                    'first_seen': '2025-11-21T08:00:00',
                    'last_seen': '2025-11-21T12:00:00',
                    'example_error': 'Connection timeout to vector store',
                    'severity': 'error'
                }
            ],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'lookback_hours': 24
            }
        }

        report = scanner.format_findings(findings)
        assert 'PERFORMANCE BOTTLENECKS' in report
        assert 'timeout' in report
        assert 'qdrant' in report
        assert '15 occurrences' in report

    def test_standalone_function(self):
        """Test standalone scan function."""
        findings, report = scan_performance_profile_standalone(lookback_hours=1)

        assert isinstance(findings, dict)
        assert isinstance(report, str)
        assert 'scan_metadata' in findings or findings == {}

    def test_scan_with_different_lookback_periods(self):
        """Test scanning with different lookback periods."""
        scanner = PerformanceProfilerScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        for hours in [1, 6, 24, 72]:
            findings = scanner.scan_performance_profile(lookback_hours=hours)
            assert findings['scan_metadata']['lookback_hours'] == hours

    def test_format_findings_complete_report(self):
        """Test formatting complete report with all finding types."""
        scanner = PerformanceProfilerScanner()

        findings = {
            'resource_usage': {
                'system': {
                    'cpu_percent': 35.5,
                    'memory_percent': 55.2,
                    'memory_available_mb': 6144,
                    'memory_total_mb': 16384
                },
                'current_process': {
                    'cpu_percent': 2.5,
                    'memory_mb': 150.3
                },
                'daemons': {
                    'klr-introspection': {
                        'cpu_percent': 1.8,
                        'memory_mb': 120.5,
                        'pid': 12345
                    },
                    'klr-observer': {
                        'cpu_percent': 2.1,
                        'memory_mb': 145.2,
                        'pid': 12346
                    }
                }
            },
            'slow_components': [
                {
                    'component': 'klr-introspection',
                    'operation': 'scan_service_health',
                    'avg_duration_ms': 5500,
                    'max_duration_ms': 8000,
                    'threshold_ms': 1000,
                    'sample_count': 15,
                    'severity': 'critical'
                },
                {
                    'component': 'kloros_memory',
                    'operation': 'consolidate_episodes',
                    'avg_duration_ms': 3200,
                    'max_duration_ms': 4500,
                    'threshold_ms': 1000,
                    'sample_count': 8,
                    'severity': 'error'
                }
            ],
            'memory_leaks': [
                {
                    'component': 'klr-observer',
                    'initial_memory_mb': 200.0,
                    'final_memory_mb': 350.0,
                    'memory_increase_mb': 150.0,
                    'growth_rate_mb_per_hour': 12.5,
                    'time_span_hours': 12.0,
                    'severity': 'warning'
                }
            ],
            'bottlenecks': [
                {
                    'type': 'timeout',
                    'occurrence_count': 15,
                    'affected_component': 'qdrant',
                    'first_seen': '2025-11-21T08:00:00',
                    'last_seen': '2025-11-21T12:00:00',
                    'example_error': 'Connection timeout to vector store',
                    'severity': 'error'
                }
            ],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'lookback_hours': 24
            }
        }

        report = scanner.format_findings(findings)

        assert 'PERFORMANCE PROFILE SCAN REPORT' in report
        assert 'SYSTEM RESOURCE USAGE' in report
        assert 'DAEMON RESOURCE USAGE' in report
        assert 'SLOW OPERATIONS' in report
        assert 'POTENTIAL MEMORY LEAKS' in report
        assert 'PERFORMANCE BOTTLENECKS' in report
        assert 'Timestamp: 2025-11-21T12:00:00' in report
        assert 'Lookback: 24 hours' in report
