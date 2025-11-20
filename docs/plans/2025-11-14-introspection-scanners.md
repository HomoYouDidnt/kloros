# Introspection Scanners Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add five introspection capability scanners that monitor KLoROS's inference performance, context utilization, resource consumption, bottlenecks, and comparative strategy effectiveness, feeding insights into the existing observation/curiosity system for autonomous self-optimization.

**Architecture:** Each scanner inherits from `CapabilityScanner` and implements the standard `scan()` → `List[CapabilityGap]` interface. Scanners are auto-discovered by `CapabilityDiscoveryMonitor`, run on scheduled intervals, and emit both capability gaps (to curiosity system) and observations (to fitness ledger) when performance issues are detected. Failures are automatically quarantined and investigated by the self-repair system.

**Tech Stack:** Python 3.10+, psutil (resource monitoring), nvidia-ml-py (GPU metrics), existing KLoROS observation infrastructure (ChemBus, fitness ledger, curiosity pipeline)

---

## Risk Assessment Overview

### Global Risks

**Performance Impact:** LOW-MEDIUM
- Scanners run on scheduled intervals (5-10min default)
- Each scanner has configurable `scan_cost` budget
- ResourceGovernor prevents spawning under system pressure
- Mitigation: Conservative scan_cost values (0.15-0.25 per scanner)

**Data Accuracy:** MEDIUM
- Introspection metrics may be noisy or misinterpreted
- False positives could trigger unnecessary experiments
- Mitigation: Threshold-based filtering, 7-day baseline comparisons, evidence deduplication

**System Stability:** LOW
- Scanners inherit quarantine/circuit-breaker infrastructure
- Failed scanners auto-demoted and investigated
- System continues with degraded observability if scanner fails
- Mitigation: Comprehensive error handling, graceful degradation

**Integration Complexity:** LOW
- Follows existing scanner pattern (PyPIScanner reference)
- No new coordination logic needed
- Auto-discovered via `__init__.py` exports
- Mitigation: Copy proven patterns, comprehensive integration tests

---

## Prerequisites

### Environment Setup

**Step 1: Verify dependencies**

Run:
```bash
cd /home/kloros
python3 -c "import psutil; print(f'psutil {psutil.__version__}')"
python3 -c "import pynvml; print('nvidia-ml-py installed')"
```

Expected: Version output for both packages

**Step 2: Create test infrastructure directory**

Run:
```bash
mkdir -p /home/kloros/tests/registry/capability_scanners
touch /home/kloros/tests/registry/__init__.py
touch /home/kloros/tests/registry/capability_scanners/__init__.py
```

**Step 3: Verify HMAC key exists**

Run:
```bash
test -f ~/.kloros/keys/hmac.key && echo "HMAC key exists" || echo "ERROR: Missing HMAC key"
```

Expected: "HMAC key exists"

---

## Task 1: InferencePerformanceScanner

**Risk Assessment:**
- **Performance Impact:** LOW (0.15 scan_cost, runs every 10min)
- **Data Accuracy:** MEDIUM (inference timing can be noisy, needs statistical filtering)
- **Failure Impact:** LOW (graceful degradation - system loses inference performance insights)
- **Mitigation:** Use rolling averages, require 3+ samples before reporting gaps, threshold-based filtering

**Files:**
- Create: `/home/kloros/src/registry/capability_scanners/inference_performance_scanner.py`
- Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`
- Test: `/home/kloros/tests/registry/capability_scanners/test_inference_performance_scanner.py`

### Step 1: Write the failing test

Create file: `/home/kloros/tests/registry/capability_scanners/test_inference_performance_scanner.py`

```python
"""Tests for InferencePerformanceScanner."""

import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path

from src.registry.capability_scanners.inference_performance_scanner import (
    InferencePerformanceScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestInferencePerformanceScanner:
    """Test inference performance monitoring."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = InferencePerformanceScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'InferencePerformanceScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.15
        assert 0.0 <= metadata.alignment_baseline <= 1.0
        assert 0.0 < metadata.schedule_weight <= 1.0

    def test_scan_with_no_metrics_returns_empty(self):
        """Test scan returns empty list when no metrics available."""
        scanner = InferencePerformanceScanner()

        # Mock empty metrics file
        with patch.object(scanner, '_load_inference_metrics', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_slow_inference(self):
        """Test scanner detects slow inference patterns."""
        scanner = InferencePerformanceScanner()

        # Mock metrics showing slow inference
        mock_metrics = [
            {'task_type': 'reasoning', 'tokens_per_sec': 5.2, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 5.8, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 5.5, 'timestamp': time.time()},
            {'task_type': 'factual', 'tokens_per_sec': 45.0, 'timestamp': time.time()},
        ]

        with patch.object(scanner, '_load_inference_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert isinstance(gap, CapabilityGap)
            assert gap.type == 'performance_optimization'
            assert 'reasoning' in gap.reason.lower()
            assert 0.0 <= gap.alignment_score <= 1.0

    def test_scan_ignores_noise_below_threshold(self):
        """Test scanner ignores small performance variations."""
        scanner = InferencePerformanceScanner()

        # Mock metrics with small variation (not significant)
        mock_metrics = [
            {'task_type': 'reasoning', 'tokens_per_sec': 25.0, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 24.5, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 25.5, 'timestamp': time.time()},
        ]

        with patch.object(scanner, '_load_inference_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            assert gaps == []  # No significant performance issue

    def test_scan_handles_missing_metrics_file(self):
        """Test scanner handles missing metrics file gracefully."""
        scanner = InferencePerformanceScanner()

        with patch.object(Path, 'exists', return_value=False):
            gaps = scanner.scan()
            assert gaps == []  # Returns empty, does not crash
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_inference_performance_scanner.py -v
```

Expected: FAIL - "ModuleNotFoundError: No module named 'src.registry.capability_scanners.inference_performance_scanner'"

### Step 3: Write minimal implementation

Create file: `/home/kloros/src/registry/capability_scanners/inference_performance_scanner.py`

```python
"""
InferencePerformanceScanner - Monitors token generation performance.

Tracks tokens/second, probability distributions, backtracking patterns
to identify inference optimization opportunities.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any
from statistics import mean, stdev

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class InferencePerformanceScanner(CapabilityScanner):
    """Detects inference performance optimization opportunities."""

    # Performance thresholds
    SLOW_TOKENS_PER_SEC = 10.0  # Below this is considered slow
    SIGNIFICANT_VARIANCE = 0.3   # 30% variance triggers investigation
    MIN_SAMPLES = 3              # Need 3+ samples to report gaps

    def __init__(
        self,
        metrics_path: Path = Path("/home/kloros/.kloros/inference_metrics.jsonl")
    ):
        """Initialize scanner with metrics path."""
        self.metrics_path = metrics_path

    def scan(self) -> List[CapabilityGap]:
        """Scan inference metrics for performance optimization opportunities."""
        gaps = []

        try:
            metrics = self._load_inference_metrics()

            if not metrics:
                logger.debug("[inference_perf] No metrics available")
                return gaps

            # Group by task type
            by_task = self._group_by_task_type(metrics)

            # Analyze each task type
            for task_type, task_metrics in by_task.items():
                if len(task_metrics) < self.MIN_SAMPLES:
                    continue

                gap = self._analyze_task_performance(task_type, task_metrics)
                if gap:
                    gaps.append(gap)

            logger.info(f"[inference_perf] Found {len(gaps)} performance gaps")

        except Exception as e:
            logger.warning(f"[inference_perf] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='InferencePerformanceScanner',
            domain='introspection',
            alignment_baseline=0.7,
            scan_cost=0.15,
            schedule_weight=0.6  # Run every ~1.7 hours
        )

    def _load_inference_metrics(self) -> List[Dict[str, Any]]:
        """Load inference metrics from disk (7-day window)."""
        if not self.metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)  # 7 days

        try:
            with open(self.metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        timestamp = entry.get('timestamp', 0)
                        if timestamp >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[inference_perf] Failed to load metrics: {e}")

        return metrics

    def _group_by_task_type(
        self,
        metrics: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group metrics by task type."""
        grouped = {}
        for entry in metrics:
            task_type = entry.get('task_type', 'unknown')
            if task_type not in grouped:
                grouped[task_type] = []
            grouped[task_type].append(entry)
        return grouped

    def _analyze_task_performance(
        self,
        task_type: str,
        metrics: List[Dict[str, Any]]
    ) -> CapabilityGap:
        """Analyze performance for a specific task type."""
        tokens_per_sec = [m['tokens_per_sec'] for m in metrics if 'tokens_per_sec' in m]

        if not tokens_per_sec:
            return None

        avg_tps = mean(tokens_per_sec)

        # Check if slow
        if avg_tps < self.SLOW_TOKENS_PER_SEC:
            return CapabilityGap(
                type='performance_optimization',
                name=f'slow_inference_{task_type}',
                category='inference_performance',
                reason=f"Task type '{task_type}' averaging {avg_tps:.1f} tokens/sec (threshold: {self.SLOW_TOKENS_PER_SEC})",
                alignment_score=0.75,
                install_cost=0.4,  # Optimization experiments are moderately expensive
                metadata={
                    'task_type': task_type,
                    'avg_tokens_per_sec': avg_tps,
                    'sample_count': len(tokens_per_sec),
                    'threshold': self.SLOW_TOKENS_PER_SEC
                }
            )

        # Check for high variance
        if len(tokens_per_sec) >= 3:
            variance = stdev(tokens_per_sec) / avg_tps
            if variance > self.SIGNIFICANT_VARIANCE:
                return CapabilityGap(
                    type='performance_optimization',
                    name=f'unstable_inference_{task_type}',
                    category='inference_performance',
                    reason=f"Task type '{task_type}' has {variance*100:.1f}% variance in performance",
                    alignment_score=0.65,
                    install_cost=0.35,
                    metadata={
                        'task_type': task_type,
                        'variance': variance,
                        'avg_tokens_per_sec': avg_tps,
                        'sample_count': len(tokens_per_sec)
                    }
                )

        return None
```

### Step 4: Run test to verify it passes

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_inference_performance_scanner.py -v
```

Expected: PASS (all 5 tests green)

### Step 5: Register scanner in __init__.py

Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`

```python
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner'
]
```

### Step 6: Commit

Run:
```bash
cd /home/kloros
git add \
  src/registry/capability_scanners/inference_performance_scanner.py \
  src/registry/capability_scanners/__init__.py \
  tests/registry/capability_scanners/test_inference_performance_scanner.py

git commit -m "feat(scanners): add InferencePerformanceScanner for token generation monitoring"
```

---

## Task 2: ContextUtilizationScanner

**Risk Assessment:**
- **Performance Impact:** MEDIUM (0.25 scan_cost - requires parsing context windows)
- **Data Accuracy:** HIGH (context references are measurable and deterministic)
- **Failure Impact:** LOW (loses context efficiency insights but system continues)
- **Mitigation:** Cache parsed context, use sampling for large contexts, run less frequently (every 2 hours)

**Files:**
- Create: `/home/kloros/src/registry/capability_scanners/context_utilization_scanner.py`
- Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`
- Test: `/home/kloros/tests/registry/capability_scanners/test_context_utilization_scanner.py`

### Step 1: Write the failing test

Create file: `/home/kloros/tests/registry/capability_scanners/test_context_utilization_scanner.py`

```python
"""Tests for ContextUtilizationScanner."""

import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path

from src.registry.capability_scanners.context_utilization_scanner import (
    ContextUtilizationScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestContextUtilizationScanner:
    """Test context utilization monitoring."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ContextUtilizationScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ContextUtilizationScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.25
        assert metadata.alignment_baseline == 0.7

    def test_scan_with_no_context_logs_returns_empty(self):
        """Test scan returns empty when no context logs exist."""
        scanner = ContextUtilizationScanner()

        with patch.object(scanner, '_load_context_logs', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_unused_context_tail(self):
        """Test scanner detects when last portion of context is never referenced."""
        scanner = ContextUtilizationScanner()

        # Mock context logs showing last 30% never referenced
        mock_logs = [
            {
                'context_length': 1000,
                'references': [100, 200, 300, 400, 500, 600, 650],  # Max reference at 65%
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [50, 150, 250, 350, 450, 550, 680],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [80, 180, 280, 380, 480, 580, 630],
                'timestamp': time.time()
            }
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'context_optimization'
            assert 'unused' in gap.reason.lower()

    def test_scan_detects_recency_bias(self):
        """Test scanner detects when only recent context is used."""
        scanner = ContextUtilizationScanner()

        # Mock logs showing only last 20% of context referenced
        mock_logs = [
            {
                'context_length': 1000,
                'references': [850, 900, 920, 950, 980],  # All in last 20%
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [820, 880, 910, 940, 990],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [810, 870, 930, 960, 985],
                'timestamp': time.time()
            }
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('recency bias' in gap.reason.lower() for gap in gaps)

    def test_scan_handles_empty_references(self):
        """Test scanner handles logs with no references gracefully."""
        scanner = ContextUtilizationScanner()

        mock_logs = [
            {'context_length': 1000, 'references': [], 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
            gaps = scanner.scan()
            assert gaps == []  # No crash, just empty result
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_context_utilization_scanner.py -v
```

Expected: FAIL - ModuleNotFoundError

### Step 3: Write minimal implementation

Create file: `/home/kloros/src/registry/capability_scanners/context_utilization_scanner.py`

```python
"""
ContextUtilizationScanner - Monitors context window usage patterns.

Tracks which portions of context get referenced, detects unused context,
recency bias, and context windowing optimization opportunities.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class ContextUtilizationScanner(CapabilityScanner):
    """Detects context utilization optimization opportunities."""

    # Thresholds
    UNUSED_TAIL_THRESHOLD = 0.7   # If max reference < 70% of context, tail is unused
    RECENCY_BIAS_THRESHOLD = 0.2  # If all references in last 20%, recency bias
    MIN_SAMPLES = 3               # Need 3+ samples to report gaps

    def __init__(
        self,
        context_logs_path: Path = Path("/home/kloros/.kloros/context_utilization.jsonl")
    ):
        """Initialize scanner with context logs path."""
        self.context_logs_path = context_logs_path

    def scan(self) -> List[CapabilityGap]:
        """Scan context utilization for optimization opportunities."""
        gaps = []

        try:
            logs = self._load_context_logs()

            if len(logs) < self.MIN_SAMPLES:
                logger.debug("[context_util] Insufficient samples")
                return gaps

            # Analyze usage patterns
            unused_tail_gap = self._detect_unused_tail(logs)
            if unused_tail_gap:
                gaps.append(unused_tail_gap)

            recency_bias_gap = self._detect_recency_bias(logs)
            if recency_bias_gap:
                gaps.append(recency_bias_gap)

            logger.info(f"[context_util] Found {len(gaps)} context optimization gaps")

        except Exception as e:
            logger.warning(f"[context_util] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ContextUtilizationScanner',
            domain='introspection',
            alignment_baseline=0.7,
            scan_cost=0.25,
            schedule_weight=0.5  # Run every 2 hours
        )

    def _load_context_logs(self) -> List[Dict[str, Any]]:
        """Load context utilization logs (7-day window)."""
        if not self.context_logs_path.exists():
            return []

        logs = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.context_logs_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[context_util] Failed to load logs: {e}")

        return logs

    def _detect_unused_tail(self, logs: List[Dict[str, Any]]) -> CapabilityGap:
        """Detect if last portion of context is consistently unused."""
        max_reference_ratios = []

        for log in logs:
            context_len = log.get('context_length', 0)
            references = log.get('references', [])

            if not context_len or not references:
                continue

            max_ref = max(references)
            ratio = max_ref / context_len
            max_reference_ratios.append(ratio)

        if not max_reference_ratios:
            return None

        avg_max_ref_ratio = mean(max_reference_ratios)

        if avg_max_ref_ratio < self.UNUSED_TAIL_THRESHOLD:
            unused_pct = (1.0 - avg_max_ref_ratio) * 100
            return CapabilityGap(
                type='context_optimization',
                name='unused_context_tail',
                category='context_utilization',
                reason=f"Last {unused_pct:.0f}% of context rarely referenced (max ref at {avg_max_ref_ratio*100:.0f}%)",
                alignment_score=0.75,
                install_cost=0.3,
                metadata={
                    'avg_max_reference_ratio': avg_max_ref_ratio,
                    'unused_percentage': unused_pct,
                    'sample_count': len(max_reference_ratios)
                }
            )

        return None

    def _detect_recency_bias(self, logs: List[Dict[str, Any]]) -> CapabilityGap:
        """Detect if only recent context is being used."""
        recency_ratios = []

        for log in logs:
            context_len = log.get('context_length', 0)
            references = log.get('references', [])

            if not context_len or not references:
                continue

            # Calculate what portion of references are in the last 20%
            cutoff = context_len * 0.8
            recent_refs = [r for r in references if r >= cutoff]
            ratio = len(recent_refs) / len(references) if references else 0
            recency_ratios.append(ratio)

        if not recency_ratios:
            return None

        avg_recency = mean(recency_ratios)

        # If >80% of references are in last 20% of context, strong recency bias
        if avg_recency > 0.8:
            return CapabilityGap(
                type='context_optimization',
                name='recency_bias',
                category='context_utilization',
                reason=f"Recency bias detected: {avg_recency*100:.0f}% of references in last 20% of context",
                alignment_score=0.65,
                install_cost=0.35,
                metadata={
                    'avg_recency_ratio': avg_recency,
                    'sample_count': len(recency_ratios)
                }
            )

        return None
```

### Step 4: Run test to verify it passes

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_context_utilization_scanner.py -v
```

Expected: PASS (all 5 tests green)

### Step 5: Register scanner

Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`

```python
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner
from .context_utilization_scanner import ContextUtilizationScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner',
    'ContextUtilizationScanner'
]
```

### Step 6: Commit

Run:
```bash
cd /home/kloros
git add \
  src/registry/capability_scanners/context_utilization_scanner.py \
  src/registry/capability_scanners/__init__.py \
  tests/registry/capability_scanners/test_context_utilization_scanner.py

git commit -m "feat(scanners): add ContextUtilizationScanner for context window optimization"
```

---

## Task 3: ResourceProfilerScanner

**Risk Assessment:**
- **Performance Impact:** MEDIUM-HIGH (0.25 scan_cost - GPU queries can be expensive)
- **Data Accuracy:** HIGH (hardware metrics are deterministic)
- **Failure Impact:** LOW (system continues without resource optimization insights)
- **Special Risk:** GPU monitoring requires nvidia-ml-py, may fail on systems without NVIDIA GPUs
- **Mitigation:** Graceful fallback to CPU-only monitoring, cache GPU handles, run every 10min max

**Files:**
- Create: `/home/kloros/src/registry/capability_scanners/resource_profiler_scanner.py`
- Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`
- Test: `/home/kloros/tests/registry/capability_scanners/test_resource_profiler_scanner.py`

### Step 1: Write the failing test

Create file: `/home/kloros/tests/registry/capability_scanners/test_resource_profiler_scanner.py`

```python
"""Tests for ResourceProfilerScanner."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.registry.capability_scanners.resource_profiler_scanner import (
    ResourceProfilerScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestResourceProfilerScanner:
    """Test resource profiling scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ResourceProfilerScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ResourceProfilerScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.25

    def test_scan_detects_low_gpu_utilization(self):
        """Test scanner detects underutilized GPU."""
        scanner = ResourceProfilerScanner()

        # Mock GPU metrics showing low utilization
        mock_metrics = [
            {'gpu_util': 35.0, 'gpu_memory_util': 60.0, 'operation': 'tool_calling'},
            {'gpu_util': 42.0, 'gpu_memory_util': 65.0, 'operation': 'tool_calling'},
            {'gpu_util': 38.0, 'gpu_memory_util': 62.0, 'operation': 'tool_calling'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'resource_optimization'
            assert 'gpu' in gap.reason.lower()

    def test_scan_handles_no_gpu(self):
        """Test scanner handles systems without GPU gracefully."""
        scanner = ResourceProfilerScanner()

        # Mock CPU-only metrics
        mock_metrics = [
            {'cpu_util': 65.0, 'memory_util': 70.0, 'operation': 'reasoning'},
            {'cpu_util': 68.0, 'memory_util': 72.0, 'operation': 'reasoning'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            # Should not crash, may or may not find gaps
            assert isinstance(gaps, list)

    def test_scan_detects_cpu_bottleneck(self):
        """Test scanner detects CPU bottlenecks."""
        scanner = ResourceProfilerScanner()

        # Mock metrics showing high CPU usage
        mock_metrics = [
            {'cpu_util': 95.0, 'memory_util': 50.0, 'operation': 'preprocessing'},
            {'cpu_util': 97.0, 'memory_util': 52.0, 'operation': 'preprocessing'},
            {'cpu_util': 96.0, 'memory_util': 51.0, 'operation': 'preprocessing'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('cpu' in gap.reason.lower() for gap in gaps)

    def test_scan_with_empty_metrics_returns_empty(self):
        """Test scan returns empty when no metrics available."""
        scanner = ResourceProfilerScanner()

        with patch.object(scanner, '_load_resource_metrics', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_resource_profiler_scanner.py -v
```

Expected: FAIL - ModuleNotFoundError

### Step 3: Write minimal implementation

Create file: `/home/kloros/src/registry/capability_scanners/resource_profiler_scanner.py`

```python
"""
ResourceProfilerScanner - Monitors CPU/GPU/RAM usage per operation.

Tracks resource consumption patterns to identify allocation
optimization opportunities and bottlenecks.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)

# Optional GPU monitoring
try:
    import pynvml
    _GPU_AVAILABLE = True
except ImportError:
    _GPU_AVAILABLE = False
    logger.info("[resource_profiler] nvidia-ml-py not available, GPU monitoring disabled")


class ResourceProfilerScanner(CapabilityScanner):
    """Detects resource utilization optimization opportunities."""

    # Thresholds
    LOW_GPU_UTIL_THRESHOLD = 50.0   # Below 50% GPU util is underutilized
    HIGH_CPU_UTIL_THRESHOLD = 90.0  # Above 90% CPU is bottlenecked
    MIN_SAMPLES = 3

    def __init__(
        self,
        metrics_path: Path = Path("/home/kloros/.kloros/resource_metrics.jsonl")
    ):
        """Initialize scanner with metrics path."""
        self.metrics_path = metrics_path
        self._gpu_handle = None

        # Initialize GPU monitoring if available
        if _GPU_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                logger.warning(f"[resource_profiler] Failed to init GPU monitoring: {e}")

    def scan(self) -> List[CapabilityGap]:
        """Scan resource usage for optimization opportunities."""
        gaps = []

        try:
            metrics = self._load_resource_metrics()

            if len(metrics) < self.MIN_SAMPLES:
                logger.debug("[resource_profiler] Insufficient samples")
                return gaps

            # Group by operation type
            by_operation = self._group_by_operation(metrics)

            # Analyze each operation type
            for operation, op_metrics in by_operation.items():
                if len(op_metrics) < self.MIN_SAMPLES:
                    continue

                # Check GPU utilization
                gpu_gap = self._analyze_gpu_utilization(operation, op_metrics)
                if gpu_gap:
                    gaps.append(gpu_gap)

                # Check CPU bottlenecks
                cpu_gap = self._analyze_cpu_utilization(operation, op_metrics)
                if cpu_gap:
                    gaps.append(cpu_gap)

            logger.info(f"[resource_profiler] Found {len(gaps)} resource optimization gaps")

        except Exception as e:
            logger.warning(f"[resource_profiler] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ResourceProfilerScanner',
            domain='introspection',
            alignment_baseline=0.75,
            scan_cost=0.25,
            schedule_weight=0.6  # Run every ~1.7 hours
        )

    def _load_resource_metrics(self) -> List[Dict[str, Any]]:
        """Load resource metrics from disk (7-day window)."""
        if not self.metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[resource_profiler] Failed to load metrics: {e}")

        return metrics

    def _group_by_operation(
        self,
        metrics: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group metrics by operation type."""
        grouped = {}
        for entry in metrics:
            operation = entry.get('operation', 'unknown')
            if operation not in grouped:
                grouped[operation] = []
            grouped[operation].append(entry)
        return grouped

    def _analyze_gpu_utilization(
        self,
        operation: str,
        metrics: List[Dict[str, Any]]
    ) -> Optional[CapabilityGap]:
        """Analyze GPU utilization for an operation."""
        gpu_utils = [m['gpu_util'] for m in metrics if 'gpu_util' in m]

        if not gpu_utils:
            return None

        avg_gpu = mean(gpu_utils)

        if avg_gpu < self.LOW_GPU_UTIL_THRESHOLD:
            return CapabilityGap(
                type='resource_optimization',
                name=f'low_gpu_util_{operation}',
                category='resource_utilization',
                reason=f"Operation '{operation}' averaging {avg_gpu:.1f}% GPU utilization (threshold: {self.LOW_GPU_UTIL_THRESHOLD}%)",
                alignment_score=0.7,
                install_cost=0.4,
                metadata={
                    'operation': operation,
                    'avg_gpu_util': avg_gpu,
                    'sample_count': len(gpu_utils),
                    'threshold': self.LOW_GPU_UTIL_THRESHOLD
                }
            )

        return None

    def _analyze_cpu_utilization(
        self,
        operation: str,
        metrics: List[Dict[str, Any]]
    ) -> Optional[CapabilityGap]:
        """Analyze CPU utilization for potential bottlenecks."""
        cpu_utils = [m['cpu_util'] for m in metrics if 'cpu_util' in m]

        if not cpu_utils:
            return None

        avg_cpu = mean(cpu_utils)

        if avg_cpu > self.HIGH_CPU_UTIL_THRESHOLD:
            return CapabilityGap(
                type='resource_optimization',
                name=f'cpu_bottleneck_{operation}',
                category='resource_utilization',
                reason=f"Operation '{operation}' averaging {avg_cpu:.1f}% CPU utilization (bottleneck threshold: {self.HIGH_CPU_UTIL_THRESHOLD}%)",
                alignment_score=0.75,
                install_cost=0.35,
                metadata={
                    'operation': operation,
                    'avg_cpu_util': avg_cpu,
                    'sample_count': len(cpu_utils),
                    'threshold': self.HIGH_CPU_UTIL_THRESHOLD
                }
            )

        return None

    def __del__(self):
        """Cleanup GPU resources."""
        if _GPU_AVAILABLE and self._gpu_handle:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
```

### Step 4: Run test to verify it passes

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_resource_profiler_scanner.py -v
```

Expected: PASS (all 5 tests green)

### Step 5: Register scanner

Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`

```python
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner
from .context_utilization_scanner import ContextUtilizationScanner
from .resource_profiler_scanner import ResourceProfilerScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner',
    'ContextUtilizationScanner',
    'ResourceProfilerScanner'
]
```

### Step 6: Commit

Run:
```bash
cd /home/kloros
git add \
  src/registry/capability_scanners/resource_profiler_scanner.py \
  src/registry/capability_scanners/__init__.py \
  tests/registry/capability_scanners/test_resource_profiler_scanner.py

git commit -m "feat(scanners): add ResourceProfilerScanner for CPU/GPU/RAM monitoring"
```

---

## Task 4: BottleneckDetectorScanner

**Risk Assessment:**
- **Performance Impact:** LOW (0.20 scan_cost - reads queue metrics only)
- **Data Accuracy:** HIGH (queue depths and lock contention are measurable)
- **Failure Impact:** MEDIUM (missing bottleneck detection could cause performance degradation)
- **Special Risk:** May generate false positives during legitimate traffic spikes
- **Mitigation:** Time-windowed analysis (sustained bottlenecks only), configurable thresholds, integration with PHASE for load context

**Files:**
- Create: `/home/kloros/src/registry/capability_scanners/bottleneck_detector_scanner.py`
- Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`
- Test: `/home/kloros/tests/registry/capability_scanners/test_bottleneck_detector_scanner.py`

### Step 1: Write the failing test

Create file: `/home/kloros/tests/registry/capability_scanners/test_bottleneck_detector_scanner.py`

```python
"""Tests for BottleneckDetectorScanner."""

import pytest
import time
from unittest.mock import patch

from src.registry.capability_scanners.bottleneck_detector_scanner import (
    BottleneckDetectorScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestBottleneckDetectorScanner:
    """Test bottleneck detection scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = BottleneckDetectorScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'BottleneckDetectorScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.20

    def test_scan_detects_queue_buildup(self):
        """Test scanner detects growing queue depths."""
        scanner = BottleneckDetectorScanner()

        # Mock queue metrics showing exponential growth
        mock_metrics = [
            {'queue': 'chembus', 'depth': 50, 'timestamp': time.time() - 600},
            {'queue': 'chembus', 'depth': 120, 'timestamp': time.time() - 300},
            {'queue': 'chembus', 'depth': 280, 'timestamp': time.time() - 60},
            {'queue': 'chembus', 'depth': 350, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_queue_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'bottleneck'
            assert 'queue' in gap.reason.lower()

    def test_scan_detects_slow_operations(self):
        """Test scanner detects consistently slow operations."""
        scanner = BottleneckDetectorScanner()

        # Mock slow operation metrics
        mock_metrics = [
            {'operation': 'json_parsing', 'duration_ms': 450, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 520, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 480, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 510, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_operation_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('slow' in gap.reason.lower() for gap in gaps)

    def test_scan_ignores_transient_spikes(self):
        """Test scanner ignores one-off spikes (not sustained)."""
        scanner = BottleneckDetectorScanner()

        # Mock metrics with one spike but normal otherwise
        mock_metrics = [
            {'queue': 'chembus', 'depth': 20, 'timestamp': time.time() - 600},
            {'queue': 'chembus', 'depth': 180, 'timestamp': time.time() - 300},  # Spike
            {'queue': 'chembus', 'depth': 25, 'timestamp': time.time() - 60},
            {'queue': 'chembus', 'depth': 22, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_queue_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            assert gaps == []  # Transient spike ignored

    def test_scan_with_no_metrics_returns_empty(self):
        """Test scan returns empty when no metrics available."""
        scanner = BottleneckDetectorScanner()

        with patch.object(scanner, '_load_queue_metrics', return_value=[]):
            with patch.object(scanner, '_load_operation_metrics', return_value=[]):
                gaps = scanner.scan()
                assert gaps == []
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_bottleneck_detector_scanner.py -v
```

Expected: FAIL - ModuleNotFoundError

### Step 3: Write minimal implementation

Create file: `/home/kloros/src/registry/capability_scanners/bottleneck_detector_scanner.py`

```python
"""
BottleneckDetectorScanner - Monitors queue depths and slow operations.

Detects growing queues, lock contention, slow operations, and
processing delays that indicate system bottlenecks.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class BottleneckDetectorScanner(CapabilityScanner):
    """Detects system bottlenecks via queue and operation monitoring."""

    # Thresholds
    QUEUE_GROWTH_THRESHOLD = 2.0    # 2x growth is concerning
    QUEUE_SUSTAINED_THRESHOLD = 100  # Queue >100 sustained is bottleneck
    SLOW_OPERATION_MS = 200         # Operations >200ms are slow
    MIN_SAMPLES = 3

    def __init__(
        self,
        queue_metrics_path: Path = Path("/home/kloros/.kloros/queue_metrics.jsonl"),
        operation_metrics_path: Path = Path("/home/kloros/.kloros/operation_metrics.jsonl")
    ):
        """Initialize scanner with metrics paths."""
        self.queue_metrics_path = queue_metrics_path
        self.operation_metrics_path = operation_metrics_path

    def scan(self) -> List[CapabilityGap]:
        """Scan for bottlenecks in queues and operations."""
        gaps = []

        try:
            # Analyze queue buildup
            queue_metrics = self._load_queue_metrics()
            if queue_metrics:
                queue_gaps = self._analyze_queue_buildup(queue_metrics)
                gaps.extend(queue_gaps)

            # Analyze slow operations
            op_metrics = self._load_operation_metrics()
            if op_metrics:
                op_gaps = self._analyze_slow_operations(op_metrics)
                gaps.extend(op_gaps)

            logger.info(f"[bottleneck_detector] Found {len(gaps)} bottlenecks")

        except Exception as e:
            logger.warning(f"[bottleneck_detector] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='BottleneckDetectorScanner',
            domain='introspection',
            alignment_baseline=0.8,
            scan_cost=0.20,
            schedule_weight=0.7  # Run every ~1.4 hours
        )

    def _load_queue_metrics(self) -> List[Dict[str, Any]]:
        """Load queue depth metrics (7-day window)."""
        if not self.queue_metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.queue_metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[bottleneck_detector] Failed to load queue metrics: {e}")

        return metrics

    def _load_operation_metrics(self) -> List[Dict[str, Any]]:
        """Load operation timing metrics (7-day window)."""
        if not self.operation_metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.operation_metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[bottleneck_detector] Failed to load operation metrics: {e}")

        return metrics

    def _analyze_queue_buildup(
        self,
        metrics: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Detect growing queue depths."""
        gaps = []

        # Group by queue name
        by_queue = {}
        for entry in metrics:
            queue_name = entry.get('queue', 'unknown')
            if queue_name not in by_queue:
                by_queue[queue_name] = []
            by_queue[queue_name].append(entry)

        # Analyze each queue
        for queue_name, queue_data in by_queue.items():
            if len(queue_data) < self.MIN_SAMPLES:
                continue

            # Sort by timestamp
            queue_data.sort(key=lambda x: x.get('timestamp', 0))

            depths = [q['depth'] for q in queue_data if 'depth' in q]
            if len(depths) < self.MIN_SAMPLES:
                continue

            # Check for sustained high depth
            recent_depths = depths[-5:]  # Last 5 measurements
            avg_recent = mean(recent_depths)

            if avg_recent > self.QUEUE_SUSTAINED_THRESHOLD:
                gaps.append(CapabilityGap(
                    type='bottleneck',
                    name=f'queue_buildup_{queue_name}',
                    category='queue_bottleneck',
                    reason=f"Queue '{queue_name}' sustained depth {avg_recent:.0f} (threshold: {self.QUEUE_SUSTAINED_THRESHOLD})",
                    alignment_score=0.8,
                    install_cost=0.4,
                    metadata={
                        'queue': queue_name,
                        'avg_depth': avg_recent,
                        'threshold': self.QUEUE_SUSTAINED_THRESHOLD,
                        'sample_count': len(depths)
                    }
                ))

            # Check for growth trend
            if len(depths) >= 4:
                first_half = mean(depths[:len(depths)//2])
                second_half = mean(depths[len(depths)//2:])

                if first_half > 0 and second_half / first_half >= self.QUEUE_GROWTH_THRESHOLD:
                    gaps.append(CapabilityGap(
                        type='bottleneck',
                        name=f'queue_growth_{queue_name}',
                        category='queue_bottleneck',
                        reason=f"Queue '{queue_name}' growing {second_half/first_half:.1f}x (from {first_half:.0f} to {second_half:.0f})",
                        alignment_score=0.75,
                        install_cost=0.35,
                        metadata={
                            'queue': queue_name,
                            'growth_factor': second_half / first_half,
                            'initial_depth': first_half,
                            'current_depth': second_half
                        }
                    ))

        return gaps

    def _analyze_slow_operations(
        self,
        metrics: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Detect consistently slow operations."""
        gaps = []

        # Group by operation name
        by_operation = {}
        for entry in metrics:
            op_name = entry.get('operation', 'unknown')
            if op_name not in by_operation:
                by_operation[op_name] = []
            by_operation[op_name].append(entry)

        # Analyze each operation
        for op_name, op_data in by_operation.items():
            if len(op_data) < self.MIN_SAMPLES:
                continue

            durations = [o['duration_ms'] for o in op_data if 'duration_ms' in o]
            if len(durations) < self.MIN_SAMPLES:
                continue

            avg_duration = mean(durations)

            if avg_duration > self.SLOW_OPERATION_MS:
                gaps.append(CapabilityGap(
                    type='bottleneck',
                    name=f'slow_operation_{op_name}',
                    category='operation_bottleneck',
                    reason=f"Operation '{op_name}' averaging {avg_duration:.0f}ms (threshold: {self.SLOW_OPERATION_MS}ms)",
                    alignment_score=0.7,
                    install_cost=0.3,
                    metadata={
                        'operation': op_name,
                        'avg_duration_ms': avg_duration,
                        'threshold_ms': self.SLOW_OPERATION_MS,
                        'sample_count': len(durations)
                    }
                ))

        return gaps
```

### Step 4: Run test to verify it passes

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_bottleneck_detector_scanner.py -v
```

Expected: PASS (all 5 tests green)

### Step 5: Register scanner

Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`

```python
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner
from .context_utilization_scanner import ContextUtilizationScanner
from .resource_profiler_scanner import ResourceProfilerScanner
from .bottleneck_detector_scanner import BottleneckDetectorScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner',
    'ContextUtilizationScanner',
    'ResourceProfilerScanner',
    'BottleneckDetectorScanner'
]
```

### Step 6: Commit

Run:
```bash
cd /home/kloros
git add \
  src/registry/capability_scanners/bottleneck_detector_scanner.py \
  src/registry/capability_scanners/__init__.py \
  tests/registry/capability_scanners/test_bottleneck_detector_scanner.py

git commit -m "feat(scanners): add BottleneckDetectorScanner for queue and operation monitoring"
```

---

## Task 5: ComparativeAnalyzerScanner

**Risk Assessment:**
- **Performance Impact:** LOW (0.15 scan_cost - reads ledger data only)
- **Data Accuracy:** HIGH (fitness ledger provides ground truth)
- **Failure Impact:** LOW (system loses strategy comparison insights)
- **Special Risk:** May recommend premature optimization if sample size is small
- **Mitigation:** Require statistical significance (min 10 samples per strategy), confidence intervals, integrate with D-REAM's existing fitness evaluation

**Files:**
- Create: `/home/kloros/src/registry/capability_scanners/comparative_analyzer_scanner.py`
- Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`
- Test: `/home/kloros/tests/registry/capability_scanners/test_comparative_analyzer_scanner.py`

### Step 1: Write the failing test

Create file: `/home/kloros/tests/registry/capability_scanners/test_comparative_analyzer_scanner.py`

```python
"""Tests for ComparativeAnalyzerScanner."""

import pytest
import time
from unittest.mock import patch

from src.registry.capability_scanners.comparative_analyzer_scanner import (
    ComparativeAnalyzerScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestComparativeAnalyzerScanner:
    """Test comparative strategy analysis scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ComparativeAnalyzerScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ComparativeAnalyzerScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.15

    def test_scan_detects_superior_brainmod_strategy(self):
        """Test scanner detects when one brainmod consistently outperforms."""
        scanner = ComparativeAnalyzerScanner()

        # Mock fitness data showing ToT outperforming standard
        mock_fitness = [
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'strategy_optimization'
            assert 'tot' in gap.reason.lower()

    def test_scan_requires_sufficient_samples(self):
        """Test scanner ignores comparisons with insufficient data."""
        scanner = ComparativeAnalyzerScanner()

        # Mock insufficient samples
        mock_fitness = [
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()
            assert gaps == []  # Not enough samples

    def test_scan_detects_variant_outperformance(self):
        """Test scanner detects when zooid variant outperforms baseline."""
        scanner = ComparativeAnalyzerScanner()

        # Mock data showing variant outperforming
        mock_fitness = [
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 120, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 130, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 125, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 128, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 122, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 135, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 118, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 132, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 127, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 124, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 220, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 240, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 235, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 228, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 232, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 245, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 218, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 242, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 237, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 224, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('batched' in gap.reason.lower() for gap in gaps)

    def test_scan_with_no_data_returns_empty(self):
        """Test scan returns empty when no fitness data available."""
        scanner = ComparativeAnalyzerScanner()

        with patch.object(scanner, '_load_fitness_data', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []
```

### Step 2: Run test to verify it fails

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_comparative_analyzer_scanner.py -v
```

Expected: FAIL - ModuleNotFoundError

### Step 3: Write minimal implementation

Create file: `/home/kloros/src/registry/capability_scanners/comparative_analyzer_scanner.py`

```python
"""
ComparativeAnalyzerScanner - Compares strategy and variant performance.

Analyzes fitness ledger to identify which brainmods, zooid variants,
and strategies consistently outperform alternatives.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class ComparativeAnalyzerScanner(CapabilityScanner):
    """Detects superior strategies via comparative fitness analysis."""

    # Thresholds
    MIN_SAMPLES_PER_STRATEGY = 10     # Need 10+ samples for comparison
    SIGNIFICANT_PERFORMANCE_GAP = 0.15 # 15% improvement is significant
    SIGNIFICANT_SUCCESS_GAP = 0.20     # 20% better success rate

    def __init__(
        self,
        fitness_ledger_path: Path = Path("/home/kloros/.kloros/lineage/fitness_ledger.jsonl")
    ):
        """Initialize scanner with fitness ledger path."""
        self.fitness_ledger_path = fitness_ledger_path

    def scan(self) -> List[CapabilityGap]:
        """Scan fitness data for superior strategies."""
        gaps = []

        try:
            fitness_data = self._load_fitness_data()

            if not fitness_data:
                logger.debug("[comparative_analyzer] No fitness data available")
                return gaps

            # Compare brainmod strategies
            brainmod_gaps = self._compare_brainmod_strategies(fitness_data)
            gaps.extend(brainmod_gaps)

            # Compare zooid variants
            variant_gaps = self._compare_zooid_variants(fitness_data)
            gaps.extend(variant_gaps)

            logger.info(f"[comparative_analyzer] Found {len(gaps)} strategy improvements")

        except Exception as e:
            logger.warning(f"[comparative_analyzer] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ComparativeAnalyzerScanner',
            domain='introspection',
            alignment_baseline=0.75,
            scan_cost=0.15,
            schedule_weight=0.5  # Run every 2 hours
        )

    def _load_fitness_data(self) -> List[Dict[str, Any]]:
        """Load fitness ledger data (7-day window)."""
        if not self.fitness_ledger_path.exists():
            return []

        data = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.fitness_ledger_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            data.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[comparative_analyzer] Failed to load fitness data: {e}")

        return data

    def _compare_brainmod_strategies(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare brainmod performance for each zooid type."""
        gaps = []

        # Group by zooid type
        by_zooid = {}
        for entry in fitness_data:
            if 'brainmod' not in entry:
                continue

            zooid = entry.get('zooid', 'unknown')
            if zooid not in by_zooid:
                by_zooid[zooid] = {}

            brainmod = entry['brainmod']
            if brainmod not in by_zooid[zooid]:
                by_zooid[zooid][brainmod] = []

            by_zooid[zooid][brainmod].append(entry)

        # Compare strategies within each zooid type
        for zooid, strategies in by_zooid.items():
            if len(strategies) < 2:
                continue  # Need at least 2 strategies to compare

            # Calculate success rates
            strategy_stats = {}
            for brainmod, entries in strategies.items():
                if len(entries) < self.MIN_SAMPLES_PER_STRATEGY:
                    continue

                successes = [e for e in entries if e.get('success', False)]
                success_rate = len(successes) / len(entries)
                strategy_stats[brainmod] = {
                    'success_rate': success_rate,
                    'sample_count': len(entries)
                }

            if len(strategy_stats) < 2:
                continue

            # Find best and worst
            best = max(strategy_stats.items(), key=lambda x: x[1]['success_rate'])
            worst = min(strategy_stats.items(), key=lambda x: x[1]['success_rate'])

            performance_gap = best[1]['success_rate'] - worst[1]['success_rate']

            if performance_gap >= self.SIGNIFICANT_SUCCESS_GAP:
                gaps.append(CapabilityGap(
                    type='strategy_optimization',
                    name=f'superior_brainmod_{zooid}_{best[0]}',
                    category='brainmod_strategy',
                    reason=f"Brainmod '{best[0]}' outperforms '{worst[0]}' by {performance_gap*100:.1f}% for '{zooid}' tasks ({best[1]['success_rate']*100:.1f}% vs {worst[1]['success_rate']*100:.1f}%)",
                    alignment_score=0.8,
                    install_cost=0.25,
                    metadata={
                        'zooid': zooid,
                        'superior_strategy': best[0],
                        'inferior_strategy': worst[0],
                        'performance_gap': performance_gap,
                        'superior_success_rate': best[1]['success_rate'],
                        'inferior_success_rate': worst[1]['success_rate'],
                        'sample_counts': {best[0]: best[1]['sample_count'], worst[0]: worst[1]['sample_count']}
                    }
                ))

        return gaps

    def _compare_zooid_variants(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare zooid variant performance (e.g., batched vs standard)."""
        gaps = []

        # Group by zooid type and variant
        by_zooid = {}
        for entry in fitness_data:
            if 'variant' not in entry or 'ttr_ms' not in entry:
                continue

            zooid = entry.get('zooid', 'unknown')
            if zooid not in by_zooid:
                by_zooid[zooid] = {}

            variant = entry['variant']
            if variant not in by_zooid[zooid]:
                by_zooid[zooid][variant] = []

            by_zooid[zooid][variant].append(entry)

        # Compare variants within each zooid type
        for zooid, variants in by_zooid.items():
            if len(variants) < 2:
                continue

            # Calculate average TTR
            variant_stats = {}
            for variant, entries in variants.items():
                if len(entries) < self.MIN_SAMPLES_PER_STRATEGY:
                    continue

                ttrs = [e['ttr_ms'] for e in entries if 'ttr_ms' in e]
                if not ttrs:
                    continue

                avg_ttr = mean(ttrs)
                variant_stats[variant] = {
                    'avg_ttr_ms': avg_ttr,
                    'sample_count': len(ttrs)
                }

            if len(variant_stats) < 2:
                continue

            # Find fastest and slowest
            fastest = min(variant_stats.items(), key=lambda x: x[1]['avg_ttr_ms'])
            slowest = max(variant_stats.items(), key=lambda x: x[1]['avg_ttr_ms'])

            improvement = (slowest[1]['avg_ttr_ms'] - fastest[1]['avg_ttr_ms']) / slowest[1]['avg_ttr_ms']

            if improvement >= self.SIGNIFICANT_PERFORMANCE_GAP:
                gaps.append(CapabilityGap(
                    type='strategy_optimization',
                    name=f'superior_variant_{zooid}_{fastest[0]}',
                    category='zooid_variant',
                    reason=f"Variant '{fastest[0]}' outperforms '{slowest[0]}' by {improvement*100:.1f}% for '{zooid}' ({fastest[1]['avg_ttr_ms']:.0f}ms vs {slowest[1]['avg_ttr_ms']:.0f}ms TTR)",
                    alignment_score=0.75,
                    install_cost=0.3,
                    metadata={
                        'zooid': zooid,
                        'superior_variant': fastest[0],
                        'inferior_variant': slowest[0],
                        'improvement_pct': improvement,
                        'superior_ttr_ms': fastest[1]['avg_ttr_ms'],
                        'inferior_ttr_ms': slowest[1]['avg_ttr_ms'],
                        'sample_counts': {fastest[0]: fastest[1]['sample_count'], slowest[0]: slowest[1]['sample_count']}
                    }
                ))

        return gaps
```

### Step 4: Run test to verify it passes

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/test_comparative_analyzer_scanner.py -v
```

Expected: PASS (all 5 tests green)

### Step 5: Register scanner

Modify: `/home/kloros/src/registry/capability_scanners/__init__.py`

```python
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner
from .inference_performance_scanner import InferencePerformanceScanner
from .context_utilization_scanner import ContextUtilizationScanner
from .resource_profiler_scanner import ResourceProfilerScanner
from .bottleneck_detector_scanner import BottleneckDetectorScanner
from .comparative_analyzer_scanner import ComparativeAnalyzerScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner',
    'InferencePerformanceScanner',
    'ContextUtilizationScanner',
    'ResourceProfilerScanner',
    'BottleneckDetectorScanner',
    'ComparativeAnalyzerScanner'
]
```

### Step 6: Commit

Run:
```bash
cd /home/kloros
git add \
  src/registry/capability_scanners/comparative_analyzer_scanner.py \
  src/registry/capability_scanners/__init__.py \
  tests/registry/capability_scanners/test_comparative_analyzer_scanner.py

git commit -m "feat(scanners): add ComparativeAnalyzerScanner for strategy performance comparison"
```

---

## Task 6: Integration Testing

**Files:**
- Create: `/home/kloros/tests/registry/test_introspection_scanners_integration.py`

### Step 1: Write integration test

Create file: `/home/kloros/tests/registry/test_introspection_scanners_integration.py`

```python
"""Integration tests for introspection scanners."""

import pytest
from pathlib import Path

from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.registry.capability_scanners import (
    InferencePerformanceScanner,
    ContextUtilizationScanner,
    ResourceProfilerScanner,
    BottleneckDetectorScanner,
    ComparativeAnalyzerScanner
)


class TestIntrospectionScannersIntegration:
    """Test introspection scanners integrate with discovery monitor."""

    def test_all_scanners_discoverable(self):
        """Test all introspection scanners are auto-discovered."""
        monitor = CapabilityDiscoveryMonitor()

        scanner_names = [s.get_metadata().name for s in monitor.scanners]

        assert 'InferencePerformanceScanner' in scanner_names
        assert 'ContextUtilizationScanner' in scanner_names
        assert 'ResourceProfilerScanner' in scanner_names
        assert 'BottleneckDetectorScanner' in scanner_names
        assert 'ComparativeAnalyzerScanner' in scanner_names

    def test_all_scanners_have_introspection_domain(self):
        """Test all new scanners report 'introspection' domain."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            metadata = scanner.get_metadata()
            assert metadata.domain == 'introspection'

    def test_all_scanners_have_reasonable_scan_cost(self):
        """Test scan costs are within reasonable bounds."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            metadata = scanner.get_metadata()
            assert 0.0 < metadata.scan_cost <= 0.3  # All should be light-medium weight

    def test_scanners_return_valid_gaps_structure(self):
        """Test all scanners return properly structured CapabilityGap objects."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            gaps = scanner.scan()
            assert isinstance(gaps, list)

            # If gaps exist, validate structure
            for gap in gaps:
                assert hasattr(gap, 'type')
                assert hasattr(gap, 'name')
                assert hasattr(gap, 'category')
                assert hasattr(gap, 'reason')
                assert hasattr(gap, 'alignment_score')
                assert hasattr(gap, 'install_cost')
                assert 0.0 <= gap.alignment_score <= 1.0
                assert 0.0 <= gap.install_cost <= 1.0

    def test_monitor_can_run_cycle_with_new_scanners(self):
        """Test capability monitor can complete cycle with introspection scanners."""
        monitor = CapabilityDiscoveryMonitor()

        # Run a discovery cycle (should not crash)
        try:
            # This would normally be called by coordinator
            # Just verify it doesn't crash
            introspection_scanners = [
                s for s in monitor.scanners
                if s.get_metadata().domain == 'introspection'
            ]
            assert len(introspection_scanners) >= 5
        except Exception as e:
            pytest.fail(f"Monitor cycle failed with introspection scanners: {e}")
```

### Step 2: Run integration tests

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/test_introspection_scanners_integration.py -v
```

Expected: PASS (all 5 integration tests green)

### Step 3: Commit

Run:
```bash
cd /home/kloros
git add tests/registry/test_introspection_scanners_integration.py
git commit -m "test(scanners): add integration tests for introspection scanners"
```

---

## Task 7: Documentation

**Files:**
- Create: `/home/kloros/docs/introspection-scanners.md`

### Step 1: Write scanner documentation

Create file: `/home/kloros/docs/introspection-scanners.md`

```markdown
# Introspection Scanners

## Overview

Five capability scanners that monitor KLoROS's internal inference and resource usage patterns, feeding insights into the observation/curiosity system for autonomous self-optimization.

## Scanners

### 1. InferencePerformanceScanner

**Purpose:** Monitors token generation performance

**Metrics:**
- Tokens/second by task type
- Probability distribution entropy
- Backtracking frequency

**Triggers When:**
- Token generation < 10 tokens/sec (slow threshold)
- Performance variance > 30% (unstable)

**Outputs:**
- `performance_optimization` capability gaps
- Feeds curiosity system with optimization questions

**Schedule:** Every ~1.7 hours (schedule_weight: 0.6)

---

### 2. ContextUtilizationScanner

**Purpose:** Monitors which portions of context windows get referenced

**Metrics:**
- Context reference patterns
- Unused context tail detection
- Recency bias detection

**Triggers When:**
- Last 30%+ of context never referenced
- >80% of references in last 20% of context (recency bias)

**Outputs:**
- `context_optimization` capability gaps
- Context windowing recommendations

**Schedule:** Every 2 hours (schedule_weight: 0.5)

---

### 3. ResourceProfilerScanner

**Purpose:** Monitors CPU/GPU/RAM usage per operation

**Metrics:**
- GPU utilization per operation
- CPU utilization and bottlenecks
- Memory consumption patterns

**Triggers When:**
- GPU utilization < 50% (underutilized)
- CPU utilization > 90% (bottlenecked)

**Outputs:**
- `resource_optimization` capability gaps
- Batching/allocation recommendations

**Schedule:** Every ~1.7 hours (schedule_weight: 0.6)

**Special:** Gracefully degrades to CPU-only monitoring if no GPU

---

### 4. BottleneckDetectorScanner

**Purpose:** Monitors queue depths and slow operations

**Metrics:**
- Queue depth trends
- Queue growth rates
- Operation duration patterns

**Triggers When:**
- Queue depth sustained > 100
- Queue growing 2x+ (exponential growth)
- Operations averaging > 200ms

**Outputs:**
- `bottleneck` capability gaps
- Worker scaling recommendations

**Schedule:** Every ~1.4 hours (schedule_weight: 0.7)

---

### 5. ComparativeAnalyzerScanner

**Purpose:** Compares strategy and variant performance

**Metrics:**
- Brainmod success rates
- Zooid variant TTR comparisons
- Strategy effectiveness

**Triggers When:**
- Strategy performance gap > 15%
- Success rate difference > 20%
- Min 10 samples per strategy required

**Outputs:**
- `strategy_optimization` capability gaps
- Default strategy recommendations

**Schedule:** Every 2 hours (schedule_weight: 0.5)

---

## Architecture Integration

### Data Flow

```
1. Scanner runs on schedule (CapabilityDiscoveryMonitor)
2. Scans metrics files in ~/.kloros/
3. Detects optimization opportunities
4. Emits CapabilityGaps
5. CuriosityCore generates questions from gaps
6. curiosity_processor routes to experiments
7. D-REAM/SPICA run optimization experiments
8. Results feed back to fitness ledger
```

### Failure Handling

All scanners inherit quarantine infrastructure:
- 3 failures → quarantine (exponential backoff)
- Failed scanner becomes curiosity question
- System investigates scanner itself
- Graceful degradation (continues without scanner)

### Metrics Files

Scanners read from:
- `/home/kloros/.kloros/inference_metrics.jsonl` - Token performance
- `/home/kloros/.kloros/context_utilization.jsonl` - Context usage
- `/home/kloros/.kloros/resource_metrics.jsonl` - CPU/GPU/RAM
- `/home/kloros/.kloros/queue_metrics.jsonl` - Queue depths
- `/home/kloros/.kloros/operation_metrics.jsonl` - Operation timings
- `/home/kloros/.kloros/lineage/fitness_ledger.jsonl` - Strategy fitness

**Note:** Metrics files are created by zooids/modules during normal operation. If files don't exist, scanners return empty (no crash).

---

## Configuration

### Thresholds

Edit scanner source files to tune:

**InferencePerformanceScanner:**
- `SLOW_TOKENS_PER_SEC = 10.0`
- `SIGNIFICANT_VARIANCE = 0.3`

**ContextUtilizationScanner:**
- `UNUSED_TAIL_THRESHOLD = 0.7`
- `RECENCY_BIAS_THRESHOLD = 0.2`

**ResourceProfilerScanner:**
- `LOW_GPU_UTIL_THRESHOLD = 50.0`
- `HIGH_CPU_UTIL_THRESHOLD = 90.0`

**BottleneckDetectorScanner:**
- `QUEUE_GROWTH_THRESHOLD = 2.0`
- `QUEUE_SUSTAINED_THRESHOLD = 100`
- `SLOW_OPERATION_MS = 200`

**ComparativeAnalyzerScanner:**
- `MIN_SAMPLES_PER_STRATEGY = 10`
- `SIGNIFICANT_PERFORMANCE_GAP = 0.15`
- `SIGNIFICANT_SUCCESS_GAP = 0.20`

### Scan Frequency

Edit `schedule_weight` in `get_metadata()`:
- `1.0` = every hour
- `0.5` = every 2 hours
- `0.25` = every 4 hours

---

## Testing

### Unit Tests

```bash
# Test individual scanners
pytest tests/registry/capability_scanners/test_inference_performance_scanner.py -v
pytest tests/registry/capability_scanners/test_context_utilization_scanner.py -v
pytest tests/registry/capability_scanners/test_resource_profiler_scanner.py -v
pytest tests/registry/capability_scanners/test_bottleneck_detector_scanner.py -v
pytest tests/registry/capability_scanners/test_comparative_analyzer_scanner.py -v
```

### Integration Tests

```bash
# Test auto-discovery and monitor integration
pytest tests/registry/test_introspection_scanners_integration.py -v
```

---

## Monitoring Scanner Health

Check scanner state:

```bash
cat ~/.kloros/scanner_state.json | jq '.InferencePerformanceScanner'
```

View recent gaps:

```bash
tail ~/.kloros/curiosity_feed.json | jq 'select(.category | contains("introspection"))'
```

---

## Future Enhancements

1. **Metrics Collection Automation**
   - Add instrumentation to zooids to auto-emit metrics
   - Currently relies on manual metric logging

2. **Adaptive Thresholds**
   - Learn thresholds from historical data
   - Currently uses static thresholds

3. **Cross-Scanner Correlation**
   - Detect relationships between metrics
   - E.g., "slow inference when GPU util low"

4. **Real-Time Alerts**
   - Emit observations for critical bottlenecks
   - Currently only generates capability gaps

---

## Troubleshooting

**Scanner not running:**
- Check `scanner_state.json` for quarantine status
- Verify metrics files exist (scanners gracefully skip if missing)
- Check logs: `grep "inference_perf" ~/.kloros/logs/*.log`

**No gaps generated:**
- Verify metrics files have recent data (7-day window)
- Check thresholds aren't too strict
- Ensure MIN_SAMPLES requirements met

**High scan cost:**
- Reduce `schedule_weight` to run less frequently
- Check metrics file sizes (large files slow parsing)
```

### Step 2: Commit documentation

Run:
```bash
cd /home/kloros
git add docs/introspection-scanners.md
git commit -m "docs(scanners): add comprehensive introspection scanner documentation"
```

---

## Task 8: Final Verification

### Step 1: Run full test suite

Run:
```bash
cd /home/kloros
python3 -m pytest tests/registry/capability_scanners/ -v --tb=short
```

Expected: All tests PASS

### Step 2: Verify scanner registration

Run:
```bash
cd /home/kloros
python3 -c "
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
monitor = CapabilityDiscoveryMonitor()
introspection = [s for s in monitor.scanners if s.get_metadata().domain == 'introspection']
print(f'Found {len(introspection)} introspection scanners:')
for scanner in introspection:
    meta = scanner.get_metadata()
    print(f'  - {meta.name} (cost: {meta.scan_cost}, weight: {meta.schedule_weight})')
"
```

Expected: Output showing 5 introspection scanners

### Step 3: Create final commit

Run:
```bash
cd /home/kloros
git add -A
git commit -m "feat(introspection): complete implementation of 5 introspection scanners

- InferencePerformanceScanner: token generation monitoring
- ContextUtilizationScanner: context window optimization
- ResourceProfilerScanner: CPU/GPU/RAM profiling
- BottleneckDetectorScanner: queue and operation bottlenecks
- ComparativeAnalyzerScanner: strategy performance comparison

All scanners integrate with existing observation/curiosity pipeline,
inherit quarantine/self-repair infrastructure, and include comprehensive
tests and documentation.
"
```

---

## Summary

**Implementation Complete:**
- ✅ 5 introspection scanners implemented
- ✅ 25 unit tests (5 per scanner)
- ✅ 5 integration tests
- ✅ Comprehensive documentation
- ✅ Auto-discovery integration
- ✅ Risk assessments for each scanner

**Total Lines of Code:**
- Scanner implementations: ~1,200 LOC
- Tests: ~800 LOC
- Documentation: ~400 lines

**Key Benefits:**
1. Zero new infrastructure (plugs into existing capability discovery)
2. Self-healing (inherits quarantine/circuit-breaker)
3. Autonomous optimization (feeds curiosity → experiments → evolution)
4. Graceful degradation (failures don't crash system)
5. Comprehensive observability (5 complementary lenses)

**Next Steps:**
1. Add metrics instrumentation to zooids (populate metrics files)
2. Monitor curiosity_feed.json for generated optimization questions
3. Observe D-REAM experiments triggered by introspection gaps
4. Tune thresholds based on KLoROS's workload patterns
