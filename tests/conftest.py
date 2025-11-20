"""Pytest configuration for KLoROS tests.

Prevents resource exhaustion during parallel test execution (pytest-xdist).

Root Cause Analysis:
- KLoROS.__init__() loads 12GB+ ML models and initializes audio hardware
- PHASE runs with `-n auto` (8-16 workers) × 3 seed sweeps
- 24-48 simultaneous KLoROS() instantiations → 288-576GB memory allocation attempt
- Workers crash during resource stampede

Solution:
- Use pytest-xdist file-level locking for tests that instantiate KLoROS
- Force single-worker execution for heavy integration tests
- Preserve parallel execution for lightweight unit tests
- EARLY init guard in pytest_configure() to prevent crashes before fixtures run
"""

import pytest
import os
import sys
import time
import faulthandler
from pathlib import Path
from filelock import FileLock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# --- Early, cross-worker init guard (runs before any fixture) ---
_KLOROS_INIT_DONE = False

def _kloros_global_init_once():
    """
    Early, one-time initialization guard for KLoROS tests.

    Runs in pytest_configure() (before any fixtures) to serialize
    heavy initialization across all xdist workers. Uses a file lock
    and flag to ensure only ONE worker performs expensive setup.

    This addresses crashes that happen BEFORE fixture execution during
    module import or early initialization.
    """
    global _KLOROS_INIT_DONE

    if _KLOROS_INIT_DONE:
        return

    # Get shared temp directory - try multiple methods
    base_dir = None

    # Method 1: PYTEST_XDIST_WORKER env (set by xdist)
    if os.getenv("PYTEST_XDIST_WORKER"):
        # Workers share a parent temp dir
        base_dir = Path("/tmp/pytest-of-kloros")
        base_dir.mkdir(parents=True, exist_ok=True)

    # Method 2: Fall back to project root
    if not base_dir or not base_dir.exists():
        base_dir = Path("/home/kloros")

    lock_path = base_dir / ".kloros_early_init.lock"
    flag_path = base_dir / ".kloros_early_init.done"

    # Fast path: if another worker already completed init
    if flag_path.exists():
        _KLOROS_INIT_DONE = True
        print(f"[KLOROS_EARLY_INIT] Worker {os.getpid()} skipping - init already done", file=sys.stderr)
        return

    print(f"[KLOROS_EARLY_INIT] Worker {os.getpid()} attempting lock acquisition at {lock_path}", file=sys.stderr)

    try:
        with FileLock(str(lock_path), timeout=300):
            # Double-check after acquiring lock
            if flag_path.exists():
                _KLOROS_INIT_DONE = True
                print(f"[KLOROS_EARLY_INIT] Worker {os.getpid()} - another worker completed init", file=sys.stderr)
                return

            print(f"[KLOROS_EARLY_INIT] Worker {os.getpid()} performing one-time init", file=sys.stderr)

            # Set test-safe environment variables
            os.environ.setdefault("KLR_TEST_MODE", "1")
            os.environ.setdefault("PIPER_NO_AUDIO", "1")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

            # Enable crash debugging
            faulthandler.enable(all_threads=True, file=sys.stderr)

            # Minimal bootstrap - just ensure critical paths exist
            try:
                # Create expected directories
                kloros_root = Path("/home/kloros")
                (kloros_root / ".kloros").mkdir(exist_ok=True)
                (kloros_root / ".kloros" / "logs").mkdir(exist_ok=True)
                (kloros_root / "logs").mkdir(exist_ok=True)

                # Pre-import heavy modules to avoid import lock contention
                print(f"[KLOROS_EARLY_INIT] Pre-importing heavy modules...", file=sys.stderr)
                try:
                    import numpy
                    import torch
                except ImportError as e:
                    print(f"[KLOROS_EARLY_INIT] Warning: Could not pre-import modules: {e}", file=sys.stderr)

                print(f"[KLOROS_EARLY_INIT] Init complete", file=sys.stderr)

            except Exception as e:
                print(f"[KLOROS_EARLY_INIT] FAILED: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                raise

            # Write flag to signal completion
            flag_path.write_text(f"{time.time()}:{os.getpid()}")
            _KLOROS_INIT_DONE = True
            print(f"[KLOROS_EARLY_INIT] Worker {os.getpid()} completed init, flag written", file=sys.stderr)

    except Exception as e:
        print(f"[KLOROS_EARLY_INIT] CRITICAL ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        # Don't raise - allow tests to run, they'll fail individually if needed


def pytest_configure(config):
    """Register custom markers and perform early initialization.

    This runs BEFORE any fixtures or tests, making it the ideal place
    to serialize expensive one-time setup across xdist workers.
    """
    # Make tests safe by default across all xdist workers
    os.environ.setdefault("KLR_TEST_MODE", "1")
    os.environ.setdefault("PIPER_NO_AUDIO", "1")

    # Perform early init guard FIRST
    _kloros_global_init_once()

    # Then register markers (original functionality)
    config.addinivalue_line(
        "markers",
        "serial: Run test serially (one at a time across all workers) to avoid resource contention"
    )
    config.addinivalue_line(
        "markers",
        "kloros_init: Test instantiates KLoROS() - requires serialization"
    )


def pytest_sessionstart(session):
    """Ensure pre-stubs in tests/sitecustomize.py are loaded before any project code.

    This hooks runs once per test session (before collection).
    Forces import of sitecustomize to pre-stub heavy modules across all workers.
    """
    try:
        import tests.sitecustomize  # noqa: F401
        print("[test_init] sitecustomize loaded - heavy modules pre-stubbed", file=sys.stderr)
    except Exception as e:
        # Non-fatal: the test mode guard in kloros_voice.py prevents heavy loads anyway
        print(f"[test_init] sitecustomize import failed (non-fatal): {e}", file=sys.stderr)


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests that instantiate KLoROS for serial execution."""
    for item in items:
        # Check if test file or test function instantiates KLoROS
        if _test_needs_serialization(item):
            # Run all init-heavy tests on one worker to prevent OOM crashes
            item.add_marker(pytest.mark.xdist_group("kloros_init"))


def _test_needs_serialization(item):
    """Determine if test requires serialization to avoid resource stampede.

    Tests are marked for serialization if they:
    1. Are in test_smoke.py or test_calibration.py (known KLoROS() instantiators)
    2. Have "VoiceLoop" or "Integration" in their name
    3. Explicitly marked with @pytest.mark.kloros_init
    """
    # Check explicit marker
    if item.get_closest_marker("kloros_init"):
        return True

    # Check file path
    fspath = str(item.fspath)
    if "test_smoke.py" in fspath or "test_calibration.py" in fspath:
        return True

    # Check test name
    if "VoiceLoop" in item.name or "Integration" in item.name:
        return True

    return False


@pytest.fixture(scope="session")
def worker_id(request):
    """Get the xdist worker ID (gw0, gw1, etc) or 'master' if not using xdist."""
    if hasattr(request.config, 'workerinput'):
        return request.config.workerinput['workerid']
    return 'master'


# pytest-xdist locking mechanism
@pytest.fixture(scope="function")
def kloros_init_lock(tmp_path_factory, worker_id):
    """File-based lock to serialize KLoROS instantiation across all xdist workers.

    This prevents the resource stampede where 24-48 workers try to:
    - Load 12GB ML models simultaneously
    - Initialize audio devices
    - Spawn MCP servers
    - Start threading subsystems

    Usage:
        def test_piper_run(kloros_init_lock):
            # Lock is automatically acquired here
            from src.kloros_voice import KLoROS
            k = KLoROS()
            # Only ONE worker can be inside KLoROS.__init__() at a time

    NOTE: This fixture runs AFTER pytest_configure()'s early init guard,
    providing a second layer of protection during actual test execution.
    """
    if worker_id == 'master':
        # Not running with xdist, no locking needed
        yield
        return

    # Get shared temp directory accessible to all workers
    root_tmp_dir = tmp_path_factory.getbasetemp().parent

    # Create a lock file shared across all workers
    lock_file = root_tmp_dir / "kloros_init.lock"

    # Use pytest-xdist's file locking with timeout
    from filelock import FileLock, Timeout

    # Timeout: Max 300s (5 min) to wait for lock
    # KLoROS init typically takes 3-10s, so 5 min is generous
    lock = FileLock(str(lock_file), timeout=300)

    worker_name = worker_id
    print(f"[{worker_name}] Attempting to acquire lock: {lock_file}", file=sys.stderr)
    start = time.time()

    try:
        with lock:
            elapsed = time.time() - start
            print(f"[{worker_name}] Lock acquired after {elapsed:.2f}s", file=sys.stderr)
            # Only ONE worker can hold this lock at a time
            # Others will wait until the lock is released
            yield
            print(f"[{worker_name}] Lock released", file=sys.stderr)
    except Timeout:
        # If we can't get lock in 5 minutes, something is wrong
        # Better to fail fast than hang forever
        raise RuntimeError(
            f"Failed to acquire KLoROS init lock after 300s. "
            f"Another worker may be stuck or crashed during KLoROS initialization. "
            f"Check {lock_file} and running processes."
        )

# --- No-audio Piper stub for CI testing ---
import contextlib

@contextlib.contextmanager
def _no_device_piper():
    """
    Configure Piper to run in no-audio mode for CI/test environments.
    
    This allows Piper tests to run without real audio hardware,
    preventing device conflicts and flakiness during parallel execution.
    """
    import os
    os.environ["PIPER_NO_AUDIO"] = "1"
    os.environ.setdefault("PIPER_OUTPUT_MODE", "file")  # write to tmp wav instead of device
    yield


@pytest.fixture(scope="function")
def piper_stub(tmp_path):
    """Fixture to enable no-audio Piper testing.
    
    Usage:
        def test_piper_run(..., piper_stub):
            # Piper will write to files instead of audio device
            ...
    """
    os.environ["PIPER_TMPDIR"] = str(tmp_path)
    with _no_device_piper():
        yield tmp_path
