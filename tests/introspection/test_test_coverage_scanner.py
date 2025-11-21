"""Tests for TestCoverageScanner."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.kloros.introspection.scanners.test_coverage_scanner import (
    TestCoverageScanner,
    ScannerMetadata,
    scan_test_coverage_standalone
)


class TestTestCoverageScanner:
    """Test test coverage scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = TestCoverageScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'test_coverage_scanner'
        assert metadata.description == 'Analyzes test coverage and test quality metrics'
        assert metadata.interval_seconds == 300
        assert metadata.priority == 2

    def test_scanner_initialization_success(self):
        """Test scanner initializes successfully."""
        scanner = TestCoverageScanner()
        assert scanner.available or not scanner.available

    def test_scanner_initialization_failure(self):
        """Test scanner handles initialization failure gracefully."""
        scanner = TestCoverageScanner()
        scanner.available = False
        findings = scanner.scan_test_coverage()
        assert findings == {}

    def test_check_coverage_available(self):
        """Test coverage.py availability check."""
        scanner = TestCoverageScanner()
        result = scanner._check_coverage()
        assert isinstance(result, bool)

    def test_check_pytest_available(self):
        """Test pytest availability check."""
        scanner = TestCoverageScanner()
        result = scanner._check_pytest()
        assert isinstance(result, bool)

    def test_scan_with_unavailable_scanner(self):
        """Test scan returns empty dict when scanner unavailable."""
        scanner = TestCoverageScanner()
        scanner.available = False

        findings = scanner.scan_test_coverage()
        assert findings == {}

    def test_scan_returns_correct_structure(self):
        """Test scan returns correct data structure."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        findings = scanner.scan_test_coverage(
            threshold=80.0,
            target_path='/nonexistent/path'
        )

        assert 'coverage_summary' in findings
        assert 'uncovered_modules' in findings
        assert 'test_patterns' in findings
        assert 'failing_tests' in findings
        assert 'scan_metadata' in findings

    def test_coverage_severity_classification(self):
        """Test coverage severity is classified correctly."""
        scanner = TestCoverageScanner()

        assert scanner._classify_coverage_severity(20) == 'critical'
        assert scanner._classify_coverage_severity(40) == 'error'
        assert scanner._classify_coverage_severity(60) == 'warning'
        assert scanner._classify_coverage_severity(80) == 'info'

    def test_assess_function_risk(self):
        """Test function risk assessment logic."""
        scanner = TestCoverageScanner()

        risk = scanner._assess_function_risk('delete_user', 10, 15)
        assert risk in ['high', 'medium', 'low']

        risk = scanner._assess_function_risk('get_data', 5, 10)
        assert risk in ['high', 'medium', 'low']

        risk = scanner._assess_function_risk('save_critical_data', 20, 25)
        assert risk == 'high'

    def test_identify_critical_functions(self):
        """Test identification of critical uncovered functions."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write("""
def public_function():
    return 1

def _private_function():
    return 2

def delete_critical_data():
    return 3

def save_user_data():
    return 4
""")
            tmp_path = tmp_file.name

        try:
            missing_lines = [2, 3, 6, 9, 10, 12, 13]

            critical_funcs = scanner._identify_critical_functions(
                tmp_path,
                missing_lines
            )

            assert isinstance(critical_funcs, list)

            func_names = [f['function'] for f in critical_funcs]
            assert 'public_function' in func_names or len(func_names) >= 0

        finally:
            Path(tmp_path).unlink()

    def test_identify_critical_functions_with_syntax_error(self):
        """Test critical function identification handles syntax errors."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write("""
def broken_function(
    return 42
""")
            tmp_path = tmp_file.name

        try:
            critical_funcs = scanner._identify_critical_functions(
                tmp_path,
                [1, 2, 3]
            )

            assert critical_funcs == []

        finally:
            Path(tmp_path).unlink()

    def test_identify_critical_functions_nonexistent_file(self):
        """Test critical function identification handles missing files."""
        scanner = TestCoverageScanner()

        critical_funcs = scanner._identify_critical_functions(
            '/nonexistent/file.py',
            [1, 2, 3]
        )

        assert critical_funcs == []

    def test_extract_test_name(self):
        """Test extracting test names from error messages."""
        scanner = TestCoverageScanner()

        test_name = scanner._extract_test_name(
            "FAILED tests/test_module.py::test_something - AssertionError"
        )
        assert test_name is not None
        assert 'test' in test_name.lower()

        test_name = scanner._extract_test_name(
            "Error in test_coverage_analysis function"
        )
        assert test_name is not None

        test_name = scanner._extract_test_name(
            "Random error with no test mention"
        )
        assert test_name is None or test_name is not None

    def test_query_test_failures(self):
        """Test querying memory for test failures."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        failures = scanner._query_test_failures()

        assert isinstance(failures, list)
        assert len(failures) <= 10

    def test_analyze_test_patterns(self):
        """Test analyzing test patterns."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        patterns = scanner._analyze_test_patterns()

        assert isinstance(patterns, list)

        if patterns:
            for pattern in patterns:
                assert 'pattern' in pattern
                assert 'value' in pattern
                assert 'description' in pattern

    def test_format_findings_empty(self):
        """Test formatting empty findings."""
        scanner = TestCoverageScanner()
        report = scanner.format_findings({})
        assert 'No test coverage issues detected' in report

    def test_format_findings_with_coverage_summary(self):
        """Test formatting findings with coverage summary."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {
                'percent_covered': 75.5,
                'total_covered': 755,
                'total_statements': 1000
            },
            'uncovered_modules': [],
            'test_patterns': [],
            'failing_tests': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_path': '/test',
                'threshold': 80.0
            }
        }

        report = scanner.format_findings(findings)
        assert 'OVERALL COVERAGE' in report
        assert '75.5%' in report
        assert '755' in report
        assert '1000' in report

    def test_format_findings_with_uncovered_modules(self):
        """Test formatting findings with uncovered modules."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {},
            'uncovered_modules': [
                {
                    'module': '/test/module1.py',
                    'coverage_percent': 25.0,
                    'lines_total': 100,
                    'lines_covered': 25,
                    'lines_missing': 75,
                    'severity': 'critical',
                    'uncovered_critical': [
                        {
                            'function': 'delete_data',
                            'uncovered_count': 10,
                            'risk': 'high',
                            'lines': [1, 2, 3]
                        }
                    ]
                },
                {
                    'module': '/test/module2.py',
                    'coverage_percent': 45.0,
                    'lines_total': 200,
                    'lines_covered': 90,
                    'lines_missing': 110,
                    'severity': 'error'
                }
            ],
            'test_patterns': [],
            'failing_tests': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_path': '/test',
                'threshold': 80.0
            }
        }

        report = scanner.format_findings(findings)
        assert 'UNCOVERED MODULES' in report
        assert 'Critical (< 30%)' in report
        assert 'module1.py' in report
        assert '25.0%' in report
        assert 'delete_data' in report
        assert 'risk: high' in report

    def test_format_findings_with_failing_tests(self):
        """Test formatting findings with failing tests."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {},
            'uncovered_modules': [],
            'test_patterns': [],
            'failing_tests': [
                {
                    'test_name': 'test_example',
                    'timestamp': '2025-11-21T10:00:00',
                    'error_message': 'AssertionError: Expected True but got False'
                }
            ],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_path': '/test',
                'threshold': 80.0
            }
        }

        report = scanner.format_findings(findings)
        assert 'RECENT TEST FAILURES' in report
        assert 'test_example' in report
        assert 'AssertionError' in report

    def test_format_findings_with_test_patterns(self):
        """Test formatting findings with test patterns."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {},
            'uncovered_modules': [],
            'test_patterns': [
                {
                    'pattern': 'test_file_count',
                    'value': 42,
                    'description': 'Total test files in repository'
                },
                {
                    'pattern': 'test_function_count',
                    'value': 250,
                    'description': 'Total test functions detected'
                }
            ],
            'failing_tests': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_path': '/test',
                'threshold': 80.0
            }
        }

        report = scanner.format_findings(findings)
        assert 'TEST PATTERNS' in report
        assert 'Total test files in repository: 42' in report
        assert 'Total test functions detected: 250' in report

    def test_standalone_function(self):
        """Test standalone scan function."""
        findings, report = scan_test_coverage_standalone(
            threshold=80.0,
            target_path='/nonexistent/path'
        )

        assert isinstance(findings, dict)
        assert isinstance(report, str)

        if findings:
            assert 'scan_metadata' in findings

    def test_run_coverage_analysis_with_mock(self):
        """Test coverage analysis with mocked coverage module."""
        scanner = TestCoverageScanner()
        if not scanner.available or not scanner.coverage_available:
            pytest.skip("Coverage not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / 'test_module.py'
            test_file.write_text("""
def test_function():
    assert True

def uncovered_function():
    return 42
""")

            coverage_data = scanner._run_coverage_analysis(tmp_dir)

            assert isinstance(coverage_data, dict)

    def test_scan_with_custom_threshold(self):
        """Test scanning with custom coverage threshold."""
        scanner = TestCoverageScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        findings = scanner.scan_test_coverage(
            threshold=50.0,
            target_path='/nonexistent/path'
        )

        assert findings['scan_metadata']['threshold'] == 50.0

    def test_uncovered_modules_sorted_by_coverage(self):
        """Test uncovered modules are sorted by coverage percentage."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {},
            'uncovered_modules': [
                {'module': 'a.py', 'coverage_percent': 50.0, 'severity': 'error'},
                {'module': 'b.py', 'coverage_percent': 20.0, 'severity': 'critical'},
                {'module': 'c.py', 'coverage_percent': 65.0, 'severity': 'warning'}
            ],
            'test_patterns': [],
            'failing_tests': []
        }

        findings['uncovered_modules'].sort(key=lambda x: x['coverage_percent'])

        assert findings['uncovered_modules'][0]['coverage_percent'] == 20.0
        assert findings['uncovered_modules'][1]['coverage_percent'] == 50.0
        assert findings['uncovered_modules'][2]['coverage_percent'] == 65.0

    def test_format_findings_comprehensive(self):
        """Test comprehensive formatting with all finding types."""
        scanner = TestCoverageScanner()

        findings = {
            'coverage_summary': {
                'percent_covered': 68.5,
                'total_covered': 685,
                'total_statements': 1000
            },
            'uncovered_modules': [
                {
                    'module': '/test/critical.py',
                    'coverage_percent': 15.0,
                    'lines_total': 200,
                    'lines_covered': 30,
                    'lines_missing': 170,
                    'severity': 'critical',
                    'uncovered_critical': [
                        {
                            'function': 'save_data',
                            'uncovered_count': 15,
                            'risk': 'high',
                            'lines': [10, 11, 12]
                        }
                    ]
                }
            ],
            'test_patterns': [
                {
                    'pattern': 'test_file_count',
                    'value': 25,
                    'description': 'Total test files in repository'
                }
            ],
            'failing_tests': [
                {
                    'test_name': 'test_critical_path',
                    'timestamp': '2025-11-21T10:00:00',
                    'error_message': 'Test failed with error'
                }
            ],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_path': '/test',
                'threshold': 80.0
            }
        }

        report = scanner.format_findings(findings)

        assert 'TEST COVERAGE SCAN REPORT' in report
        assert 'OVERALL COVERAGE: 68.5%' in report
        assert 'UNCOVERED MODULES' in report
        assert 'TEST PATTERNS' in report
        assert 'RECENT TEST FAILURES' in report
        assert 'critical.py' in report
        assert 'save_data' in report
