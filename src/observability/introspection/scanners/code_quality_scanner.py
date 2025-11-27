#!/usr/bin/env python3
"""
Code Quality Scanner

Analyzes code complexity and quality metrics.
"""

import logging
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, NamedTuple

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class CodeQualityScanner:
    """Analyzes code quality metrics using radon and bandit."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from src.cognition.mind.memory.storage import MemoryStore

            self.store = MemoryStore()
            self.available = True
            logger.info("[code_quality] Memory system available")

            self.radon_available = self._check_radon()
            self.bandit_available = self._check_bandit()

            if not self.radon_available or not self.bandit_available:
                logger.warning(
                    f"[code_quality] Tools availability: "
                    f"radon={self.radon_available}, bandit={self.bandit_available}"
                )
                self.available = False

        except Exception as e:
            logger.warning(f"[code_quality] Initialization failed: {e}")
            self.available = False

    def _check_radon(self) -> bool:
        """Check if radon is available."""
        try:
            import radon
            return True
        except ImportError:
            logger.warning("[code_quality] radon not available")
            return False

    def _check_bandit(self) -> bool:
        """Check if bandit is available."""
        try:
            result = subprocess.run(
                ['python3', '-m', 'bandit', '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"[code_quality] bandit not available: {e}")
            return False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="code_quality_scanner",
            description="Analyzes code complexity and quality metrics",
            interval_seconds=300,
            priority=2
        )

    def scan(self) -> List:
        return []

    def scan_code_quality(
        self,
        target_paths: Optional[List[str]] = None,
        min_complexity: int = 10
    ) -> Dict:
        """Scan codebase for quality metrics."""
        if not self.available:
            logger.warning("[code_quality] Scanner not available")
            return {}

        if target_paths is None:
            target_paths = ['/home/kloros/src/kloros']

        findings = {
            'high_complexity_modules': [],
            'maintainability_issues': [],
            'security_vulnerabilities': [],
            'code_smells': [],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'target_paths': target_paths,
                'min_complexity': min_complexity
            }
        }

        for path_str in target_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"[code_quality] Path does not exist: {path}")
                continue

            if path.is_file() and path.suffix == '.py':
                self._analyze_file(path, min_complexity, findings)
            elif path.is_dir():
                for py_file in path.rglob('*.py'):
                    if '__pycache__' not in str(py_file):
                        self._analyze_file(py_file, min_complexity, findings)

        if self.bandit_available:
            for path_str in target_paths:
                self._run_bandit_scan(path_str, findings)

        return findings

    def _analyze_file(
        self,
        file_path: Path,
        min_complexity: int,
        findings: Dict
    ) -> None:
        """Analyze a single Python file for quality metrics."""
        try:
            from radon.complexity import cc_visit
            from radon.metrics import mi_visit, mi_rank
            from radon.raw import analyze

            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            complexity_blocks = cc_visit(code)

            for block in complexity_blocks:
                if block.complexity >= min_complexity:
                    findings['high_complexity_modules'].append({
                        'module': str(file_path),
                        'function': block.name,
                        'complexity': block.complexity,
                        'lineno': block.lineno,
                        'col_offset': block.col_offset,
                        'type': block.classname if hasattr(block, 'classname') else 'function',
                        'severity': self._classify_complexity_severity(block.complexity)
                    })

            try:
                mi_score = mi_visit(code, multi=True)
                mi_value = mi_score if isinstance(mi_score, (int, float)) else 100
            except Exception as e:
                logger.debug(f"[code_quality] MI calculation failed for {file_path}: {e}")
                mi_value = 100

            raw_metrics = analyze(code)

            if mi_value < 65:
                findings['maintainability_issues'].append({
                    'module': str(file_path),
                    'maintainability_index': round(mi_value, 2),
                    'rank': mi_rank(mi_value),
                    'loc': raw_metrics.loc,
                    'lloc': raw_metrics.lloc,
                    'sloc': raw_metrics.sloc,
                    'comments': raw_metrics.comments,
                    'multi': raw_metrics.multi,
                    'blank': raw_metrics.blank,
                    'comment_ratio': round(
                        raw_metrics.comments / max(raw_metrics.loc, 1) * 100, 2
                    ),
                    'severity': self._classify_maintainability_severity(mi_value)
                })

            if raw_metrics.loc > 500:
                findings['code_smells'].append({
                    'module': str(file_path),
                    'type': 'large_file',
                    'loc': raw_metrics.loc,
                    'severity': 'warning',
                    'reason': f'File has {raw_metrics.loc} lines (recommended max: 500)'
                })

            if raw_metrics.comments == 0 and raw_metrics.loc > 50:
                findings['code_smells'].append({
                    'module': str(file_path),
                    'type': 'no_comments',
                    'loc': raw_metrics.loc,
                    'severity': 'info',
                    'reason': 'File has no comments but is over 50 lines'
                })

        except SyntaxError as e:
            logger.debug(f"[code_quality] Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.debug(f"[code_quality] Error analyzing {file_path}: {e}")

    def _classify_complexity_severity(self, complexity: int) -> str:
        """Classify complexity severity."""
        if complexity >= 20:
            return 'critical'
        elif complexity >= 15:
            return 'error'
        elif complexity >= 10:
            return 'warning'
        else:
            return 'info'

    def _classify_maintainability_severity(self, mi_value: float) -> str:
        """Classify maintainability severity based on MI score."""
        if mi_value < 20:
            return 'critical'
        elif mi_value < 40:
            return 'error'
        elif mi_value < 65:
            return 'warning'
        else:
            return 'info'

    def _run_bandit_scan(self, path: str, findings: Dict) -> None:
        """Run bandit security scanner on path."""
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.json',
                delete=False
            ) as tmp_file:
                tmp_path = tmp_file.name

            result = subprocess.run(
                [
                    'python3', '-m', 'bandit',
                    '-r', path,
                    '-f', 'json',
                    '-o', tmp_path,
                    '--quiet'
                ],
                capture_output=True,
                timeout=60
            )

            if Path(tmp_path).exists():
                with open(tmp_path, 'r') as f:
                    bandit_output = json.load(f)

                for result_item in bandit_output.get('results', []):
                    findings['security_vulnerabilities'].append({
                        'module': result_item['filename'],
                        'issue_type': result_item['test_id'],
                        'issue_text': result_item['issue_text'],
                        'severity': result_item['issue_severity'].lower(),
                        'confidence': result_item['issue_confidence'].lower(),
                        'lineno': result_item['line_number'],
                        'code': result_item.get('code', '').strip(),
                        'more_info': result_item.get('more_info', '')
                    })

                Path(tmp_path).unlink()

        except subprocess.TimeoutExpired:
            logger.warning(f"[code_quality] Bandit scan timeout for {path}")
        except Exception as e:
            logger.debug(f"[code_quality] Bandit scan error for {path}: {e}")

    def format_findings(self, findings: Dict) -> str:
        """Format code quality findings as human-readable report."""
        if not findings:
            return "No code quality issues detected"

        report = []

        high_complexity = findings.get('high_complexity_modules', [])
        if high_complexity:
            report.append(f"HIGH COMPLEXITY ({len(high_complexity)} functions)")

            critical = [f for f in high_complexity if f['severity'] == 'critical']
            if critical:
                report.append(f"\n  Critical (CC >= 20): {len(critical)} functions")
                for func in critical[:3]:
                    report.append(
                        f"    - {func['function']} in {Path(func['module']).name}: "
                        f"CC={func['complexity']}"
                    )

            errors = [f for f in high_complexity if f['severity'] == 'error']
            if errors:
                report.append(f"\n  High (CC >= 15): {len(errors)} functions")
                for func in errors[:3]:
                    report.append(
                        f"    - {func['function']} in {Path(func['module']).name}: "
                        f"CC={func['complexity']}"
                    )

        maintainability = findings.get('maintainability_issues', [])
        if maintainability:
            report.append(f"\nLOW MAINTAINABILITY ({len(maintainability)} modules)")

            for issue in maintainability[:5]:
                report.append(
                    f"  - {Path(issue['module']).name}: "
                    f"MI={issue['maintainability_index']} (Rank: {issue['rank']})"
                )
                report.append(
                    f"    LOC: {issue['loc']}, Comments: {issue['comments']} "
                    f"({issue['comment_ratio']}%)"
                )

        security = findings.get('security_vulnerabilities', [])
        if security:
            report.append(f"\nSECURITY ISSUES ({len(security)} findings)")

            high_severity = [s for s in security if s['severity'] == 'high']
            medium_severity = [s for s in security if s['severity'] == 'medium']

            if high_severity:
                report.append(f"\n  High Severity: {len(high_severity)} issues")
                for vuln in high_severity[:3]:
                    report.append(
                        f"    - {Path(vuln['module']).name}:{vuln['lineno']}: "
                        f"{vuln['issue_text']}"
                    )

            if medium_severity:
                report.append(f"\n  Medium Severity: {len(medium_severity)} issues")

        code_smells = findings.get('code_smells', [])
        if code_smells:
            report.append(f"\nCODE SMELLS ({len(code_smells)} detected)")

            large_files = [s for s in code_smells if s['type'] == 'large_file']
            if large_files:
                report.append(f"  - {len(large_files)} files exceed 500 lines")

        if not report:
            return "No code quality issues detected"

        scan_meta = findings.get('scan_metadata', {})
        header = [
            "="*60,
            "CODE QUALITY SCAN REPORT",
            f"Timestamp: {scan_meta.get('timestamp', 'N/A')}",
            f"Target paths: {', '.join(scan_meta.get('target_paths', []))}",
            "="*60
        ]

        return '\n'.join(header + [''] + report)


def scan_code_quality_standalone(
    target_paths: Optional[List[str]] = None,
    min_complexity: int = 10
) -> Tuple[Dict, str]:
    """CLI entry point: Scan code quality."""
    scanner = CodeQualityScanner()
    findings = scanner.scan_code_quality(target_paths, min_complexity)
    report = scanner.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_code_quality_standalone(
        target_paths=['/home/kloros/src/kloros/introspection/scanners'],
        min_complexity=10
    )

    print(report)

    if findings:
        print("\n" + "="*60)
        print("DETAILED FINDINGS SUMMARY")
        print("="*60)
        print(f"High complexity functions: {len(findings.get('high_complexity_modules', []))}")
        print(f"Maintainability issues: {len(findings.get('maintainability_issues', []))}")
        print(f"Security vulnerabilities: {len(findings.get('security_vulnerabilities', []))}")
        print(f"Code smells: {len(findings.get('code_smells', []))}")
