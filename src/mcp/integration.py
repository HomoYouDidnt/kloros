#!/usr/bin/env python3
"""MCP Integration Layer - Wire MCP into KLoROS runtime.

Purpose:
    Connect MCP client, capability graph, and policy engine to provide
    full capability introspection with "what/why/when" transparency.

Outcomes:
    - Unified MCP system integrated with KLoROS
    - Discovery, routing, policy enforcement
    - XAI introspection queries

Governance:
    - SPEC-001: Resource budgets enforced
    - SPEC-009: Registered in capabilities.yaml
    - Tool-Integrity: Complete implementation
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

from .client import MCPClient, MCPServer, MCPServerManifest
from .capability_graph import CapabilityGraph, CapabilityNode, ResourceBudget, HealthStatus
from .policy import PolicyEngine, PolicyRule, PolicyDecision, DataClass

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Result of capability routing with XAI trace.

    Attributes:
        capability_id: Selected capability
        rationale: Why this capability was chosen
        alternatives_considered: Other capabilities that were evaluated
        policy_decision: Policy evaluation result
        fallback_chain: Ordered list of fallback capabilities
    """
    capability_id: str
    rationale: str
    alternatives_considered: List[Dict[str, Any]] = field(default_factory=list)
    policy_decision: Optional[PolicyDecision] = None
    fallback_chain: List[str] = field(default_factory=list)


class MCPIntegration:
    """Unified MCP system for KLoROS.

    Purpose:
        Provide complete MCP functionality: discovery, graph building,
        policy enforcement, routing, and XAI introspection.

    Parameters:
        manifest_dir: Directory containing MCP server manifests
        enable_discovery: Whether to auto-discover servers on init
        timeout_sec: I/O timeout (SPEC-010: max 10s)

    Outcomes:
        - Discovered MCP servers
        - Built capability graph
        - Policy engine configured
        - XAI queries available

    Example:
        >>> mcp = MCPIntegration()
        >>> mcp.discover_and_build()
        >>> print(mcp.introspect_capabilities())
    """

    def __init__(
        self,
        manifest_dir: str = "/home/kloros/src/mcp/manifests",
        enable_discovery: bool = True,
        timeout_sec: int = 10
    ):
        """Initialize MCP integration.

        Args:
            manifest_dir: Directory with server manifests
            enable_discovery: Auto-discover on init
            timeout_sec: I/O timeout per SPEC-010
        """
        self.client = MCPClient(timeout_sec=timeout_sec)
        self.graph = CapabilityGraph()
        self.policy = PolicyEngine()
        self.manifest_dir = manifest_dir

        logger.info("[mcp.integration] Initialized MCP integration")

        if enable_discovery:
            self.discover_and_build()

    def discover_and_build(self) -> Dict[str, Any]:
        """Discover servers and build capability graph.

        Purpose:
            Run discovery, parse manifests, build graph, configure policies.

        Outcomes:
            - Servers discovered
            - Graph built
            - Policies configured
            - Summary report generated

        Returns:
            Summary dictionary with counts and status
        """
        logger.info("[mcp.integration] Starting discovery and build")

        # Step 1: Discover servers
        servers = self.client.discover_servers(self.manifest_dir)
        logger.info(f"[mcp.integration] Discovered {len(servers)} servers")

        # Step 2: Build capability graph from server manifests
        capabilities_added = 0
        for server in servers:
            for capability_id in server.manifest.capabilities:
                # Skip if already in graph (avoid duplicates)
                if self.graph.get_node(capability_id):
                    logger.debug(f"[mcp.integration] Skipping duplicate capability: {capability_id}")
                    continue

                # Create capability node
                node = CapabilityNode(
                    capability_id=capability_id,
                    name=capability_id.replace(".", " ").title(),
                    description=f"Capability from {server.manifest.name}",
                    source_server=server.manifest.server_id,
                    version=server.manifest.version,
                    budget=ResourceBudget()  # Default budget
                )

                # Add to graph
                if self.graph.add_node(node):
                    capabilities_added += 1

                    # Add default policy rule
                    rule = PolicyRule(
                        rule_id=f"policy_{capability_id}",
                        capability_id=capability_id,
                        max_time_ms=5000,
                        max_cpu_pct=90,
                        max_memory_mb=8192
                    )
                    self.policy.add_rule(rule)

        logger.info(f"[mcp.integration] Built graph with {capabilities_added} capabilities")

        # Step 2b: Load capabilities from registry (TUMIX, brainmods, etc.)
        registry_caps = self._load_from_registry()
        capabilities_added += registry_caps
        logger.info(f"[mcp.integration] Added {registry_caps} capabilities from registry")

        # Step 3: Generate summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "servers_discovered": len(servers),
            "capabilities_added": capabilities_added,
            "graph_summary": self.graph.get_summary(),
            "servers": [
                {
                    "id": s.manifest.server_id,
                    "name": s.manifest.name,
                    "version": s.manifest.version,
                    "capabilities": len(s.manifest.capabilities)
                }
                for s in servers
            ]
        }

        return summary

    def _load_from_registry(self) -> int:
        """Load capabilities from capabilities.yaml registry.

        Purpose:
            Populate MCP graph with KLoROS native capabilities
            (TUMIX, brainmods, AgentFlow, etc.) from the registry.

        Returns:
            Number of capabilities added
        """
        try:
            from src.registry.loader import get_registry
            registry = get_registry()

            count = 0
            # Load enabled capabilities from registry
            for cap in registry.get_enabled_capabilities():
                # Skip if already in graph
                if self.graph.get_node(cap.name):
                    continue

                # Create capability node
                node = CapabilityNode(
                    capability_id=cap.name,
                    name=cap.name.replace(".", " ").replace("_", " ").title(),
                    description=cap.description,
                    source_server="kloros_registry",
                    version="1.0.0",
                    budget=ResourceBudget(
                        max_time_ms=10000,
                        max_cpu_pct=80,
                        max_memory_mb=4096
                    )
                )

                if self.graph.add_node(node):
                    count += 1

                    # Add policy rule
                    rule = PolicyRule(
                        rule_id=f"policy_{cap.name}",
                        capability_id=cap.name,
                        max_time_ms=10000,
                        max_cpu_pct=80,
                        max_memory_mb=4096
                    )
                    self.policy.add_rule(rule)

            return count
        except Exception as e:
            logger.warning(f"[mcp.integration] Failed to load from registry: {e}")
            return 0

    def introspect_capabilities(self) -> str:
        """Generate capability inventory for XAI "what can you do?" query.

        Purpose:
            Provide complete, accurate list of available capabilities
            with source server, version, and status.

        Outcomes:
            Human-readable capability inventory

        Returns:
            Formatted capability list string
        """
        nodes = self.graph.get_enabled_capabilities()

        if not nodes:
            return "No capabilities currently available."

        # Group by server
        by_server: Dict[str, List[CapabilityNode]] = {}
        for node in nodes:
            if node.source_server not in by_server:
                by_server[node.source_server] = []
            by_server[node.source_server].append(node)

        lines = ["=== AVAILABLE CAPABILITIES ===\n"]

        for server_id, caps in sorted(by_server.items()):
            server = self.client.get_server(server_id)
            if server:
                lines.append(f"Server: {server.manifest.name} (v{server.manifest.version})")
                lines.append(f"  Status: {server.health_status}")
                lines.append(f"  Capabilities:")

                for cap in sorted(caps, key=lambda c: c.capability_id):
                    status = "✓" if cap.enabled else "✗"
                    lines.append(f"    {status} {cap.capability_id}")
                    lines.append(f"       Budget: {cap.budget.max_time_ms}ms, {cap.budget.max_memory_mb}MB")

                lines.append("")

        return "\n".join(lines)

    def route_capability(
        self,
        goal: str,
        user_id: str = "operator",
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """Route goal to appropriate capability with fallback chain.

        Purpose:
            Select best capability for goal, build fallback chain,
            evaluate policy, generate XAI rationale.

        Parameters:
            goal: User goal/query
            user_id: User making request
            context: Optional context dictionary

        Outcomes:
            RoutingDecision with selected capability and XAI trace

        Returns:
            RoutingDecision object

        Example:
            >>> decision = mcp.route_capability("search memory for recent events", "operator")
            >>> print(decision.capability_id)
            >>> print(decision.rationale)
        """
        # Simple keyword-based routing for now (can be enhanced with semantic search)
        enabled_nodes = self.graph.get_enabled_capabilities()

        if not enabled_nodes:
            return RoutingDecision(
                capability_id="none",
                rationale="No capabilities available",
                alternatives_considered=[]
            )

        # Score capabilities by keyword match
        scores = []
        goal_lower = goal.lower()

        for node in enabled_nodes:
            score = 0.0

            # Simple keyword matching
            cap_words = node.capability_id.lower().split(".")
            for word in cap_words:
                if word in goal_lower:
                    score += 1.0

            scores.append((node, score))

        # Sort by score
        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores or scores[0][1] == 0:
            return RoutingDecision(
                capability_id="none",
                rationale="No relevant capabilities found for goal",
                alternatives_considered=[
                    {"capability_id": n.capability_id, "score": s}
                    for n, s in scores[:3]
                ]
            )

        # Select best match
        best_node, best_score = scores[0]

        # Evaluate policy
        policy_decision = self.policy.evaluate(
            best_node.capability_id,
            user_id,
            goal
        )

        # Build fallback chain (next 2 best matches)
        fallback_chain = [n.capability_id for n, s in scores[1:3] if s > 0]

        # Generate rationale
        rationale = f"Selected {best_node.capability_id} (score: {best_score:.1f})"
        if policy_decision.allowed:
            rationale += " - Policy: ALLOWED"
        else:
            rationale += f" - Policy: DENIED ({', '.join(policy_decision.violations)})"

        return RoutingDecision(
            capability_id=best_node.capability_id,
            rationale=rationale,
            alternatives_considered=[
                {"capability_id": n.capability_id, "score": s}
                for n, s in scores[1:4]
            ],
            policy_decision=policy_decision,
            fallback_chain=fallback_chain
        )

    def explain_unavailable(self, capability_id: str) -> str:
        """Explain why a capability is unavailable (XAI "why not Z?").

        Purpose:
            Provide transparency when capability cannot be used.

        Parameters:
            capability_id: Capability to explain

        Returns:
            Human-readable explanation
        """
        node = self.graph.get_node(capability_id)

        if not node:
            return f"Capability '{capability_id}' does not exist in the system."

        if not node.enabled:
            return f"Capability '{capability_id}' is currently disabled (health: {node.health_status.value})."

        # Check server status
        server = self.client.get_server(node.source_server)
        if server and not server.connected:
            return f"Capability '{capability_id}' unavailable: server '{server.manifest.name}' is not connected."

        return f"Capability '{capability_id}' is available and enabled."

    def save_snapshot(self, path: str) -> None:
        """Save capability graph snapshot to JSON.

        Parameters:
            path: Output path for JSON snapshot
        """
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "graph_summary": self.graph.get_summary(),
            "capabilities": [
                {
                    "id": node.capability_id,
                    "name": node.name,
                    "server": node.source_server,
                    "version": node.version,
                    "enabled": node.enabled,
                    "health": node.health_status.value,
                    "depends_on": node.depends_on
                }
                for node in self.graph.nodes.values()
            ]
        }

        with open(path, 'w') as f:
            json.dump(snapshot, f, indent=2)

        logger.info(f"[mcp.integration] Saved snapshot to {path}")


if __name__ == "__main__":
    # Integration test
    print("=== MCP Integration Test ===\n")

    # Initialize
    mcp = MCPIntegration(enable_discovery=True)

    # Show discovery summary
    summary = mcp.discover_and_build()
    print(f"Discovered: {summary['servers_discovered']} servers")
    print(f"Capabilities: {summary['capabilities_added']}\n")

    # Test introspection
    print(mcp.introspect_capabilities())

    # Test routing
    print("\n=== Routing Test ===")
    decision = mcp.route_capability("search for recent conversations", "operator")
    print(f"Selected: {decision.capability_id}")
    print(f"Rationale: {decision.rationale}")
    print(f"Fallbacks: {decision.fallback_chain}")

    # Test unavailable explanation
    print("\n=== Unavailable Explanation ===")
    print(mcp.explain_unavailable("nonexistent.capability"))

    # Save snapshot
    snapshot_path = "/home/kloros/artifacts/mcp-reports/capability_graph.json"
    mcp.save_snapshot(snapshot_path)
    print(f"\nSnapshot saved to {snapshot_path}")
