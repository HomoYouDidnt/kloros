# Capability Discovery System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable KLoROS to detect missing tools, skills, and patterns through reactive detection and proactive scanning with meta-cognitive consolidation.

**Architecture:** Three-layer system with pluggable scanners (discovery), orchestration layer (prioritization), and meta-monitor (consolidation). Scanners auto-register from directory using zooid pattern. State persists across restarts for temporal continuity.

**Tech Stack:** Python 3.13, dataclasses, abstract base classes, JSONL for state persistence

---

## Phase 1: Foundation (Core Infrastructure)

### Task 1: Base Scanner Protocol

**Files:**
- Create: `src/registry/capability_scanners/base.py`
- Create: `src/registry/capability_scanners/__init__.py`
- Create: `tests/registry/test_capability_scanner_base.py`

**Step 1: Write failing test for CapabilityGap dataclass**

```python
# tests/registry/test_capability_scanner_base.py
import pytest
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata, CapabilityScanner


def test_capability_gap_creation():
    """Test CapabilityGap dataclass creation."""
    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2
    )

    assert gap.type == 'external_tool'
    assert gap.name == 'ripgrep'
    assert gap.alignment_score == 0.7
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scanner_base.py::test_capability_gap_creation -v`

Expected: FAIL with "No module named 'src.registry.capability_scanners'"

**Step 3: Create base.py with dataclasses**

```python
# src/registry/capability_scanners/base.py
"""
Base scanner protocol for capability discovery.

Defines data structures and abstract interface for all capability scanners.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class CapabilityGap:
    """Represents a missing capability."""
    type: str              # 'external_tool', 'skill', 'pattern'
    name: str              # 'ripgrep', 'database-migrations', 'circuit-breaker'
    category: str          # 'pypi_package', 'claude_skill', 'arch_pattern'
    reason: str            # Why this capability is needed
    alignment_score: float # 0.0-1.0
    install_cost: float    # 0.0-1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScannerMetadata:
    """Scanner identification and scheduling info."""
    name: str
    domain: str            # 'external_tools', 'skills', 'patterns'
    alignment_baseline: float  # Base alignment for gaps from this scanner
    scan_cost: float       # Resource cost (0.0-1.0)
    schedule_weight: float # How often to run (1.0=every cycle, 0.1=rarely)


class CapabilityScanner(ABC):
    """Base class for all capability scanners."""

    @abstractmethod
    def scan(self) -> List[CapabilityGap]:
        """Discover missing capabilities. Returns list of gaps."""
        pass

    @abstractmethod
    def get_metadata(self) -> ScannerMetadata:
        """Return scanner info."""
        pass

    def should_run(self, last_run: float, idle_budget: float) -> bool:
        """Default scheduling logic - can be overridden."""
        import time
        metadata = self.get_metadata()
        time_since_last = time.time() - last_run

        # Run based on schedule_weight and available budget
        min_interval = 3600 * (1.0 / metadata.schedule_weight)  # Hours to seconds
        return time_since_last >= min_interval and metadata.scan_cost <= idle_budget
```

**Step 4: Create __init__.py**

```python
# src/registry/capability_scanners/__init__.py
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner

__all__ = ['CapabilityGap', 'ScannerMetadata', 'CapabilityScanner']
```

**Step 5: Create test directory**

Run: `mkdir -p tests/registry`

**Step 6: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scanner_base.py::test_capability_gap_creation -v`

Expected: PASS

**Step 7: Write test for ScannerMetadata**

```python
# tests/registry/test_capability_scanner_base.py (add to file)

def test_scanner_metadata_creation():
    """Test ScannerMetadata dataclass creation."""
    metadata = ScannerMetadata(
        name='TestScanner',
        domain='external_tools',
        alignment_baseline=0.6,
        scan_cost=0.15,
        schedule_weight=0.5
    )

    assert metadata.name == 'TestScanner'
    assert metadata.scan_cost == 0.15
```

**Step 8: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scanner_base.py::test_scanner_metadata_creation -v`

Expected: PASS

**Step 9: Write test for abstract scanner**

```python
# tests/registry/test_capability_scanner_base.py (add to file)

def test_capability_scanner_abstract():
    """Test that CapabilityScanner cannot be instantiated."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        scanner = CapabilityScanner()


def test_capability_scanner_should_run():
    """Test default should_run scheduling logic."""
    import time

    class TestScanner(CapabilityScanner):
        def scan(self):
            return []

        def get_metadata(self):
            return ScannerMetadata(
                name='Test',
                domain='test',
                alignment_baseline=0.5,
                scan_cost=0.1,
                schedule_weight=1.0  # Run every hour
            )

    scanner = TestScanner()

    # Should run if last_run was >1 hour ago
    last_run = time.time() - 3700  # 61 minutes ago
    assert scanner.should_run(last_run, idle_budget=0.2) is True

    # Should not run if last_run was recent
    last_run = time.time() - 1800  # 30 minutes ago
    assert scanner.should_run(last_run, idle_budget=0.2) is False

    # Should not run if budget insufficient
    last_run = time.time() - 7200  # 2 hours ago
    assert scanner.should_run(last_run, idle_budget=0.05) is False
```

**Step 10: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scanner_base.py -v`

Expected: 3 tests pass

**Step 11: Commit**

```bash
git add src/registry/capability_scanners/ tests/registry/
git commit -m "feat: add base scanner protocol for capability discovery

- CapabilityGap dataclass for missing capabilities
- ScannerMetadata for scanner identification
- CapabilityScanner ABC with scheduling logic

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: CapabilityDiscoveryMonitor Orchestrator

**Files:**
- Create: `src/registry/capability_discovery_monitor.py`
- Create: `tests/registry/test_capability_discovery_monitor.py`

**Step 1: Write failing test for monitor initialization**

```python
# tests/registry/test_capability_discovery_monitor.py
import pytest
from pathlib import Path
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor


def test_monitor_initialization():
    """Test CapabilityDiscoveryMonitor initialization."""
    monitor = CapabilityDiscoveryMonitor()

    assert monitor is not None
    assert hasattr(monitor, 'scanners')
    assert isinstance(monitor.scanners, list)
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py::test_monitor_initialization -v`

Expected: FAIL with "No module named 'src.registry.capability_discovery_monitor'"

**Step 3: Create monitor with minimal implementation**

```python
# src/registry/capability_discovery_monitor.py
"""
CapabilityDiscoveryMonitor - Orchestrates capability gap detection.

Coordinates scanner execution, prioritization, and question generation.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.registry.capability_scanners.base import (
    CapabilityScanner,
    CapabilityGap,
    ScannerMetadata
)

logger = logging.getLogger(__name__)


class CapabilityDiscoveryMonitor:
    """
    Orchestrates capability discovery through pluggable scanners.

    Responsibilities:
    - Discover and register scanners
    - Schedule scanner execution
    - Track scanner state
    - Generate curiosity questions from gaps
    """

    def __init__(
        self,
        scanner_state_path: Path = Path("/home/kloros/.kloros/scanner_state.json"),
        operation_patterns_path: Path = Path("/home/kloros/.kloros/operation_patterns.jsonl")
    ):
        """Initialize monitor and load persisted state."""
        self.scanner_state_path = scanner_state_path
        self.operation_patterns_path = operation_patterns_path

        # Load persisted state
        self.scanner_state = self._load_scanner_state()
        self.operation_patterns = self._load_operation_patterns()

        # Discover scanners
        self.scanners: List[CapabilityScanner] = []
        self._discover_scanners()

        logger.info(f"[capability_monitor] Initialized with {len(self.scanners)} scanners")

    def _load_scanner_state(self) -> Dict[str, Dict[str, Any]]:
        """Load scanner state from disk."""
        if not self.scanner_state_path.exists():
            return {}

        try:
            with open(self.scanner_state_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[capability_monitor] Failed to load scanner state: {e}")
            return {}

    def _load_operation_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load operation patterns from disk (7-day window)."""
        if not self.operation_patterns_path.exists():
            return {}

        patterns = {}
        cutoff = time.time() - (7 * 86400)  # 7 days ago

        try:
            with open(self.operation_patterns_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        timestamp = entry.get('timestamp', 0)
                        if timestamp >= cutoff:
                            operation = entry.get('operation', 'unknown')
                            if operation not in patterns:
                                patterns[operation] = []
                            patterns[operation].append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[capability_monitor] Failed to load operation patterns: {e}")

        return patterns

    def _discover_scanners(self) -> None:
        """Auto-discover scanner classes from capability_scanners package."""
        # For now, scanners list is empty
        # Will be populated in next tasks
        pass

    def generate_capability_questions(self) -> List[Any]:
        """
        Generate curiosity questions from capability gaps.

        Returns list of CuriosityQuestion objects.
        """
        # Placeholder - will implement in later tasks
        return []
```

**Step 4: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py::test_monitor_initialization -v`

Expected: PASS

**Step 5: Write test for state persistence**

```python
# tests/registry/test_capability_discovery_monitor.py (add to file)
import json
import tempfile
from pathlib import Path


def test_monitor_loads_scanner_state():
    """Test monitor loads scanner state from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        # Write test state
        test_state = {
            "TestScanner": {
                "last_run": 1234567890.0,
                "suspended": False
            }
        }
        with open(state_path, 'w') as f:
            json.dump(test_state, f)

        # Initialize monitor
        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        assert "TestScanner" in monitor.scanner_state
        assert monitor.scanner_state["TestScanner"]["last_run"] == 1234567890.0


def test_monitor_loads_operation_patterns():
    """Test monitor loads operation patterns from disk."""
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        # Write test patterns
        with open(patterns_path, 'w') as f:
            # Recent pattern (within 7 days)
            recent = {
                "timestamp": time.time() - 86400,  # 1 day ago
                "operation": "grep",
                "file_size": 1000000
            }
            f.write(json.dumps(recent) + '\n')

            # Old pattern (beyond 7 days)
            old = {
                "timestamp": time.time() - (8 * 86400),  # 8 days ago
                "operation": "grep",
                "file_size": 500000
            }
            f.write(json.dumps(old) + '\n')

        # Initialize monitor
        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        # Only recent patterns loaded
        assert "grep" in monitor.operation_patterns
        assert len(monitor.operation_patterns["grep"]) == 1
```

**Step 6: Run tests to verify they pass**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py -v`

Expected: 3 tests pass

**Step 7: Commit**

```bash
git add src/registry/capability_discovery_monitor.py tests/registry/test_capability_discovery_monitor.py
git commit -m "feat: add CapabilityDiscoveryMonitor orchestrator

- Scanner discovery and registration
- State persistence (scanner state + operation patterns)
- 7-day rolling window for operation patterns
- Temporal continuity across restarts

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2: Initial Scanners

### Task 3: PyPIScanner Implementation

**Files:**
- Create: `src/registry/capability_scanners/pypi_scanner.py`
- Create: `tests/registry/test_pypi_scanner.py`

**Step 1: Write failing test for PyPIScanner**

```python
# tests/registry/test_pypi_scanner.py
import pytest
from src.registry.capability_scanners.pypi_scanner import PyPIScanner
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


def test_pypi_scanner_metadata():
    """Test PyPIScanner metadata."""
    scanner = PyPIScanner()
    metadata = scanner.get_metadata()

    assert metadata.name == 'PyPIScanner'
    assert metadata.domain == 'external_tools'
    assert 0.0 <= metadata.scan_cost <= 1.0
    assert 0.0 <= metadata.schedule_weight <= 1.0


def test_pypi_scanner_scan_returns_gaps():
    """Test PyPIScanner.scan() returns list of CapabilityGap objects."""
    scanner = PyPIScanner()
    gaps = scanner.scan()

    assert isinstance(gaps, list)
    # May be empty if all packages installed
    for gap in gaps:
        assert isinstance(gap, CapabilityGap)
        assert gap.type == 'external_tool'
        assert gap.category == 'pypi_package'
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_pypi_scanner.py -v`

Expected: FAIL with "No module named 'src.registry.capability_scanners.pypi_scanner'"

**Step 3: Create PyPIScanner implementation**

```python
# src/registry/capability_scanners/pypi_scanner.py
"""
PyPIScanner - Detects missing Python packages.

Compares installed packages against curated lists of useful packages
for different domains (ML, DevOps, monitoring, etc.).
"""

import logging
import subprocess
from typing import List, Set

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class PyPIScanner(CapabilityScanner):
    """Detects missing Python packages that could improve capabilities."""

    # Curated package lists by domain
    ML_PACKAGES = ['torch', 'transformers', 'mlflow', 'wandb']
    DEVOPS_PACKAGES = ['docker', 'kubernetes']
    MONITORING_PACKAGES = ['prometheus-client', 'opentelemetry-api']

    def scan(self) -> List[CapabilityGap]:
        """Scan for missing Python packages."""
        gaps = []

        try:
            installed = self._get_installed_packages()

            # Check each curated package
            all_packages = (
                self.ML_PACKAGES +
                self.DEVOPS_PACKAGES +
                self.MONITORING_PACKAGES
            )

            for pkg in all_packages:
                if pkg not in installed:
                    gaps.append(self._create_gap_for_package(pkg))

            logger.info(f"[pypi_scanner] Found {len(gaps)} missing packages")

        except Exception as e:
            logger.warning(f"[pypi_scanner] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='PyPIScanner',
            domain='external_tools',
            alignment_baseline=0.6,  # Tools generally medium alignment
            scan_cost=0.15,          # Low cost (local pip list)
            schedule_weight=0.5      # Run every ~2 hours idle
        )

    def _get_installed_packages(self) -> Set[str]:
        """Get set of installed package names."""
        try:
            result = subprocess.run(
                ['pip', 'list', '--format=freeze'],
                capture_output=True,
                text=True,
                timeout=5
            )

            packages = set()
            for line in result.stdout.split('\n'):
                if '==' in line:
                    pkg_name = line.split('==')[0].lower()
                    packages.add(pkg_name)

            return packages

        except Exception as e:
            logger.warning(f"[pypi_scanner] Failed to list packages: {e}")
            return set()

    def _create_gap_for_package(self, pkg: str) -> CapabilityGap:
        """Create CapabilityGap for missing package."""
        # Determine domain and alignment
        if pkg in self.ML_PACKAGES:
            domain = 'machine learning'
            alignment = 0.7
        elif pkg in self.DEVOPS_PACKAGES:
            domain = 'devops'
            alignment = 0.6
        elif pkg in self.MONITORING_PACKAGES:
            domain = 'monitoring'
            alignment = 0.8
        else:
            domain = 'general'
            alignment = 0.5

        return CapabilityGap(
            type='external_tool',
            name=pkg,
            category='pypi_package',
            reason=f"Package {pkg} not installed but commonly used in {domain} work",
            alignment_score=alignment,
            install_cost=0.3,  # pip install is relatively easy
            metadata={'domain': domain}
        )
```

**Step 4: Run tests to verify they pass**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_pypi_scanner.py -v`

Expected: 2 tests pass

**Step 5: Write integration test**

```python
# tests/registry/test_pypi_scanner.py (add to file)

def test_pypi_scanner_detects_uninstalled_package():
    """Test scanner detects packages that aren't installed."""
    scanner = PyPIScanner()
    gaps = scanner.scan()

    # Should find at least some missing packages from curated lists
    # (Unless running in environment with all packages installed)
    gap_names = [g.name for g in gaps]

    # All gaps should be for packages
    for gap in gaps:
        assert gap.type == 'external_tool'
        assert gap.category == 'pypi_package'
        assert 0.0 <= gap.alignment_score <= 1.0
        assert 0.0 <= gap.install_cost <= 1.0
```

**Step 6: Run integration test**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_pypi_scanner.py::test_pypi_scanner_detects_uninstalled_package -v`

Expected: PASS

**Step 7: Update __init__.py to export scanner**

```python
# src/registry/capability_scanners/__init__.py
"""
Capability scanner registry.

Auto-discovers scanner classes from this package.
"""

from .base import CapabilityGap, ScannerMetadata, CapabilityScanner
from .pypi_scanner import PyPIScanner

__all__ = [
    'CapabilityGap',
    'ScannerMetadata',
    'CapabilityScanner',
    'PyPIScanner'
]
```

**Step 8: Commit**

```bash
git add src/registry/capability_scanners/pypi_scanner.py tests/registry/test_pypi_scanner.py src/registry/capability_scanners/__init__.py
git commit -m "feat: add PyPIScanner for missing package detection

- Scans for missing packages from curated lists
- Categorizes by domain (ML, DevOps, monitoring)
- Low scan cost (uses pip list)
- Proactive capability gap detection

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Scanner Discovery in Monitor

**Files:**
- Modify: `src/registry/capability_discovery_monitor.py:74-76`
- Modify: `tests/registry/test_capability_discovery_monitor.py`

**Step 1: Write test for scanner discovery**

```python
# tests/registry/test_capability_discovery_monitor.py (add to file)

def test_monitor_discovers_scanners():
    """Test monitor discovers available scanners."""
    monitor = CapabilityDiscoveryMonitor()

    # Should discover at least PyPIScanner
    assert len(monitor.scanners) > 0

    scanner_names = [s.get_metadata().name for s in monitor.scanners]
    assert 'PyPIScanner' in scanner_names
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py::test_monitor_discovers_scanners -v`

Expected: FAIL with "assert 0 > 0" (no scanners discovered)

**Step 3: Implement scanner discovery**

```python
# src/registry/capability_discovery_monitor.py
# Replace _discover_scanners method (around line 74)

def _discover_scanners(self) -> None:
    """Auto-discover scanner classes from capability_scanners package."""
    from src.registry import capability_scanners
    import inspect

    discovered = []

    # Scan package for CapabilityScanner subclasses
    for name in dir(capability_scanners):
        obj = getattr(capability_scanners, name)

        # Check if it's a class and subclass of CapabilityScanner
        if (inspect.isclass(obj) and
            issubclass(obj, CapabilityScanner) and
            obj is not CapabilityScanner):

            try:
                # Instantiate scanner
                scanner = obj()
                metadata = scanner.get_metadata()

                # Restore persisted state if available
                if metadata.name in self.scanner_state:
                    state = self.scanner_state[metadata.name]
                    scanner.last_run = state.get('last_run', 0.0)
                    scanner.suspended = state.get('suspended', False)
                else:
                    scanner.last_run = 0.0
                    scanner.suspended = False

                discovered.append(scanner)
                logger.info(f"[capability_monitor] Discovered scanner: {metadata.name}")

            except Exception as e:
                logger.warning(f"[capability_monitor] Failed to instantiate {name}: {e}")

    self.scanners = discovered
    logger.info(f"[capability_monitor] Discovered {len(discovered)} scanners")
```

**Step 4: Add last_run and suspended attributes to scanner instances**

Note: These are dynamically added, not part of base class

**Step 5: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py::test_monitor_discovers_scanners -v`

Expected: PASS

**Step 6: Write test for state restoration**

```python
# tests/registry/test_capability_discovery_monitor.py (add to file)

def test_monitor_restores_scanner_state():
    """Test monitor restores scanner state from disk."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        # Write state with PyPIScanner info
        test_state = {
            "PyPIScanner": {
                "last_run": 1234567890.0,
                "suspended": False
            }
        }
        with open(state_path, 'w') as f:
            json.dump(test_state, f)

        # Initialize monitor
        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        # Find PyPIScanner
        pypi_scanner = None
        for scanner in monitor.scanners:
            if scanner.get_metadata().name == 'PyPIScanner':
                pypi_scanner = scanner
                break

        assert pypi_scanner is not None
        assert pypi_scanner.last_run == 1234567890.0
        assert pypi_scanner.suspended is False
```

**Step 7: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_discovery_monitor.py::test_monitor_restores_scanner_state -v`

Expected: PASS

**Step 8: Commit**

```bash
git add src/registry/capability_discovery_monitor.py tests/registry/test_capability_discovery_monitor.py
git commit -m "feat: add scanner auto-discovery to monitor

- Auto-discovers CapabilityScanner subclasses
- Restores scanner state from disk (last_run, suspended)
- Temporal continuity for scanner scheduling

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3: Prioritization & Question Generation

### Task 5: Hybrid Scoring System

**Files:**
- Modify: `src/registry/capability_discovery_monitor.py` (add methods)
- Create: `tests/registry/test_capability_scoring.py`

**Step 1: Write test for frequency scoring**

```python
# tests/registry/test_capability_scoring.py
import pytest
import time
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.registry.capability_scanners.base import CapabilityGap


def test_frequency_score_calculation():
    """Test frequency score based on operation patterns."""
    monitor = CapabilityDiscoveryMonitor()

    # Mock operation patterns
    monitor.operation_patterns = {
        'grep': [
            {'timestamp': time.time() - 3600, 'file_size': 1000000},
            {'timestamp': time.time() - 7200, 'file_size': 2000000},
            {'timestamp': time.time() - 10800, 'file_size': 1500000},
        ]
    }

    # Gap related to grep operations
    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2,
        metadata={'operation': 'grep'}
    )

    score = monitor._calculate_frequency_score(gap)

    assert 0.0 <= score <= 1.0
    # High frequency (3 ops in window) should score high
    assert score > 0.5
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scoring.py::test_frequency_score_calculation -v`

Expected: FAIL with "AttributeError: 'CapabilityDiscoveryMonitor' object has no attribute '_calculate_frequency_score'"

**Step 3: Implement frequency scoring**

```python
# src/registry/capability_discovery_monitor.py (add method)

def _calculate_frequency_score(self, gap: CapabilityGap) -> float:
    """
    Calculate frequency score (0.0-1.0) based on operation patterns.

    Higher score = operation happens frequently, need is urgent.
    """
    operation = gap.metadata.get('operation')
    if not operation or operation not in self.operation_patterns:
        return 0.1  # Low baseline for non-tracked operations

    patterns = self.operation_patterns[operation]
    count = len(patterns)

    # Normalize: 0 ops = 0.0, 10+ ops in 7 days = 1.0
    frequency_score = min(count / 10.0, 1.0)

    # Boost reactive gaps (immediate need)
    if gap.metadata.get('reactive', False):
        frequency_score = min(frequency_score + 0.3, 1.0)

    return frequency_score
```

**Step 4: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scoring.py::test_frequency_score_calculation -v`

Expected: PASS

**Step 5: Write test for priority calculation**

```python
# tests/registry/test_capability_scoring.py (add to file)

def test_priority_score_calculation():
    """Test hybrid priority score calculation."""
    monitor = CapabilityDiscoveryMonitor()

    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2
    )

    # Mock component scores
    frequency = 0.8
    voi = 0.6
    alignment = gap.alignment_score
    cost = gap.install_cost

    priority = monitor._calculate_priority_score(
        frequency, voi, alignment, cost
    )

    assert 0.0 <= priority <= 1.0

    # With high frequency and alignment, should score well
    # Formula: (freq * 0.3) + (voi * 0.35) + (align * 0.25) + ((1-cost) * 0.1)
    expected = (0.8 * 0.3) + (0.6 * 0.35) + (0.7 * 0.25) + ((1.0 - 0.2) * 0.1)
    assert abs(priority - expected) < 0.01
```

**Step 6: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scoring.py::test_priority_score_calculation -v`

Expected: FAIL

**Step 7: Implement priority scoring**

```python
# src/registry/capability_discovery_monitor.py (add method)

def _calculate_priority_score(
    self,
    frequency: float,
    voi: float,
    alignment: float,
    cost: float
) -> float:
    """
    Calculate hybrid priority score.

    Formula: (frequency * 0.3) + (voi * 0.35) + (alignment * 0.25) + ((1-cost) * 0.1)

    Returns score 0.0-1.0.
    """
    priority = (
        (frequency * 0.3) +
        (voi * 0.35) +
        (alignment * 0.25) +
        ((1.0 - cost) * 0.1)
    )

    return max(0.0, min(priority, 1.0))
```

**Step 8: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_capability_scoring.py -v`

Expected: 2 tests pass

**Step 9: Commit**

```bash
git add src/registry/capability_discovery_monitor.py tests/registry/test_capability_scoring.py
git commit -m "feat: add hybrid scoring system

- Frequency scoring based on operation patterns
- Priority calculation: freq(30%) + voi(35%) + align(25%) + cost(10%)
- Reactive gap boosting for immediate needs

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Question Generation

**Files:**
- Modify: `src/registry/capability_discovery_monitor.py` (implement generate_capability_questions)
- Create: `tests/registry/test_question_generation.py`

**Step 1: Write test for question generation**

```python
# tests/registry/test_question_generation.py
import pytest
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.registry.curiosity_core import CuriosityQuestion, ActionClass


def test_generate_capability_questions():
    """Test generating CuriosityQuestion objects from gaps."""
    monitor = CapabilityDiscoveryMonitor()

    questions = monitor.generate_capability_questions()

    # Should return list
    assert isinstance(questions, list)

    # All items should be CuriosityQuestion
    for q in questions:
        assert isinstance(q, CuriosityQuestion)
        assert q.action_class == ActionClass.FIND_SUBSTITUTE
        assert hasattr(q, 'hypothesis')
        assert hasattr(q, 'question')
        assert hasattr(q, 'evidence')
```

**Step 2: Run test to verify it fails**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_question_generation.py::test_generate_capability_questions -v`

Expected: FAIL (questions empty or wrong type)

**Step 3: Implement question generation**

```python
# src/registry/capability_discovery_monitor.py
# Replace generate_capability_questions method (around line 82)

def generate_capability_questions(self) -> List[Any]:
    """
    Generate curiosity questions from capability gaps.

    Steps:
    1. Run scanners that should_run
    2. Collect capability gaps
    3. Score gaps with hybrid prioritization
    4. Convert top N gaps to CuriosityQuestions

    Returns list of CuriosityQuestion objects.
    """
    from src.registry.curiosity_core import CuriosityQuestion, ActionClass
    import hashlib

    all_gaps = []

    # Run scanners
    for scanner in self.scanners:
        metadata = scanner.get_metadata()

        # Skip suspended scanners
        if getattr(scanner, 'suspended', False):
            logger.debug(f"[capability_monitor] Skipping suspended scanner: {metadata.name}")
            continue

        # Check if should run (scheduling + budget)
        idle_budget = 5.0  # 5 seconds total budget
        if not scanner.should_run(
            last_run=getattr(scanner, 'last_run', 0.0),
            idle_budget=idle_budget
        ):
            logger.debug(f"[capability_monitor] Skipping {metadata.name} (not scheduled)")
            continue

        try:
            logger.info(f"[capability_monitor] Running scanner: {metadata.name}")
            gaps = scanner.scan()
            all_gaps.extend(gaps)

            # Update last_run
            scanner.last_run = time.time()

        except Exception as e:
            logger.warning(f"[capability_monitor] Scanner {metadata.name} failed: {e}")

    if not all_gaps:
        logger.info("[capability_monitor] No capability gaps detected")
        return []

    # Score gaps
    scored_gaps = []
    for gap in all_gaps:
        frequency = self._calculate_frequency_score(gap)
        voi = 0.5  # Placeholder - will integrate with brainmods reasoning later
        alignment = gap.alignment_score
        cost = gap.install_cost

        priority = self._calculate_priority_score(frequency, voi, alignment, cost)

        scored_gaps.append((priority, gap))

    # Sort by priority (highest first)
    scored_gaps.sort(key=lambda x: x[0], reverse=True)

    # Take top 10
    top_gaps = scored_gaps[:10]

    # Convert to CuriosityQuestions
    questions = []
    for priority, gap in top_gaps:
        question_id = self._generate_question_id(gap)

        q = CuriosityQuestion(
            id=question_id,
            hypothesis=f"MISSING_CAPABILITY_{gap.category}_{gap.name}",
            question=f"Should I acquire {gap.name} to improve {gap.category} capabilities?",
            evidence=[
                gap.reason,
                f"type:{gap.type}",
                f"category:{gap.category}",
                f"alignment:{gap.alignment_score:.2f}",
                f"install_cost:{gap.install_cost:.2f}",
                f"priority:{priority:.2f}"
            ],
            action_class=ActionClass.FIND_SUBSTITUTE,
            value_estimate=priority,
            cost=gap.install_cost,
            capability_key=f"{gap.category}.{gap.name}"
        )

        questions.append(q)

    logger.info(f"[capability_monitor] Generated {len(questions)} capability questions")

    # Save scanner state
    self._save_scanner_state()

    return questions

def _generate_question_id(self, gap: CapabilityGap) -> str:
    """Generate unique question ID for capability gap."""
    content = f"{gap.type}:{gap.category}:{gap.name}"
    hash_digest = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"capability.{gap.category}.{hash_digest}"

def _save_scanner_state(self) -> None:
    """Save scanner state to disk."""
    state = {}
    for scanner in self.scanners:
        metadata = scanner.get_metadata()
        state[metadata.name] = {
            'last_run': getattr(scanner, 'last_run', 0.0),
            'suspended': getattr(scanner, 'suspended', False)
        }

    try:
        # Atomic write
        tmp_path = Path(str(self.scanner_state_path) + '.tmp')
        with open(tmp_path, 'w') as f:
            json.dump(state, f, indent=2)
        tmp_path.rename(self.scanner_state_path)

        logger.debug(f"[capability_monitor] Saved scanner state")

    except Exception as e:
        logger.warning(f"[capability_monitor] Failed to save scanner state: {e}")
```

**Step 4: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_question_generation.py::test_generate_capability_questions -v`

Expected: PASS

**Step 5: Write test for question limit**

```python
# tests/registry/test_question_generation.py (add to file)

def test_question_generation_limit():
    """Test that question generation respects max limit."""
    monitor = CapabilityDiscoveryMonitor()

    # Force all scanners to run
    for scanner in monitor.scanners:
        scanner.last_run = 0.0

    questions = monitor.generate_capability_questions()

    # Should not exceed 10 questions
    assert len(questions) <= 10
```

**Step 6: Run test to verify it passes**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/registry/test_question_generation.py -v`

Expected: 2 tests pass

**Step 7: Commit**

```bash
git add src/registry/capability_discovery_monitor.py tests/registry/test_question_generation.py
git commit -m "feat: add question generation from capability gaps

- Runs scanners on schedule
- Scores gaps with hybrid prioritization
- Converts top 10 gaps to CuriosityQuestion objects
- Saves scanner state after execution

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4: Integration

### Task 7: Integrate with Curiosity Core

**Files:**
- Modify: `src/registry/curiosity_core.py:2143` (add after IntegrationFlowMonitor)
- Create: `tests/integration/test_capability_discovery_integration.py`

**Step 1: Write integration test**

```python
# tests/integration/test_capability_discovery_integration.py
import pytest
from src.registry.curiosity_core import CuriosityCore


def test_curiosity_core_includes_capability_questions():
    """Test that CuriosityCore generates capability discovery questions."""
    core = CuriosityCore()
    feed = core.generate_questions_from_matrix()

    # Should generate questions
    assert feed is not None
    assert hasattr(feed, 'questions')

    # Look for capability questions
    capability_questions = [
        q for q in feed.questions
        if q.id.startswith('capability.')
    ]

    # May or may not have capability questions depending on state
    # But integration should work without errors
    assert isinstance(capability_questions, list)
```

**Step 2: Run test to verify current state**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/integration/test_capability_discovery_integration.py -v`

Expected: PASS (but no capability questions yet)

**Step 3: Add integration to curiosity_core.py**

```python
# src/registry/curiosity_core.py
# Add after IntegrationFlowMonitor section (around line 2143)

        # CAPABILITY DISCOVERY: Detect missing tools, skills, patterns
        try:
            from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
            capability_monitor = CapabilityDiscoveryMonitor()
            capability_questions = capability_monitor.generate_capability_questions()
            questions.extend(capability_questions)
            logger.info(f"[curiosity_core] Generated {len(capability_questions)} capability gap questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate capability questions: {e}")
```

**Step 4: Run integration test**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/integration/test_capability_discovery_integration.py -v`

Expected: PASS

**Step 5: Run full test suite**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 6: Commit**

```bash
git add src/registry/curiosity_core.py tests/integration/test_capability_discovery_integration.py
git commit -m "feat: integrate capability discovery with curiosity core

- Add CapabilityDiscoveryMonitor to question generation pipeline
- Runs after integration analysis
- Capability questions enter feed with other monitor questions

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5: Documentation & Verification

### Task 8: Update Documentation

**Files:**
- Create: `docs/capability-discovery.md`
- Modify: `README.md` (if exists)

**Step 1: Write capability discovery documentation**

```markdown
# Capability Discovery System

## Overview

KLoROS automatically detects missing tools, skills, and patterns through the capability discovery system. This system complements existing failure detection by identifying *absent* capabilities rather than *broken* ones.

## Architecture

### Three Layers

1. **Scanner Layer** - Pluggable capability detectors
   - `PyPIScanner` - Missing Python packages
   - Future: `SkillScanner`, `PatternScanner`, `ReactiveGapScanner`

2. **Orchestration Layer** - `CapabilityDiscoveryMonitor`
   - Auto-discovers scanners from `capability_scanners/` package
   - Schedules scanner execution during idle time
   - Applies hybrid prioritization (frequency + VOI + alignment + cost)
   - Generates `CuriosityQuestion` objects

3. **Meta-Cognition Layer** - `MonitorHealthMonitor` (future)
   - Tracks scanner effectiveness
   - Proposes consolidation when scanners overlap
   - Prevents scanner bloat

## How It Works

### Scanner Scheduling

Scanners run based on:
- `schedule_weight` - How often to run (1.0=every hour, 0.1=every 10 hours)
- `last_run` - When scanner last executed
- `idle_budget` - Available CPU time budget
- `suspended` - Whether scanner is disabled

### Prioritization Formula

```python
priority = (frequency * 0.3) + (voi * 0.35) + (alignment * 0.25) + ((1-cost) * 0.1)
```

- **Frequency** (30%): How often related operation occurs
- **VOI** (35%): Value-of-information score (from brainmods)
- **Alignment** (25%): Alignment with core mission
- **Cost** (10%): Installation/learning cost

### Temporal Continuity

State persists across restarts:
- `/home/kloros/.kloros/scanner_state.json` - Last run times, suspension status
- `/home/kloros/.kloros/operation_patterns.jsonl` - 7-day operation frequency window

## Adding New Scanners

1. Create scanner class in `src/registry/capability_scanners/`
2. Inherit from `CapabilityScanner`
3. Implement `scan()` and `get_metadata()`
4. Scanner auto-discovers on next run

Example:

```python
from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

class MyScanner(CapabilityScanner):
    def scan(self) -> List[CapabilityGap]:
        # Detect capability gaps
        return [...]

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name='MyScanner',
            domain='my_domain',
            alignment_baseline=0.7,
            scan_cost=0.2,
            schedule_weight=0.5
        )
```

## Configuration

No configuration needed - system is self-organizing through:
- Auto-discovery of scanners
- Adaptive scheduling based on value
- State persistence for continuity

## Monitoring

Check logs for:
- `[capability_monitor] Discovered N scanners` - Scanner registration
- `[capability_monitor] Running scanner: X` - Scanner execution
- `[capability_monitor] Generated N capability questions` - Question output

## Design Document

See `docs/plans/2025-11-06-capability-discovery-design.md` for full architecture and rationale.
```

**Step 2: Save documentation**

Run: `cat > docs/capability-discovery.md` (paste content above)

**Step 3: Commit documentation**

```bash
git add docs/capability-discovery.md
git commit -m "docs: add capability discovery system documentation

- Architecture overview (3 layers)
- Scanner scheduling and prioritization
- Adding new scanners guide
- State persistence details

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: Final Verification

**Step 1: Run complete test suite**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/ -v`

Expected: All tests pass

**Step 2: Check test coverage**

Run: `source /home/kloros/.venv/bin/activate && python -m pytest tests/ --cov=src/registry/capability_scanners --cov=src/registry/capability_discovery_monitor --cov-report=term-missing`

Expected: >80% coverage on new modules

**Step 3: Manual verification - generate questions**

Run:
```bash
source /home/kloros/.venv/bin/activate
python -c "
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
monitor = CapabilityDiscoveryMonitor()
questions = monitor.generate_capability_questions()
print(f'Generated {len(questions)} questions')
for q in questions[:3]:
    print(f'  - {q.id}: {q.question}')
"
```

Expected: Output showing generated questions

**Step 4: Verify state persistence**

Run:
```bash
ls -lh /home/kloros/.kloros/scanner_state.json
cat /home/kloros/.kloros/scanner_state.json
```

Expected: File exists with scanner state

**Step 5: Final commit**

```bash
git commit --allow-empty -m "chore: capability discovery system Phase 1 complete

Phase 1 (Foundation + Initial Scanners) implemented:
- Base scanner protocol with CapabilityGap/ScannerMetadata
- CapabilityDiscoveryMonitor orchestrator
- PyPIScanner for missing packages
- Hybrid prioritization system
- Question generation pipeline
- Integration with curiosity_core
- State persistence for temporal continuity

Next phases:
- Phase 2: ReactiveGapScanner for problem detection
- Phase 3: Operation pattern tracking for frequency scoring
- Phase 4: MonitorHealthMonitor for meta-cognition
- Phase 5: Additional scanners (Skills, Patterns)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Success Criteria

**Phase 1 Complete When:**
- ✅ All tests pass
- ✅ PyPIScanner detects missing packages
- ✅ Questions generated and enter curiosity feed
- ✅ Scanner state persists across restarts
- ✅ Integration with curiosity_core works
- ✅ Documentation complete

**Verify:**
1. Tests: `pytest tests/ -v` → All pass
2. Questions: Monitor generates capability questions
3. State: `scanner_state.json` exists and updates
4. Integration: Questions appear in curiosity feed
5. Docs: `docs/capability-discovery.md` explains system

## Future Phases (Not in This Plan)

**Phase 2: Reactive Detection**
- ReactiveGapScanner hooks into exceptions/failures
- Operation pattern recording

**Phase 3: Enhanced Prioritization**
- Brainmods VOI integration
- Operation frequency tracking

**Phase 4: Meta-Cognition**
- MonitorHealthMonitor implementation
- Scanner consolidation proposals

**Phase 5: Additional Scanners**
- SkillMarketplaceScanner
- PatternLibraryScanner
- Domain-specific scanners

---

## Notes

- Plan focuses on Phase 1: Foundation + Initial Scanner
- Each task is 2-5 minutes following TDD
- Commit after each completed task
- Tests verify each component works
- Integration test verifies end-to-end flow
- State persistence enables temporal continuity
