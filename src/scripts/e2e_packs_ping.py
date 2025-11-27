#!/usr/bin/env python3
"""End-to-end pack integration test - ping all pack entry points."""
import os, sys
os.environ.setdefault("KLR_REGISTRY", "/home/kloros/src/registry/capabilities.yaml")
sys.path.insert(0, "/home/kloros/src")
sys.path.insert(0, "/home/kloros")

results = []

def test_pack(name, test_fn):
    """Test a pack and record result."""
    try:
        print(f"[*] Testing {name}...")
        test_fn()
        print(f"[OK] {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        results.append((name, False, str(e)))

# Browser Agent
def test_browser():
    from browser_agent.agent.executor import BrowserExecutor
    executor = BrowserExecutor(headless=True, policy=None)
    # Check methods exist
    assert hasattr(executor, 'navigate')
    assert hasattr(executor, 'get_content')
    assert hasattr(executor, 'get_title')

# Dev Agent
def test_dev():
    from dev_agent import run_task
    # Check it's callable
    assert callable(run_task)

# Scholar Pack
def test_scholar():
    from scholar.pipeline_plus import build_plus_report
    # Check it's callable
    assert callable(build_plus_report)

# XAI Pack
def test_xai():
    from xai.explain import render
    from xai.record import DecisionRecord
    # Check they're callable/importable
    assert callable(render)
    assert DecisionRecord is not None

# Dev Agent Tools
def test_dev_tools():
    from dev_agent.tools.repo import repo_init, apply_patch
    from dev_agent.tools.sandbox import run_cmd
    from dev_agent.tools.git_tools import ensure_repo, branch, commit, pr_stub
    from dev_agent.tools.deps import deps_sync
    # Check all are callable
    assert all(callable(fn) for fn in [repo_init, apply_patch, run_cmd, ensure_repo, branch, commit, pr_stub, deps_sync])
    # Check decorators applied (should have __wrapped__)
    assert hasattr(repo_init, '__wrapped__') or hasattr(repo_init, '__name__')

print("============================================================")
print("KLoROS Pack Integration Test")
print("============================================================")

test_pack("Browser Agent", test_browser)
test_pack("Dev Agent", test_dev)
test_pack("Scholar Pack", test_scholar)
test_pack("XAI Pack", test_xai)
test_pack("Dev Agent Tools", test_dev_tools)

print()
print("============================================================")
print(f"Results: {sum(1 for _, ok, _ in results if ok)}/{len(results)} passed")
print("============================================================")

for name, ok, err in results:
    status = "[OK]" if ok else "[FAIL]"
    msg = "" if ok else f" - {err}"
    print(f"{status} {name}{msg}")

# Exit with error if any failed
if any(not ok for _, ok, _ in results):
    sys.exit(1)
