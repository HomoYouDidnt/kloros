#!/usr/bin/env python3
"""
Tests for CrossSystemPatternScanner

Comprehensive test suite covering:
- Co-occurrence detection
- Architectural smell detection
- Data collection and fallback
- Error handling
- CapabilityGap conversion
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

import sys
sys.path.insert(0, '/home/kloros/src')

from src.observability.introspection.scanners.cross_system_pattern_scanner import (
    CrossSystemPatternScanner,
    ScannerMetadata
)


class TestCrossSystemPatternScannerInitialization:
    """Test scanner initialization and metadata."""

    def test_get_metadata(self):
        """Test scanner metadata is correct."""
        scanner = CrossSystemPatternScanner()
        metadata = scanner.get_metadata()

        assert metadata.name == "cross_system_pattern_scanner"
        assert metadata.interval_seconds == 1800
        assert metadata.priority == 1
        assert "co-occurrence" in metadata.description.lower()

    def test_initialization_with_memory(self):
        """Test scanner initializes successfully with memory available."""
        scanner = CrossSystemPatternScanner()

        if scanner.available:
            assert scanner.store is not None
            assert scanner.other_scanners is not None
            assert len(scanner.other_scanners) > 0

    def test_initialization_without_memory(self):
        """Test scanner handles missing memory gracefully."""
        with patch('kloros_memory.storage.MemoryStore',
                   side_effect=ImportError("No module")):
            scanner = CrossSystemPatternScanner()

            assert scanner.available is False
            assert scanner.other_scanners == []

    def test_default_smell_detection_disabled(self):
        """Test architectural smell detection is disabled by default."""
        scanner = CrossSystemPatternScanner()

        assert scanner.detect_smells_enabled is False

    def test_scanner_list_initialization(self):
        """Test all Phase 1-3 scanners are initialized."""
        scanner = CrossSystemPatternScanner()

        if scanner.available and scanner.other_scanners:
            scanner_names = []
            for s in scanner.other_scanners:
                if hasattr(s, 'get_metadata'):
                    scanner_names.append(s.get_metadata().name)
                else:
                    scanner_names.append(s.__class__.__name__.lower())

            expected_scanners = [
                'code_quality_scanner',
                'test_coverage_scanner',
                'performance_profiler_scanner',
                'service_health_correlator'
            ]

            for expected in expected_scanners:
                assert any(expected == name for name in scanner_names), \
                    f"{expected} not found in scanner list"


class TestCoOccurrenceDetection:
    """Test co-occurrence pattern detection."""

    def test_single_component_multiple_issues(self):
        """Test detection when one component has multiple issues."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [{
                    'module': '/home/kloros/src/test.py',
                    'complexity': 25,
                    'severity': 'critical'
                }],
                'maintainability_issues': [{
                    'module': '/home/kloros/src/test.py',
                    'maintainability_index': 30,
                    'severity': 'error'
                }]
            }
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert len(co_occurrences) == 1
        assert co_occurrences[0]['component'] == '/home/kloros/src/test.py'
        assert co_occurrences[0]['issue_count'] == 2
        assert co_occurrences[0]['severity_score'] > 0

    def test_multiple_components_different_combinations(self):
        """Test detection across multiple components with different issue combinations."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [
                    {'module': '/home/kloros/src/component_a.py', 'complexity': 20, 'severity': 'error'},
                    {'module': '/home/kloros/src/component_b.py', 'complexity': 15, 'severity': 'warning'}
                ]
            },
            'test_coverage_scanner': {
                'uncovered_modules': [
                    {'module': '/home/kloros/src/component_a.py', 'coverage_percent': 20, 'severity': 'critical'},
                    {'module': '/home/kloros/src/component_c.py', 'coverage_percent': 45, 'severity': 'warning'}
                ]
            }
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert len(co_occurrences) == 1
        assert co_occurrences[0]['component'] == '/home/kloros/src/component_a.py'
        assert co_occurrences[0]['issue_count'] == 2

    def test_empty_findings(self):
        """Test co-occurrence detection with empty findings."""
        scanner = CrossSystemPatternScanner()

        co_occurrences = scanner._detect_co_occurrences({})

        assert co_occurrences == []

    def test_single_issue_per_component(self):
        """Test that components with only 1 issue are not included."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [
                    {'module': '/home/kloros/src/component_a.py', 'complexity': 20, 'severity': 'error'}
                ]
            },
            'test_coverage_scanner': {
                'uncovered_modules': [
                    {'module': '/home/kloros/src/component_b.py', 'coverage_percent': 20, 'severity': 'critical'}
                ]
            }
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert len(co_occurrences) == 0

    def test_severity_ranking(self):
        """Test that co-occurrences are ranked by severity score."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [
                    {'module': '/home/kloros/src/critical.py', 'complexity': 25, 'severity': 'critical'},
                    {'module': '/home/kloros/src/warning.py', 'complexity': 12, 'severity': 'warning'}
                ],
                'maintainability_issues': [
                    {'module': '/home/kloros/src/critical.py', 'maintainability_index': 20, 'severity': 'critical'},
                    {'module': '/home/kloros/src/warning.py', 'maintainability_index': 60, 'severity': 'warning'}
                ]
            }
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert len(co_occurrences) == 2
        assert co_occurrences[0]['component'] == '/home/kloros/src/critical.py'
        assert co_occurrences[0]['severity_score'] > co_occurrences[1]['severity_score']

    def test_pattern_type_classification_quality_deterioration(self):
        """Test pattern type classification for quality deterioration."""
        scanner = CrossSystemPatternScanner()

        issues = [
            {'type': 'high_complexity', 'severity': 'error'},
            {'type': 'low_maintainability', 'severity': 'error'}
        ]

        pattern_type = scanner._classify_pattern_type(issues)

        assert pattern_type == 'quality_deterioration'

    def test_pattern_type_classification_performance_cluster(self):
        """Test pattern type classification for performance cluster."""
        scanner = CrossSystemPatternScanner()

        issues = [
            {'type': 'slow_operation', 'severity': 'warning'},
            {'type': 'memory_leak', 'severity': 'error'}
        ]

        pattern_type = scanner._classify_pattern_type(issues)

        assert pattern_type == 'performance_cluster'

    def test_pattern_type_classification_multi_dimensional(self):
        """Test pattern type classification for multi-dimensional issues."""
        scanner = CrossSystemPatternScanner()

        issues = [
            {'type': 'high_complexity', 'severity': 'error'},
            {'type': 'low_coverage', 'severity': 'critical'},
            {'type': 'slow_operation', 'severity': 'warning'},
            {'type': 'code_smell', 'severity': 'info'}
        ]

        pattern_type = scanner._classify_pattern_type(issues)

        assert pattern_type == 'multi_dimensional_issue'

    def test_severity_score_calculation(self):
        """Test severity score calculation with different severities."""
        scanner = CrossSystemPatternScanner()

        issues = [
            {'severity': 'critical'},
            {'severity': 'error'},
            {'severity': 'warning'},
            {'severity': 'info'}
        ]

        score = scanner._calculate_severity_score(issues)

        assert score == 185


class TestArchitecturalSmellDetection:
    """Test architectural smell detection."""

    def test_god_object_detection(self):
        """Test God Object detection with all criteria met."""
        scanner = CrossSystemPatternScanner()
        scanner.detect_smells_enabled = True

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [{
                    'module': '/home/kloros/src/god.py',
                    'complexity': 25,
                    'severity': 'critical'
                }],
                'maintainability_issues': [{
                    'module': '/home/kloros/src/god.py',
                    'maintainability_index': 28,
                    'loc': 782,
                    'severity': 'error'
                }]
            }
        }

        god_objects = scanner._detect_god_objects(findings)

        assert len(god_objects) == 1
        assert god_objects[0]['smell_type'] == 'god_object'
        assert god_objects[0]['component'] == '/home/kloros/src/god.py'
        assert god_objects[0]['severity'] == 'critical'
        assert god_objects[0]['evidence']['cyclomatic_complexity'] == 25
        assert god_objects[0]['evidence']['lines_of_code'] == 782
        assert god_objects[0]['evidence']['maintainability_index'] == 28

    def test_god_object_not_detected_insufficient_criteria(self):
        """Test God Object not detected when criteria not fully met."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [{
                    'module': '/home/kloros/src/component.py',
                    'complexity': 18,
                    'severity': 'warning'
                }],
                'maintainability_issues': [{
                    'module': '/home/kloros/src/component.py',
                    'maintainability_index': 35,
                    'loc': 450,
                    'severity': 'warning'
                }]
            }
        }

        god_objects = scanner._detect_god_objects(findings)

        assert len(god_objects) == 0

    def test_testing_gap_detection(self):
        """Test Testing Gap detection with critical functions uncovered."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'test_coverage_scanner': {
                'uncovered_modules': [{
                    'module': '/home/kloros/src/auth.py',
                    'coverage_percent': 15,
                    'severity': 'critical',
                    'uncovered_critical': [
                        {'function': 'delete_user', 'risk': 'high'},
                        {'function': 'validate_token', 'risk': 'high'}
                    ]
                }]
            }
        }

        testing_gaps = scanner._detect_testing_gaps(findings)

        assert len(testing_gaps) == 1
        assert testing_gaps[0]['smell_type'] == 'testing_gap'
        assert testing_gaps[0]['component'] == '/home/kloros/src/auth.py'
        assert testing_gaps[0]['severity'] == 'error'
        assert len(testing_gaps[0]['evidence']['uncovered_critical_functions']) == 2

    def test_testing_gap_not_detected_high_coverage(self):
        """Test Testing Gap not detected when coverage is adequate."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'test_coverage_scanner': {
                'uncovered_modules': [{
                    'module': '/home/kloros/src/auth.py',
                    'coverage_percent': 75,
                    'severity': 'info',
                    'uncovered_critical': [
                        {'function': 'delete_user', 'risk': 'high'}
                    ]
                }]
            }
        }

        testing_gaps = scanner._detect_testing_gaps(findings)

        assert len(testing_gaps) == 0

    def test_bottleneck_cluster_detection(self):
        """Test Bottleneck Cluster detection with multiple performance issues."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'performance_profiler_scanner': {
                'slow_components': [{
                    'component': 'klr-introspection',
                    'operation': 'scan_code_quality',
                    'avg_duration_ms': 2500,
                    'severity': 'error'
                }],
                'memory_leaks': [{
                    'component': 'klr-introspection',
                    'growth_rate_mb_per_hour': 75,
                    'severity': 'critical'
                }]
            }
        }

        bottleneck_clusters = scanner._detect_bottleneck_clusters(findings)

        assert len(bottleneck_clusters) == 1
        assert bottleneck_clusters[0]['smell_type'] == 'bottleneck_cluster'
        assert bottleneck_clusters[0]['component'] == 'klr-introspection'
        assert bottleneck_clusters[0]['severity'] == 'error'
        assert bottleneck_clusters[0]['evidence']['issue_count'] == 2

    def test_bottleneck_cluster_not_detected_single_issue(self):
        """Test Bottleneck Cluster not detected with only one performance issue."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'performance_profiler_scanner': {
                'slow_components': [{
                    'component': 'klr-observer',
                    'operation': 'investigate',
                    'avg_duration_ms': 3000,
                    'severity': 'error'
                }]
            }
        }

        bottleneck_clusters = scanner._detect_bottleneck_clusters(findings)

        assert len(bottleneck_clusters) == 0

    def test_smell_detection_feature_flag_disabled(self):
        """Test that smell detection is skipped when feature flag is disabled."""
        scanner = CrossSystemPatternScanner()
        scanner.detect_smells_enabled = False

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [{
                    'module': '/home/kloros/src/god.py',
                    'complexity': 25,
                    'severity': 'critical'
                }]
            }
        }

        result = scanner.scan_patterns()

        assert result['architectural_smells'] == []
        assert result['scan_metadata']['smells_enabled'] is False


class TestDataCollection:
    """Test data collection and fallback logic."""

    def test_collect_findings_all_scanners_succeed(self):
        """Test data collection when all scanners succeed."""
        scanner = CrossSystemPatternScanner()

        if not scanner.available:
            pytest.skip("Scanner not available")

        findings = scanner._collect_recent_findings(30)

        assert isinstance(findings, dict)
        assert len(findings) > 0

    def test_collect_findings_partial_scanner_failure(self):
        """Test that collection continues with partial scanner failures."""
        scanner = CrossSystemPatternScanner()

        mock_failing_scanner = Mock()
        mock_failing_scanner.get_metadata.side_effect = Exception("Scanner error")

        mock_working_scanner = Mock()
        mock_working_scanner.get_metadata.return_value = Mock(name='working_scanner')

        scanner.other_scanners = [mock_failing_scanner, mock_working_scanner]

        findings = scanner._collect_recent_findings(30)

        assert isinstance(findings, dict)

    def test_call_scanner_directly_code_quality(self):
        """Test direct scanner call for code quality scanner."""
        scanner = CrossSystemPatternScanner()

        mock_scanner = Mock()
        mock_scanner.scan_code_quality.return_value = {'high_complexity_modules': []}

        result = scanner._call_scanner_directly(mock_scanner, 'code_quality_scanner')

        assert result == {'high_complexity_modules': []}
        mock_scanner.scan_code_quality.assert_called_once()

    def test_call_scanner_directly_test_coverage(self):
        """Test direct scanner call for test coverage scanner."""
        scanner = CrossSystemPatternScanner()

        mock_scanner = Mock()
        mock_scanner.scan_test_coverage.return_value = {'uncovered_modules': []}

        result = scanner._call_scanner_directly(mock_scanner, 'test_coverage_scanner')

        assert result == {'uncovered_modules': []}
        mock_scanner.scan_test_coverage.assert_called_once()

    def test_call_scanner_directly_performance(self):
        """Test direct scanner call for performance profiler."""
        scanner = CrossSystemPatternScanner()

        mock_scanner = Mock()
        mock_scanner.scan_performance_profile.return_value = {'slow_components': []}

        result = scanner._call_scanner_directly(mock_scanner, 'performance_profiler_scanner')

        assert result == {'slow_components': []}
        mock_scanner.scan_performance_profile.assert_called_once()

    def test_call_scanner_directly_unknown_scanner(self):
        """Test direct scanner call with unknown scanner type."""
        scanner = CrossSystemPatternScanner()

        mock_scanner = Mock()

        result = scanner._call_scanner_directly(mock_scanner, 'unknown_scanner_type')

        assert result == {}

    def test_call_scanner_directly_exception_handling(self):
        """Test exception handling in direct scanner call."""
        scanner = CrossSystemPatternScanner()

        mock_scanner = Mock()
        mock_scanner.scan_code_quality.side_effect = Exception("Scanner crashed")

        result = scanner._call_scanner_directly(mock_scanner, 'code_quality_scanner')

        assert result == {}

    def test_query_stored_findings_not_implemented(self):
        """Test that stored findings query returns None (not yet implemented)."""
        scanner = CrossSystemPatternScanner()

        result = scanner._query_stored_findings('test_scanner', 30)

        assert result is None


class TestScanPatternsMethod:
    """Test main scan_patterns method."""

    def test_scan_patterns_returns_correct_structure(self):
        """Test that scan_patterns returns correct data structure."""
        scanner = CrossSystemPatternScanner()

        if not scanner.available:
            pytest.skip("Scanner not available")

        result = scanner.scan_patterns(lookback_minutes=30)

        assert 'co_occurrences' in result
        assert 'architectural_smells' in result
        assert 'scan_metadata' in result

        metadata = result['scan_metadata']
        assert 'timestamp' in metadata
        assert 'lookback_minutes' in metadata
        assert 'scanners_checked' in metadata
        assert 'smells_enabled' in metadata

    def test_scan_patterns_caching(self):
        """Test that scan_patterns caches results within 30-minute window."""
        scanner = CrossSystemPatternScanner()

        if not scanner.available:
            pytest.skip("Scanner not available")

        result1 = scanner.scan_patterns(lookback_minutes=30)
        result2 = scanner.scan_patterns(lookback_minutes=30)

        assert result1['scan_metadata']['timestamp'] == result2['scan_metadata']['timestamp']

    def test_scan_patterns_empty_when_unavailable(self):
        """Test that scan_patterns returns empty results when unavailable."""
        scanner = CrossSystemPatternScanner()
        scanner.available = False

        result = scanner.scan_patterns(lookback_minutes=30)

        assert result['co_occurrences'] == []
        assert result['architectural_smells'] == []
        assert result['scan_metadata']['scanners_checked'] == 0


class TestScanMethod:
    """Test daemon-compatible scan() method."""

    def test_scan_returns_empty_list(self):
        """Test that scan() returns empty list (as per design spec)."""
        scanner = CrossSystemPatternScanner()

        result = scanner.scan()

        assert result == []
        assert isinstance(result, list)


class TestFormatFindings:
    """Test findings formatting."""

    def test_format_findings_with_co_occurrences(self):
        """Test formatting report with co-occurrence findings."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'co_occurrences': [{
                'component': '/home/kloros/src/test.py',
                'issues': [
                    {'type': 'high_complexity', 'severity': 'critical', 'value': 'CC=25'},
                    {'type': 'low_coverage', 'severity': 'error', 'value': '15%'}
                ],
                'issue_count': 2,
                'severity_score': 150,
                'pattern_type': 'quality_testing_gap'
            }],
            'architectural_smells': [],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_minutes': 30,
                'scanners_checked': 7,
                'scanners_succeeded': 7,
                'smells_enabled': False
            }
        }

        report = scanner.format_findings(findings)

        assert 'CO-OCCURRENCE PATTERNS' in report
        assert 'test.py' in report
        assert 'quality_testing_gap' in report
        assert 'High Severity' in report

    def test_format_findings_with_architectural_smells(self):
        """Test formatting report with architectural smells."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'co_occurrences': [],
            'architectural_smells': [{
                'smell_type': 'god_object',
                'component': '/home/kloros/src/god.py',
                'evidence': {
                    'cyclomatic_complexity': 25,
                    'lines_of_code': 782,
                    'maintainability_index': 28
                },
                'severity': 'critical'
            }],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_minutes': 30,
                'scanners_checked': 7,
                'scanners_succeeded': 7,
                'smells_enabled': True
            }
        }

        report = scanner.format_findings(findings)

        assert 'ARCHITECTURAL SMELLS' in report
        assert 'God Objects' in report
        assert 'god.py' in report
        assert 'CC=25' in report

    def test_format_findings_empty(self):
        """Test formatting report with no findings."""
        scanner = CrossSystemPatternScanner()

        report = scanner.format_findings({})

        assert 'No cross-system patterns detected' in report

    def test_format_findings_includes_metadata(self):
        """Test that formatted report includes scan metadata."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'co_occurrences': [],
            'architectural_smells': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T10:00:00',
                'lookback_minutes': 45,
                'scanners_checked': 9,
                'scanners_succeeded': 8,
                'smells_enabled': True
            }
        }

        report = scanner.format_findings(findings)

        assert 'Lookback: 45 minutes' in report
        assert '8/9 succeeded' in report
        assert 'ENABLED' in report


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_initialization_without_dependencies(self):
        """Test graceful degradation when dependencies missing."""
        with patch('kloros_memory.storage.MemoryStore',
                   side_effect=ImportError):
            scanner = CrossSystemPatternScanner()

            assert scanner.available is False
            result = scanner.scan_patterns()
            assert result['co_occurrences'] == []

    def test_partial_scanner_initialization_failure(self):
        """Test handling when some scanners fail to initialize."""
        scanner = CrossSystemPatternScanner()

        if scanner.available and scanner.other_scanners:
            assert len(scanner.other_scanners) >= 3

    def test_empty_scanner_findings(self):
        """Test handling of empty findings from scanners."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {},
            'test_coverage_scanner': {},
            'performance_profiler_scanner': {}
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert co_occurrences == []

    def test_malformed_scanner_findings(self):
        """Test handling of malformed findings from scanners."""
        scanner = CrossSystemPatternScanner()

        findings = {
            'code_quality_scanner': {
                'high_complexity_modules': [
                    {'module': '/test.py'}
                ]
            }
        }

        co_occurrences = scanner._detect_co_occurrences(findings)

        assert isinstance(co_occurrences, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
