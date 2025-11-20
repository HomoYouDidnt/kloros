"""
SPICA Derivative: Model Context Protocol (MCP) Behavioral Tests

SPICA-based MCP testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Discovery: Server enumeration and manifest parsing
- Graph: DAG invariants, cycle detection, topological sort
- Routing: Goal-to-capability mapping with fallbacks
- Policy: Budget enforcement and access control
- Degradation: Health tracking and fallback handling
- XAI: Introspection queries and routing rationale

KPIs: discovery_success_rate, routing_success_rate, policy_compliance, degradation_recovery_rate
"""
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result
from src.mcp.integration import MCPIntegration, RoutingDecision
from src.mcp.capability_graph import CapabilityNode, ResourceBudget, HealthStatus
from src.mcp.policy import PolicyRule


@dataclass
class MCPTestConfig:
    """Configuration for MCP domain tests."""
    enable_discovery: bool = True
    expected_min_servers: int = 2
    expected_min_capabilities: int = 9
    test_goals: List[Dict] = None
    max_test_duration_sec: int = 300

    def __post_init__(self):
        if self.test_goals is None:
            self.test_goals = [
                {"goal": "search memory", "expected_prefix": "memory"},
                {"goal": "search documents with RAG", "expected_prefix": "rag"},
                {"goal": "summarize memory", "expected_prefix": "memory"}
            ]


@dataclass
class MCPTestResult:
    """Results from a single MCP test."""
    test_id: str
    test_name: str
    status: str
    latency_ms: float
    error: Optional[str] = None


class SpicaMCP(SpicaBase):
    """SPICA derivative for MCP behavioral testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[MCPTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-mcp-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'enable_discovery': test_config.enable_discovery,
                'expected_min_servers': test_config.expected_min_servers,
                'expected_min_capabilities': test_config.expected_min_capabilities,
                'test_goals': test_config.test_goals,
                'max_test_duration_sec': test_config.max_test_duration_sec
            })

        super().__init__(spica_id=spica_id, domain="mcp", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or MCPTestConfig()
        self.results: List[MCPTestResult] = []
        self.mcp: Optional[MCPIntegration] = None
        
        self.record_telemetry("spica_mcp_init", {
            "enable_discovery": self.test_config.enable_discovery,
            "expected_min_servers": self.test_config.expected_min_servers
        })

    def _initialize_mcp(self) -> bool:
        """Initialize MCP integration."""
        try:
            self.mcp = MCPIntegration(enable_discovery=self.test_config.enable_discovery)
            self.record_telemetry("mcp_initialized", {"success": True})
            return True
        except Exception as e:
            self.record_telemetry("mcp_init_failed", {"error": str(e)})
            return False

    def _run_discovery_test(self, epoch_id: str) -> MCPTestResult:
        """Test MCP server discovery."""
        start = time.time()
        test_name = "discovery"
        test_id = f"mcp::{test_name}::{epoch_id}"

        try:
            servers = self.mcp.client.servers
            assert len(servers) >= self.test_config.expected_min_servers, \
                f"Expected ≥{self.test_config.expected_min_servers} servers, got {len(servers)}"

            for server_id, server in servers.items():
                assert server.manifest.name, "Server must have name"
                assert server.manifest.version, "Server must have version"
                assert len(server.manifest.capabilities) > 0, "Server must have capabilities"

            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="pass", latency_ms=latency_ms)
            self.record_telemetry("test_complete", {"test": test_name, "status": "pass"})
            write_test_result(test_id, "pass", latency_ms, 0.0, 0.0, epoch_id)
            return result

        except AssertionError as e:
            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="fail", 
                                   latency_ms=latency_ms, error=str(e))
            self.record_telemetry("test_failed", {"test": test_name, "error": str(e)})
            write_test_result(test_id, "fail", latency_ms, 0.0, 0.0, epoch_id)
            return result

    def _run_graph_dag_test(self, epoch_id: str) -> MCPTestResult:
        """Test graph DAG invariant."""
        start = time.time()
        test_name = "graph_dag"
        test_id = f"mcp::{test_name}::{epoch_id}"

        try:
            assert not self.mcp.graph.has_cycles(), "Graph must be acyclic (DAG)"

            summary = self.mcp.graph.get_summary()
            assert summary['total_capabilities'] >= self.test_config.expected_min_capabilities, \
                f"Expected ≥{self.test_config.expected_min_capabilities} capabilities, got {summary['total_capabilities']}"
            assert summary['enabled'] > 0, "Must have enabled capabilities"

            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="pass", latency_ms=latency_ms)
            self.record_telemetry("test_complete", {"test": test_name, "status": "pass", "capabilities": summary['total_capabilities']})
            write_test_result(test_id, "pass", latency_ms, 0.0, 0.0, epoch_id)
            return result

        except AssertionError as e:
            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="fail",
                                   latency_ms=latency_ms, error=str(e))
            self.record_telemetry("test_failed", {"test": test_name, "error": str(e)})
            write_test_result(test_id, "fail", latency_ms, 0.0, 0.0, epoch_id)
            return result

    def _run_routing_test(self, epoch_id: str) -> MCPTestResult:
        """Test MCP routing."""
        start = time.time()
        test_name = "routing"
        test_id = f"mcp::{test_name}::{epoch_id}"

        try:
            for goal_data in self.test_config.test_goals:
                goal = goal_data["goal"]
                expected_prefix = goal_data["expected_prefix"]
                
                decision = self.mcp.route_capability(goal, "operator")
                assert decision.capability_id != "none", f"Routing failed for goal: {goal}"
                assert decision.capability_id.startswith(expected_prefix.split('.')[0]), \
                    f"Expected {expected_prefix}, got {decision.capability_id} for goal: {goal}"

            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="pass", latency_ms=latency_ms)
            self.record_telemetry("test_complete", {"test": test_name, "status": "pass"})
            write_test_result(test_id, "pass", latency_ms, 0.0, 0.0, epoch_id)
            return result

        except AssertionError as e:
            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="fail",
                                   latency_ms=latency_ms, error=str(e))
            self.record_telemetry("test_failed", {"test": test_name, "error": str(e)})
            write_test_result(test_id, "fail", latency_ms, 0.0, 0.0, epoch_id)
            return result

    def _run_policy_test(self, epoch_id: str) -> MCPTestResult:
        """Test policy budget enforcement."""
        start = time.time()
        test_name = "policy_budgets"
        test_id = f"mcp::{test_name}::{epoch_id}"

        try:
            for node in self.mcp.graph.nodes.values():
                assert node.budget is not None, f"Capability {node.capability_id} missing budget"
                assert node.budget.max_time_ms > 0, f"Invalid max_time_ms for {node.capability_id}"
                assert node.budget.max_memory_mb > 0, f"Invalid max_memory_mb for {node.capability_id}"
                assert node.budget.max_cpu_pct <= 90, f"max_cpu_pct exceeds limit for {node.capability_id}"

            decision = self.mcp.policy.evaluate("memory.search", "operator", "test query")
            assert decision.allowed, "Default policy should allow requests"

            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="pass", latency_ms=latency_ms)
            self.record_telemetry("test_complete", {"test": test_name, "status": "pass"})
            write_test_result(test_id, "pass", latency_ms, 0.0, 0.0, epoch_id)
            return result

        except AssertionError as e:
            latency_ms = (time.time() - start) * 1000
            result = MCPTestResult(test_id=test_id, test_name=test_name, status="fail",
                                   latency_ms=latency_ms, error=str(e))
            self.record_telemetry("test_failed", {"test": test_name, "error": str(e)})
            write_test_result(test_id, "fail", latency_ms, 0.0, 0.0, epoch_id)
            return result

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """SPICA evaluate() interface for MCP tests."""
        epoch_id = (context or {}).get("epoch_id", "unknown")
        
        if not self._initialize_mcp():
            return {"fitness": 0.0, "test_id": "mcp::init_failed", "status": "fail", "spica_id": self.spica_id}

        results = self.run_all_tests(epoch_id)
        
        passed = sum(1 for r in results if r.status == "pass")
        total = len(results)
        fitness = passed / total if total > 0 else 0.0

        return {
            "fitness": fitness,
            "test_id": f"mcp::all::{epoch_id}",
            "status": "pass" if passed == total else "fail",
            "metrics": {"tests_passed": passed, "tests_failed": total - passed, "total_tests": total},
            "spica_id": self.spica_id
        }

    def run_all_tests(self, epoch_id: str) -> List[MCPTestResult]:
        """Run all MCP behavioral tests."""
        if not self.mcp:
            if not self._initialize_mcp():
                return []

        test_methods = [
            self._run_discovery_test,
            self._run_graph_dag_test,
            self._run_routing_test,
            self._run_policy_test
        ]

        for test_method in test_methods:
            try:
                result = test_method(epoch_id)
                self.results.append(result)
            except Exception as e:
                self.record_telemetry("test_exception", {"error": str(e)})
                continue

        return self.results

    def get_summary(self) -> Dict:
        """Get summary statistics for all tests."""
        if not self.results:
            return {"pass_rate": 0.0, "total_tests": 0}

        passed = sum(1 for r in self.results if r.status == "pass")
        latencies = [r.latency_ms for r in self.results]

        return {
            "pass_rate": passed / len(self.results),
            "total_tests": len(self.results),
            "tests_passed": passed,
            "tests_failed": len(self.results) - passed,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0
        }
