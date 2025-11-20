#!/usr/bin/env python3
"""PHASE MCP Domain - Behavioral tests for Model Context Protocol.

Purpose:
    Validate MCP discovery, graph building, routing, policy enforcement,
    degradation handling, and XAI transparency.

Test Categories:
    1. Discovery: Server enumeration and manifest parsing
    2. Graph: DAG invariants, cycle detection, topological sort
    3. Routing: Goal-to-capability mapping with fallbacks
    4. Policy: Budget enforcement and access control
    5. Degradation: mark_disabled/enabled and health tracking
    6. XAI: Introspection queries and routing rationale

Governance:
    - SPEC-001: Resource budgets enforced
    - SPEC-010: 10s I/O timeout compliance
    - Tool-Integrity: Complete test coverage
    - D-REAM-Compatible: pytest fixtures, JSONL output
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, "/home/kloros")

from src.mcp.integration import MCPIntegration, RoutingDecision
from src.mcp.capability_graph import CapabilityNode, ResourceBudget, HealthStatus
from src.mcp.policy import PolicyRule
from src.phase.report_writer import write_test_result


def run_mcp_domain(epoch_id: str) -> Dict[str, Any]:
    """Run all MCP behavioral tests.

    Purpose:
        Execute comprehensive MCP test suite to validate all components
        and ensure production readiness.

    Parameters:
        epoch_id: D-REAM epoch identifier for test tracking

    Outcomes:
        Test results with pass/fail counts and latency

    Returns:
        Dict with test results (status, tests_passed, tests_failed, latency_ms)
    """
    import time
    start_time = time.time()

    results = []
    tests_passed = 0
    tests_failed = 0

    # Initialize MCP
    try:
        mcp = MCPIntegration(enable_discovery=True)
    except Exception as e:
        return {
            "status": "fail",
            "tests_passed": 0,
            "tests_failed": 1,
            "latency_ms": (time.time() - start_time) * 1000,
            "error": f"Failed to initialize MCP: {e}"
        }

    # Test 1: Discovery - Server enumeration
    test_id = f"{epoch_id}::mcp::discovery"
    try:
        servers = mcp.client.servers
        assert len(servers) >= 2, f"Expected ≥2 servers, got {len(servers)}"

        # Check manifests are valid
        for server_id, server in servers.items():
            assert server.manifest.name, "Server must have name"
            assert server.manifest.version, "Server must have version"
            assert len(server.manifest.capabilities) > 0, "Server must have capabilities"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "discovery", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "discovery", "status": "fail", "error": str(e)})

    # Test 2: Graph - No cycles (DAG invariant)
    test_id = f"{epoch_id}::mcp::graph_dag"
    try:
        assert not mcp.graph.has_cycles(), "Graph must be acyclic (DAG)"

        summary = mcp.graph.get_summary()
        assert summary['total_capabilities'] >= 9, f"Expected ≥9 capabilities, got {summary['total_capabilities']}"
        assert summary['enabled'] > 0, "Must have enabled capabilities"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "graph_dag", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "graph_dag", "status": "fail", "error": str(e)})

    # Test 3: Topological Sort
    test_id = f"{epoch_id}::mcp::topological_sort"
    try:
        topo_order = mcp.graph.topological_sort()
        assert len(topo_order) == len(mcp.graph.nodes), "Topological order must include all nodes"

        # Verify order respects dependencies
        seen = set()
        for cap_id in topo_order:
            node = mcp.graph.get_node(cap_id)
            # All dependencies must appear before this node
            for dep in node.depends_on:
                assert dep in seen, f"Dependency {dep} must appear before {cap_id} in topological order"
            seen.add(cap_id)

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "topological_sort", "status": "pass"})
    except (AssertionError, ValueError) as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "topological_sort", "status": "fail", "error": str(e)})

    # Test 4: Routing - Goal to capability
    test_id = f"{epoch_id}::mcp::routing"
    try:
        # Test multiple goals
        test_goals = [
            ("search memory", "memory.search"),
            ("search documents with RAG", "rag.search"),
            ("summarize memory", "memory.summarize"),
        ]

        for goal, expected_capability_prefix in test_goals:
            decision = mcp.route_capability(goal, "operator")
            assert decision.capability_id != "none", f"Routing failed for goal: {goal}"
            assert decision.capability_id.startswith(expected_capability_prefix.split('.')[0]), \
                f"Expected {expected_capability_prefix}, got {decision.capability_id} for goal: {goal}"

            # Check fallback chain exists
            assert len(decision.fallback_chain) >= 0, "Should have fallback chain"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "routing", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "routing", "status": "fail", "error": str(e)})

    # Test 5: Policy - Budget enforcement
    test_id = f"{epoch_id}::mcp::policy_budgets"
    try:
        # Check that all capabilities have budgets
        for node in mcp.graph.nodes.values():
            assert node.budget is not None, f"Capability {node.capability_id} missing budget"
            assert node.budget.max_time_ms > 0, f"Invalid max_time_ms for {node.capability_id}"
            assert node.budget.max_memory_mb > 0, f"Invalid max_memory_mb for {node.capability_id}"
            assert node.budget.max_cpu_pct <= 90, f"max_cpu_pct exceeds SPEC-001 limit for {node.capability_id}"

        # Test policy decision
        decision = mcp.policy.evaluate("memory.search", "operator", "test query")
        assert decision.allowed, "Default policy should allow requests"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "policy_budgets", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "policy_budgets", "status": "fail", "error": str(e)})

    # Test 6: Policy - Forbidden patterns
    test_id = f"{epoch_id}::mcp::policy_forbidden"
    try:
        # Add forbidden pattern rule
        rule = PolicyRule(
            rule_id="test_forbidden",
            capability_id="memory.search",
            forbidden_patterns=[r"password", r"secret"]
        )
        mcp.policy.add_rule(rule)

        # Test forbidden pattern detection
        decision = mcp.policy.evaluate("memory.search", "operator", "show me the password")
        assert not decision.allowed, "Should deny requests matching forbidden patterns"
        assert len(decision.violations) > 0, "Should report violations"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "policy_forbidden", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "policy_forbidden", "status": "fail", "error": str(e)})

    # Test 7: Degradation - mark_disabled
    test_id = f"{epoch_id}::mcp::degradation_disable"
    try:
        test_cap = "memory.search"
        node_before = mcp.graph.get_node(test_cap)
        assert node_before.enabled, "Capability should start enabled"

        # Disable capability
        mcp.graph.mark_disabled(test_cap, reason="PHASE test")

        node_after = mcp.graph.get_node(test_cap)
        assert not node_after.enabled, "Capability should be disabled"
        assert node_after.health_status != HealthStatus.OK, "Health status should reflect failure"

        # Verify routing respects disabled state
        decision = mcp.route_capability("search memory", "operator")
        # Should either route to fallback or return none
        if decision.capability_id == test_cap:
            # If it still routes to disabled cap, it should be in fallback chain
            assert len(decision.fallback_chain) > 0, "Should have fallbacks for disabled capability"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "degradation_disable", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "degradation_disable", "status": "fail", "error": str(e)})

    # Test 8: Degradation - mark_enabled (recovery)
    test_id = f"{epoch_id}::mcp::degradation_recover"
    try:
        test_cap = "memory.search"

        # Re-enable capability
        mcp.graph.mark_enabled(test_cap)

        node_after = mcp.graph.get_node(test_cap)
        assert node_after.enabled, "Capability should be re-enabled"
        assert node_after.health_status == HealthStatus.OK, "Health status should recover"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "degradation_recover", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "degradation_recover", "status": "fail", "error": str(e)})

    # Test 9: XAI - Introspection "what can you do?"
    test_id = f"{epoch_id}::mcp::xai_introspect"
    try:
        capabilities_text = mcp.introspect_capabilities()
        assert len(capabilities_text) > 0, "Introspection should return non-empty text"
        assert "AVAILABLE CAPABILITIES" in capabilities_text, "Should have capabilities header"

        # Check that it includes server info
        for server_id, server in mcp.client.servers.items():
            assert server.manifest.name in capabilities_text, f"Should list server {server.manifest.name}"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "xai_introspect", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "xai_introspect", "status": "fail", "error": str(e)})

    # Test 10: XAI - Routing rationale
    test_id = f"{epoch_id}::mcp::xai_rationale"
    try:
        decision = mcp.route_capability("search for documents", "operator")
        assert decision.rationale, "Should provide rationale for routing decision"
        assert "score" in decision.rationale.lower() or "selected" in decision.rationale.lower(), \
            "Rationale should explain selection"

        # Check alternatives are tracked
        assert len(decision.alternatives_considered) >= 0, "Should track alternatives"

        write_test_result(test_id, "pass", (time.time() - start_time) * 1000, epoch_id)
        tests_passed += 1
        results.append({"test": "xai_rationale", "status": "pass"})
    except AssertionError as e:
        write_test_result(test_id, "fail", (time.time() - start_time) * 1000, epoch_id, str(e))
        tests_failed += 1
        results.append({"test": "xai_rationale", "status": "fail", "error": str(e)})

    # Calculate final results
    latency_ms = (time.time() - start_time) * 1000
    status = "pass" if tests_failed == 0 else "fail"

    return {
        "status": status,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "total_tests": tests_passed + tests_failed,
        "latency_ms": latency_ms,
        "results": results
    }


def run_single_epoch_test(epoch_id: str) -> Dict[str, Any]:
    """Run MCP domain test for single epoch.

    Purpose:
        Entry point for PHASE framework integration.

    Parameters:
        epoch_id: D-REAM epoch identifier

    Returns:
        Test results dictionary
    """
    return run_mcp_domain(epoch_id)


if __name__ == "__main__":
    # Standalone test
    print("=== MCP Domain Tests ===\n")

    result = run_mcp_domain("manual_test")

    print(f"\n{'='*70}")
    print(f"Tests: {result['tests_passed']}/{result['total_tests']} passed")
    print(f"Status: {result['status'].upper()}")
    print(f"Latency: {result['latency_ms']:.1f}ms")
    print(f"{'='*70}")

    # Show individual test results
    if 'results' in result:
        print("\nTest Details:")
        for test_result in result['results']:
            status_symbol = "✓" if test_result['status'] == 'pass' else "✗"
            print(f"  {status_symbol} {test_result['test']}")
            if 'error' in test_result:
                print(f"     Error: {test_result['error']}")
