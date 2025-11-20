#!/usr/bin/env python3
"""MCP Developer CLI - Interactive introspection and testing tool.

Purpose:
    Provide command-line interface for MCP operations, introspection,
    and manual testing during development.

Commands:
    list        - List all discovered capabilities
    inspect     - Inspect specific capability details
    route       - Test routing for a goal
    graph       - Show capability graph structure
    health      - Check server and capability health
    policy      - Test policy evaluation
    simulate    - Simulate server failure/recovery
    snapshot    - Save current state snapshot

Usage:
    python3 /home/kloros/scripts/mcp_cli.py list
    python3 /home/kloros/scripts/mcp_cli.py route "search for recent memories"
    python3 /home/kloros/scripts/mcp_cli.py inspect memory.search
    python3 /home/kloros/scripts/mcp_cli.py graph --dot

Governance:
    - Tool-Integrity: Complete implementation with help text
    - SPEC-001: Respects resource budgets
    - D-REAM-Allowed-Stack: Python CLI, no prohibited utilities
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, "/home/kloros")

from src.mcp.integration import MCPIntegration
from src.mcp.capability_graph import HealthStatus


class MCPCli:
    """MCP Developer CLI tool.

    Purpose:
        Interactive command-line interface for MCP operations.
    """

    def __init__(self):
        """Initialize MCP CLI."""
        print("Initializing MCP...")
        self.mcp = MCPIntegration(enable_discovery=True)
        print(f"✓ Connected to {len(self.mcp.client.servers)} servers\n")

    def cmd_list(self, args):
        """List all capabilities."""
        print("=== CAPABILITY INVENTORY ===\n")
        print(self.mcp.introspect_capabilities())

    def cmd_inspect(self, args):
        """Inspect specific capability."""
        capability_id = args.capability_id
        node = self.mcp.graph.get_node(capability_id)

        if not node:
            print(f"✗ Capability '{capability_id}' not found")
            return

        print(f"=== CAPABILITY: {capability_id} ===\n")
        print(f"Name: {node.name}")
        print(f"Description: {node.description}")
        print(f"Server: {node.source_server}")
        print(f"Version: {node.version}")
        print(f"Enabled: {'✓' if node.enabled else '✗'}")
        print(f"Health: {node.health_status.value}")
        print(f"\nBudget:")
        print(f"  Max time: {node.budget.max_time_ms}ms")
        print(f"  Max CPU: {node.budget.max_cpu_pct}%")
        print(f"  Max memory: {node.budget.max_memory_mb}MB")

        if node.depends_on:
            print(f"\nDependencies: {', '.join(node.depends_on)}")

        dependents = self.mcp.graph.get_dependents(capability_id)
        if dependents:
            print(f"Dependents: {', '.join(dependents)}")

        print(f"\nError count: {node.error_count}")

    def cmd_route(self, args):
        """Test routing for a goal."""
        goal = args.goal
        user_id = args.user or "operator"

        print(f"=== ROUTING: {goal} ===\n")

        decision = self.mcp.route_capability(goal, user_id)

        print(f"Selected: {decision.capability_id}")
        print(f"Rationale: {decision.rationale}")

        if decision.policy_decision:
            print(f"\nPolicy Decision: {'✓ ALLOWED' if decision.policy_decision.allowed else '✗ DENIED'}")
            if decision.policy_decision.violations:
                print(f"Violations:")
                for violation in decision.policy_decision.violations:
                    print(f"  - {violation}")
            if decision.policy_decision.budget_enforced:
                budget = decision.policy_decision.budget_enforced
                print(f"\nBudget Enforced:")
                print(f"  Max time: {budget.get('max_time_ms')}ms")
                print(f"  Max memory: {budget.get('max_memory_mb')}MB")

        if decision.alternatives_considered:
            print(f"\nAlternatives Considered:")
            for alt in decision.alternatives_considered:
                print(f"  - {alt['capability_id']} (score: {alt['score']:.1f})")

        if decision.fallback_chain:
            print(f"\nFallback Chain: {' → '.join(decision.fallback_chain)}")

    def cmd_graph(self, args):
        """Show capability graph structure."""
        print("=== CAPABILITY GRAPH ===\n")

        summary = self.mcp.graph.get_summary()
        print(f"Total capabilities: {summary['total_capabilities']}")
        print(f"Enabled: {summary['enabled']}")
        print(f"Disabled: {summary['disabled']}")
        print(f"Has cycles: {'✗ YES' if summary['has_cycles'] else '✓ NO'}")
        print(f"Servers: {summary['servers']}")

        if args.dot:
            print("\n=== DOT FORMAT ===\n")
            print("digraph capabilities {")
            print("  rankdir=LR;")
            print("  node [shape=box];")

            for node in self.mcp.graph.nodes.values():
                color = "green" if node.enabled else "gray"
                print(f'  "{node.capability_id}" [color={color}];')

                for dep in node.depends_on:
                    print(f'  "{node.capability_id}" -> "{dep}";')

            print("}")

        if args.topo:
            print("\n=== TOPOLOGICAL ORDER ===\n")
            try:
                order = self.mcp.graph.topological_sort()
                for i, cap_id in enumerate(order, 1):
                    print(f"{i}. {cap_id}")
            except ValueError as e:
                print(f"✗ Cannot compute: {e}")

    def cmd_health(self, args):
        """Check server and capability health."""
        print("=== HEALTH STATUS ===\n")

        # Server health
        print("Servers:")
        for server_id, server in self.mcp.client.servers.items():
            status = "✓" if server.connected else "✗"
            print(f"  {status} {server.manifest.name} ({server.health_status})")

        # Capability health
        print("\nCapabilities by Health Status:")

        by_status = {status: [] for status in HealthStatus}
        for node in self.mcp.graph.nodes.values():
            by_status[node.health_status].append(node.capability_id)

        for status, caps in by_status.items():
            if caps:
                symbol = "✓" if status == HealthStatus.OK else "!" if status == HealthStatus.DEGRADED else "✗"
                print(f"\n{symbol} {status.value}:")
                for cap in caps:
                    print(f"    {cap}")

    def cmd_policy(self, args):
        """Test policy evaluation."""
        capability_id = args.capability_id
        user_id = args.user or "operator"
        input_text = args.input or ""

        print(f"=== POLICY EVALUATION ===\n")
        print(f"Capability: {capability_id}")
        print(f"User: {user_id}")
        print(f"Input: {input_text or '(none)'}\n")

        decision = self.mcp.policy.evaluate(capability_id, user_id, input_text)

        print(f"Decision: {'✓ ALLOWED' if decision.allowed else '✗ DENIED'}")

        if decision.violations:
            print(f"\nViolations:")
            for violation in decision.violations:
                print(f"  - {violation}")

        if decision.budget_enforced:
            print(f"\nBudget Enforced:")
            budget = decision.budget_enforced
            print(f"  Max time: {budget.get('max_time_ms')}ms")
            print(f"  Max CPU: {budget.get('max_cpu_pct')}%")
            print(f"  Max memory: {budget.get('max_memory_mb')}MB")

    def cmd_simulate(self, args):
        """Simulate server failure/recovery."""
        capability_id = args.capability_id
        action = args.action

        print(f"=== SIMULATING {action.upper()} ===\n")
        print(f"Capability: {capability_id}")

        node = self.mcp.graph.get_node(capability_id)
        if not node:
            print(f"✗ Capability not found")
            return

        print(f"Before: {node.health_status.value}, enabled={node.enabled}")

        if action == "fail":
            self.mcp.graph.mark_disabled(capability_id, reason="Simulated failure (CLI)")
        elif action == "recover":
            self.mcp.graph.mark_enabled(capability_id)

        node = self.mcp.graph.get_node(capability_id)
        print(f"After: {node.health_status.value}, enabled={node.enabled}")

        # Show routing impact
        print("\n=== ROUTING IMPACT ===")
        decision = self.mcp.route_capability(f"use {capability_id}", "operator")
        print(f"Would route to: {decision.capability_id}")
        if decision.fallback_chain:
            print(f"Fallbacks available: {', '.join(decision.fallback_chain)}")

    def cmd_snapshot(self, args):
        """Save current state snapshot."""
        output_path = args.output or "/home/kloros/artifacts/mcp-reports/snapshot_manual.json"

        print(f"=== SAVING SNAPSHOT ===\n")
        print(f"Output: {output_path}")

        self.mcp.save_snapshot(output_path)

        # Show summary
        with open(output_path) as f:
            snapshot = json.load(f)

        print(f"\n✓ Snapshot saved")
        print(f"Timestamp: {snapshot['timestamp']}")
        print(f"Capabilities: {len(snapshot['capabilities'])}")
        print(f"Total servers: {snapshot['graph_summary']['servers']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Developer CLI - Introspection and testing tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list command
    subparsers.add_parser("list", help="List all capabilities")

    # inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect specific capability")
    inspect_parser.add_argument("capability_id", help="Capability ID to inspect")

    # route command
    route_parser = subparsers.add_parser("route", help="Test routing for a goal")
    route_parser.add_argument("goal", help="Goal to route")
    route_parser.add_argument("--user", help="User ID (default: operator)")

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Show capability graph")
    graph_parser.add_argument("--dot", action="store_true", help="Output in DOT format")
    graph_parser.add_argument("--topo", action="store_true", help="Show topological order")

    # health command
    subparsers.add_parser("health", help="Check server and capability health")

    # policy command
    policy_parser = subparsers.add_parser("policy", help="Test policy evaluation")
    policy_parser.add_argument("capability_id", help="Capability ID")
    policy_parser.add_argument("--user", help="User ID (default: operator)")
    policy_parser.add_argument("--input", help="Input text to evaluate")

    # simulate command
    simulate_parser = subparsers.add_parser("simulate", help="Simulate failure/recovery")
    simulate_parser.add_argument("capability_id", help="Capability ID")
    simulate_parser.add_argument("action", choices=["fail", "recover"], help="Action to simulate")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Save state snapshot")
    snapshot_parser.add_argument("--output", help="Output path (default: artifacts/mcp-reports/snapshot_manual.json)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize CLI
    cli = MCPCli()

    # Dispatch command
    command_map = {
        "list": cli.cmd_list,
        "inspect": cli.cmd_inspect,
        "route": cli.cmd_route,
        "graph": cli.cmd_graph,
        "health": cli.cmd_health,
        "policy": cli.cmd_policy,
        "simulate": cli.cmd_simulate,
        "snapshot": cli.cmd_snapshot,
    }

    handler = command_map.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()
