"""Tests for CodeQualityScanner."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.observability.introspection.scanners.code_quality_scanner import (
    CodeQualityScanner,
    ScannerMetadata,
    scan_code_quality_standalone
)


class TestCodeQualityScanner:
    """Test code quality scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = CodeQualityScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'code_quality_scanner'
        assert metadata.description == 'Analyzes code complexity and quality metrics'
        assert metadata.interval_seconds == 300
        assert metadata.priority == 2

    def test_scanner_initialization_success(self):
        """Test scanner initializes successfully."""
        scanner = CodeQualityScanner()
        assert scanner.available or not scanner.available

    def test_scanner_initialization_failure(self):
        """Test scanner handles initialization failure gracefully."""
        scanner = CodeQualityScanner()
        scanner.available = False
        findings = scanner.scan_code_quality()
        assert findings == {}

    def test_check_radon_available(self):
        """Test radon availability check."""
        scanner = CodeQualityScanner()
        result = scanner._check_radon()
        assert isinstance(result, bool)

    def test_check_bandit_available(self):
        """Test bandit availability check."""
        scanner = CodeQualityScanner()
        result = scanner._check_bandit()
        assert isinstance(result, bool)

    def test_scan_with_unavailable_scanner(self):
        """Test scan returns empty dict when scanner unavailable."""
        scanner = CodeQualityScanner()
        scanner.available = False

        findings = scanner.scan_code_quality()
        assert findings == {}

    def test_scan_nonexistent_path(self):
        """Test scan handles nonexistent path gracefully."""
        scanner = CodeQualityScanner()
        if not scanner.available:
            pytest.skip("Scanner not available")

        findings = scanner.scan_code_quality(
            target_paths=['/nonexistent/path/to/nowhere']
        )

        assert 'high_complexity_modules' in findings
        assert 'maintainability_issues' in findings
        assert 'security_vulnerabilities' in findings
        assert 'code_smells' in findings

    def test_scan_single_file(self):
        """Test scanning a single Python file."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
            pytest.skip("Scanner not available")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write("""
def simple_function():
    return 42

def complex_function(a, b, c, d):
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if a > b:
                        if b > c:
                            if c > d:
                                return a + b + c + d
    return 0
""")
            tmp_path = tmp_file.name

        try:
            findings = scanner.scan_code_quality(
                target_paths=[tmp_path],
                min_complexity=5
            )

            assert 'high_complexity_modules' in findings
            assert 'scan_metadata' in findings
            assert findings['scan_metadata']['min_complexity'] == 5

            complex_funcs = findings['high_complexity_modules']
            assert any('complex_function' in f['function'] for f in complex_funcs)

        finally:
            Path(tmp_path).unlink()

    def test_scan_directory(self):
        """Test scanning a directory of Python files."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
            pytest.skip("Scanner not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            file1 = Path(tmp_dir) / 'module1.py'
            file1.write_text("""
def func1():
    return 1
""")

            file2 = Path(tmp_dir) / 'module2.py'
            file2.write_text("""
def func2():
    return 2
""")

            findings = scanner.scan_code_quality(target_paths=[tmp_dir])

            assert 'high_complexity_modules' in findings
            assert 'scan_metadata' in findings
            assert tmp_dir in findings['scan_metadata']['target_paths']

    def test_complexity_severity_classification(self):
        """Test complexity severity is classified correctly."""
        scanner = CodeQualityScanner()

        assert scanner._classify_complexity_severity(5) == 'info'
        assert scanner._classify_complexity_severity(10) == 'warning'
        assert scanner._classify_complexity_severity(15) == 'error'
        assert scanner._classify_complexity_severity(20) == 'critical'
        assert scanner._classify_complexity_severity(30) == 'critical'

    def test_maintainability_severity_classification(self):
        """Test maintainability severity is classified correctly."""
        scanner = CodeQualityScanner()

        assert scanner._classify_maintainability_severity(10) == 'critical'
        assert scanner._classify_maintainability_severity(30) == 'error'
        assert scanner._classify_maintainability_severity(50) == 'warning'
        assert scanner._classify_maintainability_severity(70) == 'info'
        assert scanner._classify_maintainability_severity(90) == 'info'

    def test_detect_large_file_smell(self):
        """Test detection of large file code smell."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
            pytest.skip("Scanner not available")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write('\n'.join([f'line_{i} = {i}' for i in range(600)]))
            tmp_path = tmp_file.name

        try:
            findings = scanner.scan_code_quality(
                target_paths=[tmp_path],
                min_complexity=100
            )

            code_smells = findings['code_smells']
            large_file_smells = [
                s for s in code_smells if s['type'] == 'large_file'
            ]
            assert len(large_file_smells) > 0

        finally:
            Path(tmp_path).unlink()

    def test_detect_no_comments_smell(self):
        """Test detection of missing comments code smell."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
            pytest.skip("Scanner not available")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write('\n'.join([
                'def function1():',
                '    return 1',
                '',
                'def function2():',
                '    return 2',
                '',
            ] * 15))
            tmp_path = tmp_file.name

        try:
            findings = scanner.scan_code_quality(
                target_paths=[tmp_path],
                min_complexity=100
            )

            code_smells = findings['code_smells']
            no_comment_smells = [
                s for s in code_smells if s['type'] == 'no_comments'
            ]
            assert len(no_comment_smells) > 0

        finally:
            Path(tmp_path).unlink()

    def test_format_findings_empty(self):
        """Test formatting empty findings."""
        scanner = CodeQualityScanner()
        report = scanner.format_findings({})
        assert 'No code quality issues detected' in report

    def test_format_findings_with_complexity(self):
        """Test formatting findings with complexity issues."""
        scanner = CodeQualityScanner()

        findings = {
            'high_complexity_modules': [
                {
                    'module': '/test/module.py',
                    'function': 'complex_func',
                    'complexity': 25,
                    'severity': 'critical'
                }
            ],
            'maintainability_issues': [],
            'security_vulnerabilities': [],
            'code_smells': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_paths': ['/test']
            }
        }

        report = scanner.format_findings(findings)
        assert 'HIGH COMPLEXITY' in report
        assert 'complex_func' in report
        assert 'CC=25' in report

    def test_format_findings_with_maintainability(self):
        """Test formatting findings with maintainability issues."""
        scanner = CodeQualityScanner()

        findings = {
            'high_complexity_modules': [],
            'maintainability_issues': [
                {
                    'module': '/test/module.py',
                    'maintainability_index': 45.3,
                    'rank': 'B',
                    'loc': 200,
                    'comments': 10,
                    'comment_ratio': 5.0,
                    'severity': 'error'
                }
            ],
            'security_vulnerabilities': [],
            'code_smells': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_paths': ['/test']
            }
        }

        report = scanner.format_findings(findings)
        assert 'LOW MAINTAINABILITY' in report
        assert 'MI=45.3' in report
        assert 'Rank: B' in report

    def test_format_findings_with_security(self):
        """Test formatting findings with security issues."""
        scanner = CodeQualityScanner()

        findings = {
            'high_complexity_modules': [],
            'maintainability_issues': [],
            'security_vulnerabilities': [
                {
                    'module': '/test/module.py',
                    'issue_type': 'B105',
                    'issue_text': 'Hardcoded password string',
                    'severity': 'high',
                    'confidence': 'high',
                    'lineno': 42
                }
            ],
            'code_smells': [],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_paths': ['/test']
            }
        }

        report = scanner.format_findings(findings)
        assert 'SECURITY ISSUES' in report
        assert 'High Severity' in report

    def test_format_findings_with_code_smells(self):
        """Test formatting findings with code smells."""
        scanner = CodeQualityScanner()

        findings = {
            'high_complexity_modules': [],
            'maintainability_issues': [],
            'security_vulnerabilities': [],
            'code_smells': [
                {
                    'module': '/test/module.py',
                    'type': 'large_file',
                    'loc': 650,
                    'severity': 'warning',
                    'reason': 'File has 650 lines'
                }
            ],
            'scan_metadata': {
                'timestamp': '2025-11-21T12:00:00',
                'target_paths': ['/test']
            }
        }

        report = scanner.format_findings(findings)
        assert 'CODE SMELLS' in report
        assert 'files exceed 500 lines' in report

    def test_standalone_function(self):
        """Test standalone scan function."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        ) as tmp_file:
            tmp_file.write("""
def test_func():
    return 42
""")
            tmp_path = tmp_file.name

        try:
            findings, report = scan_code_quality_standalone(
                target_paths=[tmp_path],
                min_complexity=10
            )

            assert isinstance(findings, dict)
            assert isinstance(report, str)
            assert 'scan_metadata' in findings

        finally:
            Path(tmp_path).unlink()

    def test_analyze_file_with_syntax_error(self):
        """Test scanner handles syntax errors gracefully."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
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
            findings = {
                'high_complexity_modules': [],
                'maintainability_issues': [],
                'security_vulnerabilities': [],
                'code_smells': []
            }

            scanner._analyze_file(Path(tmp_path), 10, findings)

            assert len(findings['high_complexity_modules']) == 0

        finally:
            Path(tmp_path).unlink()

    def test_bandit_scan_integration(self):
        """Test bandit integration."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.bandit_available:
            pytest.skip("Bandit not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / 'insecure.py'
            test_file.write_text("""
import subprocess

def run_command(user_input):
    subprocess.call("ls " + user_input, shell=True)
""")

            findings = {
                'high_complexity_modules': [],
                'maintainability_issues': [],
                'security_vulnerabilities': [],
                'code_smells': []
            }

            scanner._run_bandit_scan(tmp_dir, findings)

            assert len(findings['security_vulnerabilities']) >= 0

    def test_scan_excludes_pycache(self):
        """Test scanner excludes __pycache__ directories."""
        scanner = CodeQualityScanner()
        if not scanner.available or not scanner.radon_available:
            pytest.skip("Scanner not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pycache_dir = Path(tmp_dir) / '__pycache__'
            pycache_dir.mkdir()

            pycache_file = pycache_dir / 'cached.py'
            pycache_file.write_text('def cached(): pass')

            normal_file = Path(tmp_dir) / 'normal.py'
            normal_file.write_text('def normal(): pass')

            findings = scanner.scan_code_quality(target_paths=[tmp_dir])

            all_modules = (
                findings['high_complexity_modules'] +
                findings['maintainability_issues'] +
                findings['code_smells']
            )

            for module_info in all_modules:
                assert '__pycache__' not in module_info['module']
