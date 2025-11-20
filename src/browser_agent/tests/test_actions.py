"""Integration tests for browser agent actions."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from browser_agent.agent.executor import BrowserExecutor
from browser_agent.agent.petri_policy import PetriPolicy

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # Mock pytest decorator
    class pytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func

async def test_basic_navigation():
    """Test basic navigation."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [{"type": "wait", "time_ms": 500}]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        assert result["steps"][0]["success"]

async def test_extract_text():
    """Test text extraction."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [
            {"type": "extract", "selector": "h1", "args": {"var_name": "title"}}
        ]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        assert result["steps"][0]["success"]
        assert "title" in result["vars"]
        assert "Example" in result["vars"]["title"]

async def test_evaluate_js():
    """Test JavaScript evaluation."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [
            {"type": "evaluate", "script": "document.title", "args": {"var_name": "page_title"}}
        ]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        assert result["steps"][0]["success"]
        assert "page_title" in result["vars"]

async def test_screenshot():
    """Test screenshot capture."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]
    policy.screenshot_every_step = False  # Only test explicit screenshot

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [
            {"type": "screenshot", "path": "test_screenshot.png"}
        ]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        assert result["steps"][0]["success"]
        # Check screenshot exists
        trace_dir = result["trace_dir"]
        screenshot_path = os.path.join(trace_dir, "test_screenshot.png")
        assert os.path.exists(screenshot_path)

async def test_scroll():
    """Test scrolling."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [
            {"type": "scroll", "direction": "down", "amount": 500},
            {"type": "scroll", "direction": "top"}
        ]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        assert result["steps"][0]["success"]
        assert result["steps"][1]["success"]

async def test_petri_policy_domain_blocking():
    """Test PETRI policy blocks disallowed domains."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]

    plan = {
        "meta": {"start_url": "https://google.com"},  # Not allowed
        "actions": []
    }

    async with BrowserExecutor(policy=policy) as executor:
        try:
            await executor.run_plan(plan)
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass  # Expected

async def test_action_limit():
    """Test action limit enforcement."""
    policy = PetriPolicy()
    policy.allow_domains = ["example.com"]
    policy.max_actions = 2

    plan = {
        "meta": {"start_url": "https://example.com"},
        "actions": [
            {"type": "wait", "time_ms": 100},
            {"type": "wait", "time_ms": 100},
            {"type": "wait", "time_ms": 100},  # Should not execute
        ]
    }

    async with BrowserExecutor(policy=policy) as executor:
        result = await executor.run_plan(plan)
        # Only first 2 actions should execute
        assert len(result["steps"]) == 2

if __name__ == "__main__":
    # Run basic smoke test
    print("Running browser agent smoke tests...")
    asyncio.run(test_basic_navigation())
    print("✅ Basic navigation")
    asyncio.run(test_extract_text())
    print("✅ Text extraction")
    asyncio.run(test_evaluate_js())
    print("✅ JavaScript evaluation")
    asyncio.run(test_screenshot())
    print("✅ Screenshot capture")
    asyncio.run(test_scroll())
    print("✅ Scrolling")
    asyncio.run(test_petri_policy_domain_blocking())
    print("✅ PETRI domain blocking")
    asyncio.run(test_action_limit())
    print("✅ Action limit enforcement")
    print("\n🎉 All tests passed!")
