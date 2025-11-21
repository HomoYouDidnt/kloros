# Phase 3: Self-Understanding Depth Design

**Date:** 2025-11-21
**Status:** Design Phase
**Depends On:** Phase 1 (Memory Foundation) - COMPLETE

## Overview

Extends introspection capabilities with three new scanners that deepen KLoROS's understanding of her own code quality, test coverage, and performance characteristics.

## Architecture

**Pattern:** Follow existing scanner architecture established by ErrorFrequencyScanner and ServiceHealthCorrelator

**New Scanners:**
1. CodeQualityScanner - Static analysis, complexity metrics, code smells
2. TestCoverageScanner - Test coverage analysis, test pattern detection
3. PerformanceProfilerScanner - Resource usage per component

All scanners:
- Inherit common scanner interface pattern
- Write findings to `/home/kloros/.kloros/scanner_findings/`
- Emit ChemBus signals for significant findings
- Integrate into introspection_daemon.py
- Run every 5 minutes in thread pool with 30s timeout

## Scanner 1: CodeQualityScanner

**Purpose:** Analyze code complexity and quality metrics

**Dependencies:**
- radon (cyclomatic complexity, maintainability index)
- pylint (static analysis)
- bandit (security vulnerabilities)

**Scan Method:**
```python
def scan_code_quality(
    self,
    target_paths: List[str] = None,
    min_complexity: int = 10
) -> Dict:
    """
    Scan codebase for quality metrics.

    Returns:
        {
            'high_complexity_modules': [...],
            'maintainability_issues': [...],
            'security_vulnerabilities': [...],
            'code_smells': [...]
        }
    """
```

**Metrics Collected:**
- Cyclomatic complexity per function/method
- Maintainability index per module
- Lines of code, comment ratio
- Security issues (SQL injection, hardcoded secrets, etc.)
- Duplicate code detection

**Findings Format:**
```json
{
    "module": "src/component_self_study.py",
    "complexity": 45,
    "maintainability_index": 62.3,
    "issues": [
        {
            "type": "high_complexity",
            "function": "_analyze_component",
            "complexity": 18,
            "severity": "warning"
        }
    ]
}
```

## Scanner 2: TestCoverageScanner

**Purpose:** Analyze test coverage and test quality

**Dependencies:**
- coverage.py (coverage metrics)
- pytest (test execution)

**Scan Method:**
```python
def scan_test_coverage(
    self,
    threshold: float = 80.0
) -> Dict:
    """
    Scan test coverage across codebase.

    Returns:
        {
            'coverage_summary': {...},
            'uncovered_modules': [...],
            'test_patterns': [...],
            'failing_tests': [...]
        }
    """
```

**Metrics Collected:**
- Overall coverage percentage
- Per-module coverage
- Untested critical functions
- Test execution patterns
- Test failure analysis from memory events

**Findings Format:**
```json
{
    "module": "src/kloros_memory/storage.py",
    "coverage_percent": 45.2,
    "uncovered_critical": [
        {
            "function": "consolidate_episodes",
            "lines": [586, 590, 595],
            "risk": "high"
        }
    ]
}
```

## Scanner 3: PerformanceProfilerScanner

**Purpose:** Monitor resource usage and performance bottlenecks

**Dependencies:**
- psutil (system resource monitoring)
- memory_profiler (memory usage)
- line_profiler (execution time)

**Scan Method:**
```python
def scan_performance_profile(
    self,
    lookback_hours: int = 24
) -> Dict:
    """
    Analyze performance characteristics from observations.

    Returns:
        {
            'resource_usage': {...},
            'slow_components': [...],
            'memory_leaks': [...],
            'bottlenecks': [...]
        }
    """
```

**Metrics Collected:**
- CPU usage per daemon
- Memory usage trends
- Response time analysis from OBSERVATION events
- I/O bottlenecks
- Database query performance

**Findings Format:**
```json
{
    "component": "klr-introspection",
    "cpu_percent": 15.3,
    "memory_mb": 245.8,
    "slow_operations": [
        {
            "operation": "scan_service_health",
            "avg_duration_ms": 3500,
            "threshold_ms": 1000,
            "severity": "warning"
        }
    ]
}
```

## Integration Changes

**introspection_daemon.py:**
```python
from kloros.introspection.scanners.code_quality_scanner import CodeQualityScanner
from kloros.introspection.scanners.test_coverage_scanner import TestCoverageScanner
from kloros.introspection.scanners.performance_profiler_scanner import PerformanceProfilerScanner

self.scanners = [
    InferencePerformanceScanner(),
    ContextUtilizationScanner(),
    ResourceProfilerScanner(),
    BottleneckDetectorScanner(),
    ComparativeAnalyzerScanner(),
    ServiceHealthCorrelator(),
    CodeQualityScanner(),           # NEW
    TestCoverageScanner(),          # NEW
    PerformanceProfilerScanner()    # NEW
]

self.executor = ThreadPoolExecutor(
    max_workers=9,  # Updated from 6
    thread_name_prefix="introspection_scanner_"
)
```

## Scanner Interface Requirements

Each scanner must implement:

```python
class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int

class XyzScanner:
    def __init__(self):
        # Initialize memory store, set self.available flag
        pass

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="xyz_scanner",
            description="...",
            interval_seconds=300,
            priority=2
        )

    def scan_xyz(self, **kwargs) -> Dict:
        # Main scanning logic
        # Query memory, analyze data
        # Return structured findings
        pass

    def format_findings(self, findings: Dict) -> str:
        # Format findings as human-readable report
        pass

def scan_xyz_standalone(**kwargs) -> Tuple[Dict, str]:
    """CLI entry point"""
    scanner = XyzScanner()
    findings = scanner.scan_xyz(**kwargs)
    report = scanner.format_findings(findings)
    return findings, report
```

## Memory Integration

Findings should be stored using existing patterns:

1. **Scanner Findings Directory:**
   - Write JSON findings to `/home/kloros/.kloros/scanner_findings/{scanner_name}/`
   - Timestamped filenames for historical tracking

2. **ChemBus Signals:**
   - Emit FINDING_DETECTED signal for significant issues:
     ```python
     self.pub.emit(
         signal="FINDING_DETECTED",
         ecosystem="introspection",
         intensity=2.0,  # Based on severity
         facts={
             "scanner": "code_quality_scanner",
             "finding_type": "high_complexity",
             "severity": "warning",
             "module": "...",
             "details": {...}
         }
     )
     ```

3. **Memory Events:**
   - Findings logged via MemoryLogger as EventType.FINDING_DETECTED
   - Enables recall during reflection: "What code quality issues exist?"

## Verification Strategy

**Scanner Implementation:**
1. Verify each scanner initializes correctly
2. Test scan methods with sample data
3. Verify findings format is correct
4. Test format_findings() output

**Integration Testing:**
1. Add scanners to introspection daemon
2. Verify all 9 scanners load
3. Confirm thread pool scales to 9 workers
4. Monitor logs for scan execution

**End-to-End Validation:**
1. Let daemon run for 30 minutes
2. Verify findings appear in scanner_findings/
3. Check ChemBus for FINDING_DETECTED signals
4. Query memory for finding events
5. Test recall: Ask KLoROS about code quality issues

**Performance Impact:**
1. Monitor introspection daemon CPU/memory
2. Verify scan cycles complete within 30s timeout
3. Ensure no impact on other daemons

## Success Criteria

- All 3 scanners implement full interface
- Integration with introspection daemon successful
- Findings written to scanner_findings/
- ChemBus signals emitted for significant findings
- Memory events created for recall
- No performance degradation
- KLoROS can recall quality/coverage/performance data

## Implementation Tasks

1. Install analysis dependencies (radon, pylint, bandit, coverage)
2. Implement CodeQualityScanner
3. Implement TestCoverageScanner
4. Implement PerformanceProfilerScanner
5. Integrate all 3 scanners into introspection daemon
6. Update thread pool to max_workers=9
7. Verify end-to-end functionality
8. 30-minute observation period
