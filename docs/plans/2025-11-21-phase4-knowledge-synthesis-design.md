# Phase 4: Knowledge Synthesis Design

**Date:** 2025-11-21
**Status:** Approved
**Phase:** Self-Mastery Phase 4
**Depends On:** Phase 3 (Self-Understanding Depth) - COMPLETE

## Overview

Implements meta-level understanding through two new introspection scanners that synthesize data from existing scanners and compare code against documentation.

## Strategic Approach

**Hybrid Implementation:**
- Start with simple co-occurrence pattern detection (foundation)
- Prepare architectural smell detection (ready to activate via feature flag)
- Compare formal documentation against actual component capabilities

**Value Proposition:**
- Holistic system health understanding
- Multi-dimensional problem identification
- Documentation drift detection
- Foundation for autonomous refactoring decisions

## Architecture

**Pattern:** Extends Phase 3 scanner architecture with meta-analysis capabilities

**New Scanners:**
1. CrossSystemPatternScanner - Aggregates findings from all 9 scanners
2. DocumentationCompletenessScanner - Compares `/docs/` against knowledge.db

**Integration:**
- Both scanners follow Phase 3 dual interface pattern
- Primary methods return rich `Dict` findings
- `scan()` method converts critical findings to `CapabilityGap` objects
- Run every 30 minutes (slower cadence than Phase 3's 5 minutes)
- Thread pool increases from 9 to 11 workers

**Data Access Strategy (Hybrid):**
- Check memory.db for recent findings first
- Fall back to calling scanner methods directly
- Forward-compatible: benefits automatically when findings persistence is added
- Documentation scanner: Direct access to knowledge.db + `/docs/` filesystem

## Scanner 1: CrossSystemPatternScanner

**Purpose:** Aggregate findings from all introspection scanners to detect co-occurrence patterns and architectural smells.

**Scan Method:**
```python
def scan_patterns(
    self,
    lookback_minutes: int = 30
) -> Dict:
    """
    Analyze cross-system patterns from scanner findings.

    Returns:
        {
            'co_occurrences': [...],
            'architectural_smells': [...],
            'scan_metadata': {...}
        }
    """
```

**Core Logic:**

```python
class CrossSystemPatternScanner:
    def __init__(self):
        self.detect_smells_enabled = False  # Feature flag
        self.other_scanners = [
            CodeQualityScanner(),
            TestCoverageScanner(),
            PerformanceProfilerScanner(),
            ServiceHealthCorrelator(),
            # ... other Phase 1-3 scanners
        ]

    def scan_patterns(self, lookback_minutes: int = 30) -> Dict:
        # 1. Collect findings (hybrid approach)
        findings = self._collect_recent_findings(lookback_minutes)

        # 2. Co-occurrence detection (always on)
        co_occurrences = self._detect_co_occurrences(findings)

        # 3. Architectural smell detection (feature flag)
        smells = []
        if self.detect_smells_enabled:
            smells = self._detect_architectural_smells(findings)

        return {
            'co_occurrences': co_occurrences,
            'architectural_smells': smells,
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_minutes': lookback_minutes,
                'scanners_checked': len(self.other_scanners),
                'smells_enabled': self.detect_smells_enabled
            }
        }
```

### Co-occurrence Detection

**Algorithm:**
1. Group all findings by component/module path
2. Count issue types per component
3. Rank by severity (critical issues weighted higher)
4. Return components with 2+ issues

**Output Format:**
```python
{
    'component': 'src/kloros_memory/storage.py',
    'issues': [
        {'type': 'high_complexity', 'severity': 'error', 'value': 'CC=25'},
        {'type': 'low_coverage', 'severity': 'warning', 'value': '15%'},
        {'type': 'slow_operation', 'severity': 'warning', 'value': '2500ms'}
    ],
    'issue_count': 3,
    'severity_score': 75,  # Weighted by severity
    'pattern_type': 'quality_performance_cluster'
}
```

### Architectural Smell Detection

**Feature Flag:** `self.detect_smells_enabled = False` (ready to activate)

**Three Smell Types:**

1. **God Objects**
   - Threshold: CC≥20 AND LOC≥500 AND MI<40
   - Source: CodeQualityScanner findings
   - Severity: Critical

2. **Testing Gaps**
   - Threshold: Critical functions (delete/save/validate/auth) AND coverage<30%
   - Source: TestCoverageScanner findings
   - Severity: Error

3. **Bottleneck Clusters**
   - Threshold: 2+ performance issues in same component (slow ops + memory leaks + resource locks)
   - Source: PerformanceProfilerScanner + ServiceHealthCorrelator findings
   - Severity: Error

**Output Format:**
```python
{
    'smell_type': 'god_object',
    'component': 'src/component_self_study.py',
    'evidence': {
        'cyclomatic_complexity': 25,
        'lines_of_code': 782,
        'maintainability_index': 28
    },
    'severity': 'critical',
    'description': 'Component exhibits god object pattern: high complexity, large size, low maintainability',
    'recommended_action': 'Consider refactoring into smaller, focused modules'
}
```

### Data Collection (Hybrid Approach)

```python
def _collect_recent_findings(self, lookback_minutes: int) -> Dict:
    """Collect findings with fallback logic."""
    findings = defaultdict(list)

    for scanner in self.other_scanners:
        try:
            # Try memory.db first (when persistence is added)
            scanner_findings = self._query_stored_findings(scanner, lookback_minutes)

            if not scanner_findings:
                # Fallback: call scanner directly
                scanner_name = scanner.get_metadata().name

                if scanner_name == 'code_quality_scanner':
                    scanner_findings = scanner.scan_code_quality()
                elif scanner_name == 'test_coverage_scanner':
                    scanner_findings = scanner.scan_test_coverage()
                elif scanner_name == 'performance_profiler_scanner':
                    scanner_findings = scanner.scan_performance_profile()
                elif scanner_name == 'service_health_correlator':
                    scanner_findings = scanner.scan_service_health()
                # ... handle other scanners

            findings[scanner_name] = scanner_findings

        except Exception as e:
            logger.warning(f"[pattern] Failed to collect from {scanner_name}: {e}")
            # Continue with other scanners - partial data better than none
            findings[scanner_name] = {}

    return findings
```

## Scanner 2: DocumentationCompletenessScanner

**Purpose:** Compare formal documentation against actual component capabilities to identify gaps and staleness.

**Scan Method:**
```python
def scan_documentation(self) -> Dict:
    """
    Analyze documentation completeness.

    Returns:
        {
            'undocumented_components': [...],
            'underdocumented_components': [...],
            'stale_documentation': [...],
            'documentation_coverage_percent': float,
            'scan_metadata': {...}
        }
    """
```

**Core Logic:**

```python
class DocumentationCompletenessScanner:
    def scan_documentation(self) -> Dict:
        # 1. Load component data from knowledge.db
        components = self._load_component_knowledge()

        # 2. Parse documentation files from /docs/
        doc_inventory = self._parse_docs_directory()

        # 3. Compare and identify gaps
        gaps = self._identify_documentation_gaps(components, doc_inventory)

        # 4. Detect staleness (code changed, docs didn't)
        stale_docs = self._detect_stale_documentation(components, doc_inventory)

        # 5. Calculate coverage
        coverage = self._calculate_coverage(components, doc_inventory)

        return {
            'undocumented_components': gaps['missing'],
            'underdocumented_components': gaps['incomplete'],
            'stale_documentation': stale_docs,
            'documentation_coverage_percent': coverage,
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_components': len(components),
                'documented_components': len(doc_inventory),
                'docs_directory': '/home/kloros/docs/'
            }
        }
```

### Gap Detection Logic

**Three Gap Types:**

1. **Undocumented (Missing):**
   - Component exists in knowledge.db
   - No mention in any `/docs/` markdown file
   - Severity: Based on component importance (core modules = error, utility = warning)

2. **Underdocumented (Incomplete):**
   - Component mentioned in docs
   - But key capabilities not documented
   - Compare `capabilities` list from knowledge.db against doc content
   - Severity: Warning

3. **Stale:**
   - Component's `last_studied_at` is after doc file's `last_modified`
   - Code changed but documentation didn't
   - Severity: Info (unless gap >30 days, then warning)

**Matching Strategy:**
```python
def _identify_documentation_gaps(self, components, doc_inventory):
    """Match components against documentation."""
    gaps = {'missing': [], 'incomplete': []}

    for component_id, component_data in components.items():
        # Extract component name from ID (e.g., "module:foo.py" → "foo")
        component_name = self._extract_component_name(component_id)
        file_path = component_data.get('file_path', '')

        # Search for mentions in documentation
        mentioned_in_docs = self._find_doc_mentions(component_name, file_path, doc_inventory)

        if not mentioned_in_docs:
            # Completely undocumented
            gaps['missing'].append({
                'component_id': component_id,
                'component_type': component_data.get('component_type'),
                'file_path': file_path,
                'capabilities': component_data.get('capabilities', []),
                'severity': self._assess_importance(component_data)
            })
        else:
            # Check if documented capabilities match actual capabilities
            documented_caps = self._extract_documented_capabilities(mentioned_in_docs)
            actual_caps = component_data.get('capabilities', [])

            missing_caps = set(actual_caps) - set(documented_caps)

            if missing_caps:
                gaps['incomplete'].append({
                    'component_id': component_id,
                    'documented_in': mentioned_in_docs,
                    'missing_capabilities': list(missing_caps),
                    'coverage_percent': len(documented_caps) / len(actual_caps) * 100,
                    'severity': 'warning'
                })

    return gaps
```

### Documentation Parsing

```python
def _parse_docs_directory(self) -> Dict:
    """Parse all markdown files in /docs/ directory."""
    docs_path = Path('/home/kloros/docs/')
    doc_inventory = {}

    if not docs_path.exists():
        logger.warning("[doc_completeness] /docs/ directory not found")
        return {}

    for md_file in docs_path.rglob('*.md'):
        try:
            with open(md_file, 'r') as f:
                content = f.read()

            doc_inventory[str(md_file)] = {
                'content': content,
                'last_modified': md_file.stat().st_mtime,
                'size': md_file.stat().st_size,
                'relative_path': md_file.relative_to(docs_path)
            }
        except Exception as e:
            logger.debug(f"[doc_completeness] Error reading {md_file}: {e}")
            continue

    return doc_inventory
```

### Component Knowledge Loading

```python
def _load_component_knowledge(self) -> Dict:
    """Load component data from knowledge.db."""
    try:
        conn = sqlite3.connect('/home/kloros/.kloros/knowledge.db')
        cursor = conn.execute("""
            SELECT component_id, component_type, file_path,
                   purpose, capabilities, last_studied_at
            FROM component_knowledge
            WHERE study_depth >= 2
        """)

        components = {}
        for row in cursor.fetchall():
            component_id = row[0]
            components[component_id] = {
                'component_type': row[1],
                'file_path': row[2],
                'purpose': row[3],
                'capabilities': json.loads(row[4]) if row[4] else [],
                'last_studied_at': row[5]
            }

        conn.close()
        return components

    except Exception as e:
        logger.error(f"[doc_completeness] Failed to load component knowledge: {e}")
        return {}
```

## Dual Interface: CapabilityGap Conversion

**Conversion Strategy:**

```python
def scan(self) -> List[CapabilityGap]:
    """Daemon-compatible interface - converts critical findings to gaps."""
    findings = self.scan_patterns()  # or scan_documentation()

    gaps = []

    # Only convert high-severity findings to CapabilityGaps
    for finding in findings.get('co_occurrences', []):
        if finding['severity'] in ['critical', 'error']:
            gaps.append(self._to_capability_gap(finding))

    for smell in findings.get('architectural_smells', []):
        if smell['severity'] == 'critical':
            gaps.append(self._to_capability_gap(smell))

    for gap in findings.get('undocumented_components', []):
        if gap['severity'] == 'error':  # Only critical components
            gaps.append(self._to_capability_gap(gap))

    return gaps

def _to_capability_gap(self, finding: Dict) -> CapabilityGap:
    """Convert finding to CapabilityGap format."""
    if finding.get('smell_type') == 'god_object':
        return CapabilityGap(
            hypothesis="GOD_OBJECT_DETECTED",
            question=f"Component {finding['component']} shows god object pattern - needs refactoring?",
            evidence=[
                f"complexity:{finding['evidence']['cyclomatic_complexity']}",
                f"lines_of_code:{finding['evidence']['lines_of_code']}",
                f"maintainability_index:{finding['evidence']['maintainability_index']}",
                f"severity:{finding['severity']}"
            ],
            autonomy_level=2,  # Investigate but don't auto-fix
            value_estimate=0.8,  # High value - architectural improvement
            cost_estimate=0.6    # Significant refactoring effort
        )
    # ... similar conversions for other finding types
```

**Severity Threshold for Gap Creation:**
- **Critical:** Always create CapabilityGap → triggers investigation
- **Error:** Create CapabilityGap for patterns, not individual issues
- **Warning/Info:** Log only, don't create gaps (available in rich Dict)

## Error Handling & Resilience

**Resilience Patterns:**

1. **Partial Success:** If 7 of 9 scanners provide data, pattern detection continues with available data
2. **Graceful Degradation:** Missing scanner data reduces pattern confidence but doesn't fail the scan
3. **Timeout Protection:** Each scanner call inherits daemon's 30s timeout
4. **Empty Results:** Return empty findings dict rather than raising exceptions
5. **Availability Flag:** `self.available = False` if critical dependencies missing

**CrossSystemPatternScanner Error Handling:**
```python
def _collect_recent_findings(self, lookback_minutes: int) -> Dict:
    """Collect findings with fallback logic."""
    findings = defaultdict(list)

    for scanner in self.other_scanners:
        try:
            scanner_findings = self._get_scanner_findings(scanner)
            findings[scanner.get_metadata().name] = scanner_findings
        except Exception as e:
            logger.warning(f"[pattern] Failed to collect from {scanner.get_metadata().name}: {e}")
            findings[scanner.get_metadata().name] = {}

    return findings
```

**DocumentationCompletenessScanner Error Handling:**
- Missing knowledge.db → log warning, return empty results, set `self.available = False`
- `/docs/` directory doesn't exist → log as finding, create directory
- Malformed markdown → skip file, log parse error
- Permission errors → log and continue with accessible files

## Integration Changes

**introspection_daemon.py:**
```python
from kloros.introspection.scanners.cross_system_pattern_scanner import CrossSystemPatternScanner
from kloros.introspection.scanners.documentation_completeness_scanner import DocumentationCompletenessScanner

self.scanners = [
    InferencePerformanceScanner(),
    ContextUtilizationScanner(),
    ResourceProfilerScanner(),
    BottleneckDetectorScanner(),
    ComparativeAnalyzerScanner(),
    ServiceHealthCorrelator(),
    CodeQualityScanner(),
    TestCoverageScanner(),
    PerformanceProfilerScanner(),
    CrossSystemPatternScanner(),           # NEW
    DocumentationCompletenessScanner()     # NEW
]

self.executor = ThreadPoolExecutor(
    max_workers=11,  # Updated from 9
    thread_name_prefix="introspection_scanner_"
)
```

**Scheduling:**
- Phase 4 scanners run every 30 minutes (slower cadence)
- Implementation: Check last run timestamp in `scan()` method
- If <30 minutes since last run, return cached results

## Testing Strategy

**CrossSystemPatternScanner Tests (~28 tests):**

1. **Co-occurrence detection:**
   - Single component with multiple issues
   - Multiple components with different combinations
   - Empty findings
   - Severity ranking correctness

2. **Architectural smell detection:**
   - God object detection thresholds
   - Testing gap detection
   - Bottleneck cluster detection
   - Feature flag behavior (disabled by default)

3. **Data collection:**
   - Memory.db query + fallback to direct calls
   - Partial scanner failures (7 of 9 succeed)
   - Timeout handling
   - Empty/malformed scanner results

4. **CapabilityGap conversion:**
   - Severity threshold filtering
   - Gap format correctness
   - Evidence field population

**DocumentationCompletenessScanner Tests (~25 tests):**

1. **Gap detection:**
   - Undocumented components
   - Underdocumented components
   - Fully documented components

2. **Staleness detection:**
   - Component modified after docs
   - Docs updated recently
   - Missing timestamps

3. **Coverage calculation:**
   - Percentage calculation
   - Edge cases (no docs, no components, empty files)

4. **Error handling:**
   - Missing knowledge.db
   - Missing `/docs/` directory
   - Malformed markdown
   - Permission errors

## Success Criteria

- Both scanners implement full interface (get_metadata, scan, primary method)
- All tests passing (53 total tests minimum)
- Integration with introspection daemon successful
- No performance degradation (30-minute cadence acceptable)
- Co-occurrence detection identifies multi-issue components
- Documentation gaps correctly identified
- Architectural smell detection ready to activate (feature flag)
- CapabilityGap conversion working for critical findings
- KLoROS can recall pattern and documentation findings via memory

## Implementation Tasks

1. Implement CrossSystemPatternScanner
   - Co-occurrence detection
   - Architectural smell detection (with feature flag)
   - Hybrid data collection
   - CapabilityGap conversion

2. Implement DocumentationCompletenessScanner
   - knowledge.db loading
   - `/docs/` parsing
   - Gap detection
   - Staleness detection
   - CapabilityGap conversion

3. Write comprehensive tests for both scanners

4. Integrate into introspection daemon
   - Add imports
   - Update scanner list
   - Update thread pool to 11 workers

5. Verify end-to-end functionality
   - 30-minute observation period
   - Check pattern detection output
   - Check documentation gap detection
   - Verify CapabilityGap emission

6. Activate architectural smell detection when stable
   - Flip feature flag: `detect_smells_enabled = True`
   - Verify smell detection accuracy
   - Tune thresholds if needed
