#!/usr/bin/env python3
"""Capability Graph with dependency tracking and cycle detection.

Purpose:
    Build and maintain a directed acyclic graph (DAG) of capabilities
    with preconditions, postconditions, and resource budgets.

Outcomes:
    - Explorable capability graph
    - Cycle detection (fails fast)
    - Topological ordering for execution planning
    - Dependency resolution

Governance:
    - SPEC-001: Resource budgets enforced
    - Tool-Integrity: Self-contained, testable, complete docstrings
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Capability health status."""
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ResourceBudget:
    """Resource constraints for capability execution.

    Attributes:
        max_time_ms: Maximum execution time (SPEC-001)
        max_cpu_pct: Max CPU percentage (SPEC-001: 90%)
        max_memory_mb: Max memory in MB (SPEC-001: 8GB = 8192MB)
        max_tokens: Max LLM tokens if applicable
        max_gpu_mb: Max GPU memory if applicable (SPEC-001: 4096MB)
    """
    max_time_ms: int = 5000
    max_cpu_pct: int = 90  # SPEC-001
    max_memory_mb: int = 8192  # SPEC-001: 8GB
    max_tokens: int = 2000
    max_gpu_mb: Optional[int] = None


@dataclass
class Precondition:
    """Precondition that must be met before capability execution.

    Attributes:
        condition_id: Unique identifier
        description: Human-readable description
        check_function: Optional callable for runtime validation
    """
    condition_id: str
    description: str
    check_function: Optional[Any] = None


@dataclass
class Postcondition:
    """Expected outcome after capability execution.

    Attributes:
        outcome_id: Unique identifier
        description: Human-readable description
        verify_function: Optional callable for validation
    """
    outcome_id: str
    description: str
    verify_function: Optional[Any] = None


@dataclass
class CapabilityNode:
    """Node in capability graph representing a single capability.

    Attributes:
        capability_id: Unique capability identifier (e.g., "memory.search")
        name: Human-readable name
        description: Capability description
        source_server: MCP server providing this capability
        version: Semver version

        # Execution requirements
        preconditions: List of preconditions
        postconditions: List of expected outcomes
        budget: Resource budget

        # Dependencies
        depends_on: List of capability IDs this depends on

        # Health tracking
        health_status: Current health status
        enabled: Whether capability is currently enabled
        error_count: Number of consecutive errors
    """
    capability_id: str
    name: str
    description: str
    source_server: str
    version: str = "1.0.0"

    preconditions: List[Precondition] = field(default_factory=list)
    postconditions: List[Postcondition] = field(default_factory=list)
    budget: ResourceBudget = field(default_factory=ResourceBudget)

    depends_on: List[str] = field(default_factory=list)

    health_status: HealthStatus = HealthStatus.UNKNOWN
    enabled: bool = True
    error_count: int = 0


class CapabilityGraph:
    """Directed acyclic graph of capabilities with dependency tracking.

    Purpose:
        Maintain explorable graph of capabilities with cycle detection
        and topological ordering for execution planning.

    Parameters:
        None

    Outcomes:
        - DAG of capabilities
        - Cycle detection on add_node
        - Topological ordering available
        - Dependency resolution

    Example:
        >>> graph = CapabilityGraph()
        >>> node = CapabilityNode("memory.search", "Search Memory", "...", "memory_server")
        >>> graph.add_node(node)
        >>> if graph.has_cycles():
        ...     print("Cycle detected!")
    """

    def __init__(self):
        """Initialize empty capability graph."""
        self.nodes: Dict[str, CapabilityNode] = {}
        self.edges: Dict[str, List[str]] = {}  # capability_id -> [dependencies]
        logger.info("[mcp.graph] Initialized capability graph")

    def add_node(self, node: CapabilityNode) -> bool:
        """Add capability node to graph.

        Purpose:
            Add new capability with automatic dependency edge creation
            and cycle detection.

        Parameters:
            node: CapabilityNode to add

        Outcomes:
            - Node added to graph (if no cycles)
            - Edges created for dependencies
            - Cycle detection performed

        Returns:
            True if added successfully, False if would create cycle

        Raises:
            ValueError: If node with same ID already exists
        """
        if node.capability_id in self.nodes:
            raise ValueError(f"Node {node.capability_id} already exists in graph")

        # Temporarily add node and edges
        self.nodes[node.capability_id] = node
        self.edges[node.capability_id] = node.depends_on.copy()

        # Check for cycles
        if self.has_cycles():
            # Rollback
            del self.nodes[node.capability_id]
            del self.edges[node.capability_id]
            logger.error(f"[mcp.graph] Adding {node.capability_id} would create cycle")
            return False

        logger.info(f"[mcp.graph] Added node: {node.capability_id}")
        return True

    def get_node(self, capability_id: str) -> Optional[CapabilityNode]:
        """Get capability node by ID.

        Parameters:
            capability_id: Capability identifier

        Returns:
            CapabilityNode if found, None otherwise
        """
        return self.nodes.get(capability_id)

    def mark_disabled(self, capability_id: str, reason: str = "") -> bool:
        """Disable a capability (e.g., due to server failure).

        Purpose:
            Mark capability as disabled for graceful degradation.

        Parameters:
            capability_id: Capability to disable
            reason: Optional reason for disabling

        Outcomes:
            - Capability marked as disabled
            - Health status updated to FAILED

        Returns:
            True if capability was disabled, False if not found
        """
        node = self.get_node(capability_id)
        if not node:
            logger.warning(f"[mcp.graph] Cannot disable unknown capability: {capability_id}")
            return False

        node.enabled = False
        node.health_status = HealthStatus.FAILED
        logger.info(f"[mcp.graph] Disabled capability: {capability_id} (reason: {reason})")
        return True

    def mark_enabled(self, capability_id: str) -> bool:
        """Re-enable a capability.

        Parameters:
            capability_id: Capability to enable

        Returns:
            True if enabled, False if not found
        """
        node = self.get_node(capability_id)
        if not node:
            return False

        node.enabled = True
        node.health_status = HealthStatus.OK
        node.error_count = 0
        logger.info(f"[mcp.graph] Enabled capability: {capability_id}")
        return True

    def get_dependencies(self, capability_id: str) -> List[str]:
        """Get list of capabilities this capability depends on.

        Parameters:
            capability_id: Capability identifier

        Returns:
            List of capability IDs (dependencies)
        """
        return self.edges.get(capability_id, [])

    def get_dependents(self, capability_id: str) -> List[str]:
        """Get list of capabilities that depend on this one.

        Parameters:
            capability_id: Capability identifier

        Returns:
            List of capability IDs that depend on this capability
        """
        dependents = []
        for node_id, deps in self.edges.items():
            if capability_id in deps:
                dependents.append(node_id)
        return dependents

    def has_cycles(self) -> bool:
        """Check if graph contains cycles using DFS.

        Purpose:
            Detect cycles to maintain DAG invariant.

        Outcomes:
            Boolean indicating whether cycles exist

        Returns:
            True if cycles exist, False if DAG
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle_util(node_id: str) -> bool:
            """DFS helper for cycle detection."""
            visited.add(node_id)
            rec_stack.add(node_id)

            # Check all dependencies
            for dep_id in self.edges.get(node_id, []):
                if dep_id not in visited:
                    if has_cycle_util(dep_id):
                        return True
                elif dep_id in rec_stack:
                    # Back edge found - cycle detected
                    return True

            rec_stack.remove(node_id)
            return False

        # Check all nodes
        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle_util(node_id):
                    return True

        return False

    def topological_sort(self) -> Optional[List[str]]:
        """Get topological ordering of capabilities.

        Purpose:
            Provide execution order respecting dependencies.

        Outcomes:
            Ordered list of capability IDs (or None if cycles exist)

        Returns:
            List of capability IDs in topological order, or None if graph has cycles

        Example:
            >>> order = graph.topological_sort()
            >>> if order:
            ...     print(f"Execution order: {order}")
        """
        if self.has_cycles():
            logger.error("[mcp.graph] Cannot perform topological sort: graph has cycles")
            return None

        visited: Set[str] = set()
        stack: List[str] = []

        def visit(node_id: str):
            """DFS for topological sort."""
            if node_id in visited:
                return
            visited.add(node_id)

            # Visit dependencies first
            for dep_id in self.edges.get(node_id, []):
                visit(dep_id)

            stack.append(node_id)

        # Visit all nodes
        for node_id in self.nodes:
            visit(node_id)

        return stack

    def get_enabled_capabilities(self) -> List[CapabilityNode]:
        """Get list of currently enabled capabilities.

        Returns:
            List of enabled CapabilityNode objects
        """
        return [node for node in self.nodes.values() if node.enabled]

    def get_summary(self) -> Dict[str, Any]:
        """Get graph summary statistics.

        Returns:
            Dictionary with graph metrics
        """
        enabled_count = len(self.get_enabled_capabilities())
        total_count = len(self.nodes)

        health_counts = {
            "OK": 0,
            "DEGRADED": 0,
            "FAILED": 0,
            "UNKNOWN": 0
        }

        for node in self.nodes.values():
            health_counts[node.health_status.value] += 1

        return {
            "total_capabilities": total_count,
            "enabled": enabled_count,
            "disabled": total_count - enabled_count,
            "health_status": health_counts,
            "has_cycles": self.has_cycles(),
            "servers": list(set(node.source_server for node in self.nodes.values()))
        }


if __name__ == "__main__":
    # Self-test
    print("=== Capability Graph Self-Test ===\n")

    graph = CapabilityGraph()

    # Add nodes
    memory_search = CapabilityNode(
        capability_id="memory.search",
        name="Search Memory",
        description="Search episodic memory",
        source_server="memory_mcp_server",
        budget=ResourceBudget(max_time_ms=5000, max_memory_mb=512)
    )

    memory_summarize = CapabilityNode(
        capability_id="memory.summarize",
        name="Summarize Memory",
        description="Summarize memory events",
        source_server="memory_mcp_server",
        depends_on=["memory.search"],  # Depends on search
        budget=ResourceBudget(max_time_ms=8000, max_memory_mb=1024)
    )

    rag_search = CapabilityNode(
        capability_id="rag.search",
        name="RAG Search",
        description="Hybrid retrieval search",
        source_server="rag_mcp_server",
        budget=ResourceBudget(max_time_ms=3000, max_memory_mb=2048)
    )

    # Add to graph
    graph.add_node(memory_search)
    graph.add_node(memory_summarize)
    graph.add_node(rag_search)

    # Test cycle detection
    print(f"Has cycles: {graph.has_cycles()}")

    # Test topological sort
    order = graph.topological_sort()
    print(f"Topological order: {order}\n")

    # Test dependencies
    deps = graph.get_dependencies("memory.summarize")
    print(f"memory.summarize depends on: {deps}")

    dependents = graph.get_dependents("memory.search")
    print(f"memory.search is dependency of: {dependents}\n")

    # Test summary
    summary = graph.get_summary()
    print("Graph Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
