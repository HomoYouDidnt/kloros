#!/usr/bin/env python3
"""
Cross System Pattern Scanner

Aggregates findings from all introspection scanners to detect:
- Co-occurrence patterns (multiple issues in same component)
- Architectural smells (God Objects, Testing Gaps, Bottleneck Clusters)

Purpose:
Provides holistic system health understanding by synthesizing data from
all Phase 1-3 scanners. Identifies patterns that only emerge when viewing
multiple dimensions of system health together.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, NamedTuple, Set
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class CrossSystemPatternScanner:
    """Detects cross-system patterns by aggregating findings from all scanners."""

    def __init__(self):
        self.detect_smells_enabled = False
        self.available = True
        self.last_scan_time = None
        self.cached_results = None

        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.storage import MemoryStore

            self.store = MemoryStore()

            self._initialize_scanners()

        except Exception as e:
            logger.warning(f"[pattern] Initialization failed: {e}")
            self.available = False
            self.other_scanners = []

    def _initialize_scanners(self):
        """Initialize all Phase 1-3 scanners."""
        try:
            from kloros.introspection.scanners.code_quality_scanner import CodeQualityScanner
            from kloros.introspection.scanners.test_coverage_scanner import TestCoverageScanner
            from kloros.introspection.scanners.performance_profiler_scanner import PerformanceProfilerScanner
            from kloros.introspection.scanners.service_health_correlator import ServiceHealthCorrelator
            from kloros.introspection.scanners.error_frequency_scanner import ErrorFrequencyScanner
            from kloros.introspection.scanners.self_capability_checker import SelfCapabilityChecker
            from kloros.introspection.scanners.unindexed_knowledge_scanner import UnindexedKnowledgeScanner

            self.other_scanners = [
                CodeQualityScanner(),
                TestCoverageScanner(),
                PerformanceProfilerScanner(),
                ServiceHealthCorrelator(),
                ErrorFrequencyScanner(),
                SelfCapabilityChecker(),
                UnindexedKnowledgeScanner(),
            ]

            logger.info(f"[pattern] Initialized {len(self.other_scanners)} scanners")

        except ImportError as e:
            logger.warning(f"[pattern] Failed to import scanners: {e}")
            self.other_scanners = []
            self.available = False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="cross_system_pattern_scanner",
            description="Detects co-occurrence patterns and architectural smells across all scanners",
            interval_seconds=1800,
            priority=1
        )

    def scan(self) -> List:
        """
        Daemon-compatible interface - converts critical findings to CapabilityGap objects.

        Returns empty list for now (as per design spec).
        """
        return []

    def scan_patterns(
        self,
        lookback_minutes: int = 30
    ) -> Dict:
        """
        Analyze cross-system patterns from scanner findings.

        Args:
            lookback_minutes: How far back to analyze (default: 30)

        Returns:
            {
                'co_occurrences': [...],
                'architectural_smells': [...],
                'scan_metadata': {...}
            }
        """
        if not self.available:
            logger.warning("[pattern] Scanner not available")
            return self._empty_results(lookback_minutes)

        now = datetime.now()

        if (self.last_scan_time and
            self.cached_results and
            (now - self.last_scan_time).total_seconds() < 1800):
            logger.debug("[pattern] Returning cached results (within 30-minute window)")
            return self.cached_results

        findings = self._collect_recent_findings(lookback_minutes)

        co_occurrences = self._detect_co_occurrences(findings)

        smells = []
        if self.detect_smells_enabled:
            smells = self._detect_architectural_smells(findings)

        results = {
            'co_occurrences': co_occurrences,
            'architectural_smells': smells,
            'scan_metadata': {
                'timestamp': now.isoformat(),
                'lookback_minutes': lookback_minutes,
                'scanners_checked': len(self.other_scanners),
                'scanners_succeeded': len([f for f in findings.values() if f]),
                'smells_enabled': self.detect_smells_enabled
            }
        }

        self.last_scan_time = now
        self.cached_results = results

        return results

    def _empty_results(self, lookback_minutes: int) -> Dict:
        """Return empty results structure."""
        return {
            'co_occurrences': [],
            'architectural_smells': [],
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_minutes': lookback_minutes,
                'scanners_checked': 0,
                'scanners_succeeded': 0,
                'smells_enabled': self.detect_smells_enabled
            }
        }

    def _collect_recent_findings(self, lookback_minutes: int) -> Dict:
        """
        Collect findings with fallback logic.

        Tries memory.db first (when persistence is added), then falls back
        to calling scanner methods directly.
        """
        findings = {}

        for scanner in self.other_scanners:
            scanner_name = None
            try:
                if hasattr(scanner, 'get_metadata'):
                    scanner_metadata = scanner.get_metadata()
                    scanner_name = scanner_metadata.name
                else:
                    scanner_name = scanner.__class__.__name__.lower()

                stored_findings = self._query_stored_findings(scanner_name, lookback_minutes)

                if stored_findings:
                    findings[scanner_name] = stored_findings
                else:
                    direct_findings = self._call_scanner_directly(scanner, scanner_name)
                    findings[scanner_name] = direct_findings

            except Exception as e:
                if scanner_name:
                    logger.warning(f"[pattern] Failed to collect from {scanner_name}: {e}")
                    findings[scanner_name] = {}
                else:
                    logger.warning(f"[pattern] Failed to collect from unknown scanner: {e}")

        return findings

    def _query_stored_findings(
        self,
        scanner_name: str,
        lookback_minutes: int
    ) -> Optional[Dict]:
        """
        Query memory.db for stored scanner findings.

        Currently returns None (persistence not yet implemented).
        Will be activated when findings persistence is added to memory system.
        """
        return None

    def _call_scanner_directly(self, scanner, scanner_name: str) -> Dict:
        """Call scanner's primary method directly to get findings."""
        try:
            if scanner_name == 'code_quality_scanner':
                return scanner.scan_code_quality()
            elif scanner_name == 'test_coverage_scanner':
                return scanner.scan_test_coverage()
            elif scanner_name == 'performance_profiler_scanner':
                return scanner.scan_performance_profile()
            elif scanner_name == 'service_health_correlator':
                return scanner.scan_service_health()
            elif scanner_name == 'error_frequency_scanner':
                return scanner.scan_error_frequency()
            elif scanner_name == 'self_capability_checker':
                return scanner.scan_capabilities()
            elif scanner_name == 'unindexed_knowledge_scanner':
                return scanner.scan_unindexed_knowledge()
            else:
                logger.debug(f"[pattern] Unknown scanner: {scanner_name}")
                return {}

        except Exception as e:
            logger.debug(f"[pattern] Error calling {scanner_name}: {e}")
            return {}

    def _detect_co_occurrences(self, findings: Dict) -> List[Dict]:
        """
        Detect co-occurrence patterns: multiple issues in same component.

        Algorithm:
        1. Group all findings by component/module path
        2. Count issue types per component
        3. Rank by severity (critical issues weighted higher)
        4. Return components with 2+ issues
        """
        component_issues = defaultdict(list)

        code_quality = findings.get('code_quality_scanner', {})
        if code_quality:
            for complexity in code_quality.get('high_complexity_modules', []):
                module = complexity.get('module', '')
                component_issues[module].append({
                    'type': 'high_complexity',
                    'severity': complexity.get('severity', 'warning'),
                    'value': f"CC={complexity.get('complexity', 0)}",
                    'details': complexity
                })

            for maintainability in code_quality.get('maintainability_issues', []):
                module = maintainability.get('module', '')
                component_issues[module].append({
                    'type': 'low_maintainability',
                    'severity': maintainability.get('severity', 'warning'),
                    'value': f"MI={maintainability.get('maintainability_index', 0)}",
                    'details': maintainability
                })

            for smell in code_quality.get('code_smells', []):
                module = smell.get('module', '')
                component_issues[module].append({
                    'type': 'code_smell',
                    'severity': smell.get('severity', 'info'),
                    'value': smell.get('type', 'unknown'),
                    'details': smell
                })

        test_coverage = findings.get('test_coverage_scanner', {})
        if test_coverage:
            for uncovered in test_coverage.get('uncovered_modules', []):
                module = uncovered.get('module', '')
                component_issues[module].append({
                    'type': 'low_coverage',
                    'severity': uncovered.get('severity', 'warning'),
                    'value': f"{uncovered.get('coverage_percent', 0):.1f}%",
                    'details': uncovered
                })

        performance = findings.get('performance_profiler_scanner', {})
        if performance:
            for slow in performance.get('slow_components', []):
                component = slow.get('component', '')
                component_issues[component].append({
                    'type': 'slow_operation',
                    'severity': slow.get('severity', 'warning'),
                    'value': f"{slow.get('avg_duration_ms', 0):.0f}ms",
                    'details': slow
                })

            for leak in performance.get('memory_leaks', []):
                component = leak.get('component', '')
                component_issues[component].append({
                    'type': 'memory_leak',
                    'severity': leak.get('severity', 'warning'),
                    'value': f"+{leak.get('memory_increase_mb', 0):.1f}MB",
                    'details': leak
                })

            for bottleneck in performance.get('bottlenecks', []):
                component = bottleneck.get('affected_component', '')
                component_issues[component].append({
                    'type': 'bottleneck',
                    'severity': bottleneck.get('severity', 'warning'),
                    'value': bottleneck.get('type', 'unknown'),
                    'details': bottleneck
                })

        co_occurrences = []

        for component, issues in component_issues.items():
            if len(issues) < 2:
                continue

            severity_score = self._calculate_severity_score(issues)

            pattern_type = self._classify_pattern_type(issues)

            co_occurrences.append({
                'component': component,
                'issues': issues,
                'issue_count': len(issues),
                'severity_score': severity_score,
                'pattern_type': pattern_type
            })

        co_occurrences.sort(key=lambda x: x['severity_score'], reverse=True)

        return co_occurrences

    def _calculate_severity_score(self, issues: List[Dict]) -> int:
        """
        Calculate weighted severity score for issues.

        Weights:
        - critical: 100
        - error: 50
        - warning: 25
        - info: 10
        """
        severity_weights = {
            'critical': 100,
            'error': 50,
            'warning': 25,
            'info': 10
        }

        total_score = 0
        for issue in issues:
            severity = issue.get('severity', 'info')
            total_score += severity_weights.get(severity, 10)

        return total_score

    def _classify_pattern_type(self, issues: List[Dict]) -> str:
        """Classify the pattern type based on issue combination."""
        issue_types = set(issue['type'] for issue in issues)

        if len(issue_types) >= 4:
            return 'multi_dimensional_issue'

        if 'high_complexity' in issue_types and 'low_maintainability' in issue_types:
            return 'quality_deterioration'

        if 'low_coverage' in issue_types and ('high_complexity' in issue_types or 'code_smell' in issue_types):
            return 'quality_testing_gap'

        if 'slow_operation' in issue_types and ('memory_leak' in issue_types or 'bottleneck' in issue_types):
            return 'performance_cluster'

        if len(issue_types) >= 3:
            return 'multi_dimensional_issue'

        return 'general_cluster'

    def _detect_architectural_smells(self, findings: Dict) -> List[Dict]:
        """
        Detect architectural smells (when feature flag enabled).

        Three smell types:
        1. God Objects - CC>=20 AND LOC>=500 AND MI<40
        2. Testing Gaps - Critical functions with coverage<30%
        3. Bottleneck Clusters - 2+ performance issues in same component
        """
        smells = []

        god_objects = self._detect_god_objects(findings)
        smells.extend(god_objects)

        testing_gaps = self._detect_testing_gaps(findings)
        smells.extend(testing_gaps)

        bottleneck_clusters = self._detect_bottleneck_clusters(findings)
        smells.extend(bottleneck_clusters)

        return smells

    def _detect_god_objects(self, findings: Dict) -> List[Dict]:
        """
        Detect God Object pattern.

        Criteria: CC>=20 AND LOC>=500 AND MI<40
        """
        god_objects = []

        code_quality = findings.get('code_quality_scanner', {})
        if not code_quality:
            return god_objects

        complexity_by_module = defaultdict(int)
        for complexity in code_quality.get('high_complexity_modules', []):
            module = complexity.get('module', '')
            cc = complexity.get('complexity', 0)
            if cc >= 20:
                complexity_by_module[module] = max(complexity_by_module[module], cc)

        maintainability_by_module = {}
        loc_by_module = {}
        for maint in code_quality.get('maintainability_issues', []):
            module = maint.get('module', '')
            mi = maint.get('maintainability_index', 100)
            loc = maint.get('loc', 0)

            if mi < 40:
                maintainability_by_module[module] = mi
                loc_by_module[module] = loc

        for module in complexity_by_module:
            if (module in maintainability_by_module and
                loc_by_module.get(module, 0) >= 500):

                god_objects.append({
                    'smell_type': 'god_object',
                    'component': module,
                    'evidence': {
                        'cyclomatic_complexity': complexity_by_module[module],
                        'lines_of_code': loc_by_module[module],
                        'maintainability_index': maintainability_by_module[module]
                    },
                    'severity': 'critical',
                    'description': 'Component exhibits god object pattern: high complexity, large size, low maintainability',
                    'recommended_action': 'Consider refactoring into smaller, focused modules'
                })

        return god_objects

    def _detect_testing_gaps(self, findings: Dict) -> List[Dict]:
        """
        Detect Testing Gap pattern.

        Criteria: Critical functions (delete/save/validate/auth) AND coverage<30%
        """
        testing_gaps = []

        test_coverage = findings.get('test_coverage_scanner', {})
        if not test_coverage:
            return testing_gaps

        critical_patterns = ['delete', 'save', 'validate', 'auth', 'remove', 'drop']

        for uncovered in test_coverage.get('uncovered_modules', []):
            coverage_percent = uncovered.get('coverage_percent', 100)
            if coverage_percent >= 30:
                continue

            uncovered_critical = uncovered.get('uncovered_critical', [])
            if not uncovered_critical:
                continue

            critical_funcs = []
            for func_info in uncovered_critical:
                func_name = func_info.get('function', '')
                if any(pattern in func_name.lower() for pattern in critical_patterns):
                    critical_funcs.append(func_name)

            if critical_funcs:
                testing_gaps.append({
                    'smell_type': 'testing_gap',
                    'component': uncovered.get('module', ''),
                    'evidence': {
                        'coverage_percent': coverage_percent,
                        'uncovered_critical_functions': critical_funcs,
                        'critical_function_count': len(critical_funcs)
                    },
                    'severity': 'error',
                    'description': f'Critical functions lack test coverage: {", ".join(critical_funcs[:3])}',
                    'recommended_action': 'Add tests for critical functions (delete, save, validate, auth)'
                })

        return testing_gaps

    def _detect_bottleneck_clusters(self, findings: Dict) -> List[Dict]:
        """
        Detect Bottleneck Cluster pattern.

        Criteria: 2+ performance issues in same component
        (slow ops + memory leaks + resource locks)
        """
        bottleneck_clusters = []

        performance = findings.get('performance_profiler_scanner', {})
        if not performance:
            return bottleneck_clusters

        component_performance_issues = defaultdict(list)

        for slow in performance.get('slow_components', []):
            component = slow.get('component', '')
            component_performance_issues[component].append({
                'type': 'slow_operation',
                'operation': slow.get('operation', ''),
                'avg_duration_ms': slow.get('avg_duration_ms', 0)
            })

        for leak in performance.get('memory_leaks', []):
            component = leak.get('component', '')
            component_performance_issues[component].append({
                'type': 'memory_leak',
                'growth_rate': leak.get('growth_rate_mb_per_hour', 0)
            })

        for bottleneck in performance.get('bottlenecks', []):
            component = bottleneck.get('affected_component', '')
            component_performance_issues[component].append({
                'type': 'bottleneck',
                'bottleneck_type': bottleneck.get('type', ''),
                'occurrence_count': bottleneck.get('occurrence_count', 0)
            })

        for component, perf_issues in component_performance_issues.items():
            if len(perf_issues) >= 2:
                bottleneck_clusters.append({
                    'smell_type': 'bottleneck_cluster',
                    'component': component,
                    'evidence': {
                        'issue_count': len(perf_issues),
                        'issue_types': list(set(issue['type'] for issue in perf_issues)),
                        'issues': perf_issues
                    },
                    'severity': 'error',
                    'description': f'Component has {len(perf_issues)} performance issues clustered together',
                    'recommended_action': 'Investigate performance bottlenecks and optimize critical paths'
                })

        return bottleneck_clusters

    def format_findings(self, findings: Dict) -> str:
        """Format cross-system pattern findings as human-readable report."""
        scan_meta = findings.get('scan_metadata', {})
        header = [
            "="*60,
            "CROSS-SYSTEM PATTERN SCAN REPORT",
            f"Timestamp: {scan_meta.get('timestamp', 'N/A')}",
            f"Lookback: {scan_meta.get('lookback_minutes', 30)} minutes",
            f"Scanners: {scan_meta.get('scanners_succeeded', 0)}/{scan_meta.get('scanners_checked', 0)} succeeded",
            f"Smells detection: {'ENABLED' if scan_meta.get('smells_enabled') else 'DISABLED'}",
            "="*60
        ]

        if not findings or (not findings.get('co_occurrences') and not findings.get('architectural_smells')):
            return '\n'.join(header + ['', 'No cross-system patterns detected'])

        report = []

        co_occurrences = findings.get('co_occurrences', [])
        if co_occurrences:
            report.append(f"CO-OCCURRENCE PATTERNS ({len(co_occurrences)} components)")

            high_severity = [c for c in co_occurrences if c['severity_score'] >= 100]
            if high_severity:
                report.append(f"\n  High Severity (score >= 100): {len(high_severity)} components")
                for co_occ in high_severity[:5]:
                    report.append(f"\n    {Path(co_occ['component']).name}:")
                    report.append(f"      Pattern: {co_occ['pattern_type']}")
                    report.append(f"      Issues: {co_occ['issue_count']}, Score: {co_occ['severity_score']}")
                    for issue in co_occ['issues'][:3]:
                        report.append(f"        - {issue['type']}: {issue['value']} ({issue['severity']})")

            medium_severity = [c for c in co_occurrences if 50 <= c['severity_score'] < 100]
            if medium_severity:
                report.append(f"\n  Medium Severity (50-99): {len(medium_severity)} components")

        architectural_smells = findings.get('architectural_smells', [])
        if architectural_smells:
            report.append(f"\nARCHITECTURAL SMELLS ({len(architectural_smells)} detected)")

            god_objects = [s for s in architectural_smells if s['smell_type'] == 'god_object']
            if god_objects:
                report.append(f"\n  God Objects: {len(god_objects)}")
                for smell in god_objects[:3]:
                    report.append(f"    - {Path(smell['component']).name}")
                    report.append(f"      CC={smell['evidence']['cyclomatic_complexity']}, "
                                f"LOC={smell['evidence']['lines_of_code']}, "
                                f"MI={smell['evidence']['maintainability_index']}")

            testing_gaps = [s for s in architectural_smells if s['smell_type'] == 'testing_gap']
            if testing_gaps:
                report.append(f"\n  Testing Gaps: {len(testing_gaps)}")
                for smell in testing_gaps[:3]:
                    report.append(f"    - {Path(smell['component']).name}")
                    report.append(f"      Coverage: {smell['evidence']['coverage_percent']:.1f}%")
                    report.append(f"      Critical funcs: {smell['evidence']['critical_function_count']}")

            bottleneck_clusters = [s for s in architectural_smells if s['smell_type'] == 'bottleneck_cluster']
            if bottleneck_clusters:
                report.append(f"\n  Bottleneck Clusters: {len(bottleneck_clusters)}")
                for smell in bottleneck_clusters[:3]:
                    report.append(f"    - {smell['component']}")
                    report.append(f"      Issues: {smell['evidence']['issue_count']}")
                    report.append(f"      Types: {', '.join(smell['evidence']['issue_types'])}")

        return '\n'.join(header + [''] + report)


def scan_patterns_standalone(lookback_minutes: int = 30) -> tuple:
    """CLI entry point: Scan cross-system patterns."""
    scanner = CrossSystemPatternScanner()
    findings = scanner.scan_patterns(lookback_minutes)
    report = scanner.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_patterns_standalone(lookback_minutes=30)

    print(report)

    if findings:
        print("\n" + "="*60)
        print("DETAILED FINDINGS SUMMARY")
        print("="*60)
        print(f"Co-occurrences: {len(findings.get('co_occurrences', []))}")
        print(f"Architectural smells: {len(findings.get('architectural_smells', []))}")
