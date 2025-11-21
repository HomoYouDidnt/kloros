#!/usr/bin/env python3
"""
Test Coverage Scanner

Analyzes test coverage and test quality metrics.
"""

import logging
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class TestCoverageScanner:
    """Analyzes test coverage using coverage.py."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.storage import MemoryStore

            self.store = MemoryStore()
            self.available = True
            logger.info("[test_coverage] Memory system available")

            self.coverage_available = self._check_coverage()
            self.pytest_available = self._check_pytest()

            if not self.coverage_available or not self.pytest_available:
                logger.warning(
                    f"[test_coverage] Tools availability: "
                    f"coverage={self.coverage_available}, pytest={self.pytest_available}"
                )
                self.available = False

        except Exception as e:
            logger.warning(f"[test_coverage] Initialization failed: {e}")
            self.available = False

    def _check_coverage(self) -> bool:
        """Check if coverage.py is available."""
        try:
            import coverage
            return True
        except ImportError:
            logger.warning("[test_coverage] coverage.py not available")
            return False

    def _check_pytest(self) -> bool:
        """Check if pytest is available."""
        try:
            result = subprocess.run(
                ['python3', '-m', 'pytest', '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"[test_coverage] pytest not available: {e}")
            return False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="test_coverage_scanner",
            description="Analyzes test coverage and test quality metrics",
            interval_seconds=300,
            priority=2
        )

    def scan_test_coverage(
        self,
        threshold: float = 80.0,
        target_path: Optional[str] = None
    ) -> Dict:
        """Scan test coverage across codebase."""
        if not self.available:
            logger.warning("[test_coverage] Scanner not available")
            return {}

        if target_path is None:
            target_path = '/home/kloros/src/kloros'

        findings = {
            'coverage_summary': {},
            'uncovered_modules': [],
            'test_patterns': [],
            'failing_tests': [],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'target_path': target_path,
                'threshold': threshold
            }
        }

        coverage_data = self._run_coverage_analysis(target_path)
        if coverage_data:
            findings['coverage_summary'] = coverage_data.get('summary', {})

            for module_path, module_data in coverage_data.get('modules', {}).items():
                coverage_percent = module_data.get('percent_covered', 0.0)

                if coverage_percent < threshold:
                    module_info = {
                        'module': module_path,
                        'coverage_percent': round(coverage_percent, 2),
                        'lines_total': module_data.get('num_statements', 0),
                        'lines_covered': module_data.get('covered_lines', 0),
                        'lines_missing': module_data.get('missing_lines', 0),
                        'severity': self._classify_coverage_severity(coverage_percent)
                    }

                    uncovered_critical = self._identify_critical_functions(
                        module_path,
                        module_data.get('missing_line_numbers', [])
                    )
                    if uncovered_critical:
                        module_info['uncovered_critical'] = uncovered_critical

                    findings['uncovered_modules'].append(module_info)

        test_failures = self._query_test_failures()
        if test_failures:
            findings['failing_tests'] = test_failures

        test_patterns = self._analyze_test_patterns()
        if test_patterns:
            findings['test_patterns'] = test_patterns

        findings['uncovered_modules'].sort(
            key=lambda x: x['coverage_percent']
        )

        return findings

    def _run_coverage_analysis(self, target_path: str) -> Dict:
        """Run coverage.py analysis on target path."""
        try:
            import coverage

            cov = coverage.Coverage(
                data_file=None,
                branch=True,
                source=[target_path]
            )

            cov.start()

            test_dir = '/home/kloros/tests'
            if Path(test_dir).exists():
                result = subprocess.run(
                    [
                        'python3', '-m', 'pytest',
                        test_dir,
                        '--quiet',
                        '--tb=no',
                        '--no-header',
                        '-x'
                    ],
                    capture_output=True,
                    timeout=60,
                    cwd='/home/kloros'
                )

            cov.stop()
            cov.save()

            coverage_data = {
                'summary': {
                    'total_statements': 0,
                    'total_covered': 0,
                    'percent_covered': 0.0
                },
                'modules': {}
            }

            total_statements = 0
            total_covered = 0

            for filename in cov.get_data().measured_files():
                if target_path in filename and '__pycache__' not in filename:
                    analysis = cov.analysis2(filename)

                    num_statements = len(analysis[1])
                    num_covered = len(analysis[2])
                    missing_lines = list(analysis[3])

                    if num_statements > 0:
                        percent_covered = (num_covered / num_statements) * 100

                        coverage_data['modules'][filename] = {
                            'num_statements': num_statements,
                            'covered_lines': num_covered,
                            'missing_lines': len(missing_lines),
                            'percent_covered': percent_covered,
                            'missing_line_numbers': missing_lines
                        }

                        total_statements += num_statements
                        total_covered += num_covered

            if total_statements > 0:
                coverage_data['summary'] = {
                    'total_statements': total_statements,
                    'total_covered': total_covered,
                    'percent_covered': (total_covered / total_statements) * 100
                }

            return coverage_data

        except subprocess.TimeoutExpired:
            logger.warning("[test_coverage] Coverage analysis timeout")
            return {}
        except Exception as e:
            logger.debug(f"[test_coverage] Coverage analysis failed: {e}")
            return {}

    def _identify_critical_functions(
        self,
        module_path: str,
        missing_lines: List[int]
    ) -> List[Dict]:
        """Identify critical functions that are not covered."""
        critical_functions = []

        try:
            if not Path(module_path).exists():
                return critical_functions

            with open(module_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            import ast

            try:
                tree = ast.parse(''.join(lines), filename=module_path)
            except SyntaxError:
                return critical_functions

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_start = node.lineno
                    func_end = node.end_lineno if hasattr(node, 'end_lineno') else func_start

                    uncovered_in_func = [
                        line for line in missing_lines
                        if func_start <= line <= func_end
                    ]

                    if uncovered_in_func:
                        is_critical = (
                            node.name.startswith('_') is False or
                            'init' in node.name or
                            'error' in node.name.lower() or
                            'critical' in node.name.lower() or
                            'save' in node.name.lower() or
                            'load' in node.name.lower() or
                            'delete' in node.name.lower()
                        )

                        if is_critical:
                            risk_level = self._assess_function_risk(
                                node.name,
                                len(uncovered_in_func),
                                func_end - func_start
                            )

                            critical_functions.append({
                                'function': node.name,
                                'lines': uncovered_in_func[:10],
                                'uncovered_count': len(uncovered_in_func),
                                'risk': risk_level
                            })

            return critical_functions

        except Exception as e:
            logger.debug(f"[test_coverage] Error identifying critical functions in {module_path}: {e}")
            return critical_functions

    def _assess_function_risk(
        self,
        func_name: str,
        uncovered_count: int,
        func_length: int
    ) -> str:
        """Assess risk level of uncovered function."""
        high_risk_patterns = [
            'delete', 'remove', 'drop', 'destroy',
            'save', 'write', 'update', 'commit',
            'auth', 'login', 'permission', 'access',
            'validate', 'verify', 'check'
        ]

        is_high_risk = any(pattern in func_name.lower() for pattern in high_risk_patterns)

        coverage_ratio = uncovered_count / max(func_length, 1)

        if is_high_risk and coverage_ratio > 0.5:
            return 'high'
        elif is_high_risk or coverage_ratio > 0.7:
            return 'medium'
        else:
            return 'low'

    def _classify_coverage_severity(self, coverage_percent: float) -> str:
        """Classify coverage severity based on percentage."""
        if coverage_percent < 30:
            return 'critical'
        elif coverage_percent < 50:
            return 'error'
        elif coverage_percent < 70:
            return 'warning'
        else:
            return 'info'

    def _query_test_failures(self) -> List[Dict]:
        """Query memory for recent test failure patterns."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)

            conn = self.store._get_connection()
            cursor = conn.execute("""
                SELECT content, metadata, timestamp
                FROM events
                WHERE event_type = 'error'
                AND (content LIKE '%test%' OR content LIKE '%pytest%')
                AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 50
            """, (cutoff_time.isoformat(),))

            events = cursor.fetchall()
            conn.close()

            failures = []
            seen_signatures = set()

            for content, metadata_json, timestamp in events:
                metadata = json.loads(metadata_json) if metadata_json else {}

                test_name = self._extract_test_name(content)
                if test_name:
                    signature = test_name

                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        failures.append({
                            'test_name': test_name,
                            'timestamp': timestamp,
                            'error_message': content[:200],
                            'metadata': metadata
                        })

            return failures[:10]

        except Exception as e:
            logger.debug(f"[test_coverage] Error querying test failures: {e}")
            return []

    def _extract_test_name(self, error_message: str) -> Optional[str]:
        """Extract test name from error message."""
        import re

        patterns = [
            r'test_\w+',
            r'Test\w+',
            r'tests/[\w/]+\.py::[\w]+',
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message)
            if match:
                return match.group(0)

        return None

    def _analyze_test_patterns(self) -> List[Dict]:
        """Analyze test execution patterns from memory."""
        patterns = []

        try:
            test_dir = Path('/home/kloros/tests')
            if not test_dir.exists():
                return patterns

            test_files = list(test_dir.rglob('test_*.py'))

            patterns.append({
                'pattern': 'test_file_count',
                'value': len(test_files),
                'description': f'Total test files in repository'
            })

            total_test_functions = 0
            for test_file in test_files[:20]:
                try:
                    with open(test_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    import re
                    test_funcs = re.findall(r'def (test_\w+)', content)
                    total_test_functions += len(test_funcs)
                except Exception:
                    continue

            if total_test_functions > 0:
                patterns.append({
                    'pattern': 'test_function_count',
                    'value': total_test_functions,
                    'description': f'Total test functions detected'
                })

            return patterns

        except Exception as e:
            logger.debug(f"[test_coverage] Error analyzing test patterns: {e}")
            return patterns

    def format_findings(self, findings: Dict) -> str:
        """Format test coverage findings as human-readable report."""
        if not findings:
            return "No test coverage issues detected"

        report = []

        coverage_summary = findings.get('coverage_summary', {})
        if coverage_summary:
            total_coverage = coverage_summary.get('percent_covered', 0.0)
            report.append(f"OVERALL COVERAGE: {total_coverage:.1f}%")
            report.append(
                f"  Statements: {coverage_summary.get('total_covered', 0)} / "
                f"{coverage_summary.get('total_statements', 0)}"
            )
            report.append("")

        uncovered = findings.get('uncovered_modules', [])
        if uncovered:
            report.append(f"UNCOVERED MODULES ({len(uncovered)} modules)")

            critical = [m for m in uncovered if m['severity'] == 'critical']
            if critical:
                report.append(f"\n  Critical (< 30%): {len(critical)} modules")
                for module in critical[:3]:
                    report.append(
                        f"    - {Path(module['module']).name}: "
                        f"{module['coverage_percent']:.1f}% "
                        f"({module['lines_covered']}/{module['lines_total']} lines)"
                    )

                    if 'uncovered_critical' in module:
                        for func in module['uncovered_critical'][:2]:
                            report.append(
                                f"      * {func['function']}: "
                                f"{func['uncovered_count']} uncovered lines (risk: {func['risk']})"
                            )

            errors = [m for m in uncovered if m['severity'] == 'error']
            if errors:
                report.append(f"\n  Low Coverage (< 50%): {len(errors)} modules")
                for module in errors[:3]:
                    report.append(
                        f"    - {Path(module['module']).name}: "
                        f"{module['coverage_percent']:.1f}%"
                    )

        failing_tests = findings.get('failing_tests', [])
        if failing_tests:
            report.append(f"\nRECENT TEST FAILURES ({len(failing_tests)} detected)")
            for test in failing_tests[:5]:
                report.append(f"  - {test['test_name']}")
                report.append(f"    Time: {test['timestamp']}")
                report.append(f"    Error: {test['error_message'][:100]}...")

        test_patterns = findings.get('test_patterns', [])
        if test_patterns:
            report.append(f"\nTEST PATTERNS")
            for pattern in test_patterns:
                report.append(
                    f"  - {pattern['description']}: {pattern['value']}"
                )

        if not report:
            return "No test coverage issues detected"

        scan_meta = findings.get('scan_metadata', {})
        header = [
            "="*60,
            "TEST COVERAGE SCAN REPORT",
            f"Timestamp: {scan_meta.get('timestamp', 'N/A')}",
            f"Target path: {scan_meta.get('target_path', 'N/A')}",
            f"Threshold: {scan_meta.get('threshold', 80.0)}%",
            "="*60
        ]

        return '\n'.join(header + [''] + report)


def scan_test_coverage_standalone(
    threshold: float = 80.0,
    target_path: Optional[str] = None
) -> Tuple[Dict, str]:
    """CLI entry point: Scan test coverage."""
    scanner = TestCoverageScanner()
    findings = scanner.scan_test_coverage(threshold, target_path)
    report = scanner.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_test_coverage_standalone(
        threshold=70.0,
        target_path='/home/kloros/src/kloros/introspection/scanners'
    )

    print(report)

    if findings:
        print("\n" + "="*60)
        print("DETAILED FINDINGS SUMMARY")
        print("="*60)
        print(f"Uncovered modules: {len(findings.get('uncovered_modules', []))}")
        print(f"Recent test failures: {len(findings.get('failing_tests', []))}")
        print(f"Test patterns: {len(findings.get('test_patterns', []))}")
