"""Model Context Protocol (MCP) for KLoROS.

Provides full system inventory and capability introspection for agentic AI
self-awareness and operational transparency.

Modules:
    client: MCP client for server discovery and handshake
    transport: stdio/websocket transport layer
    capability_graph: Dependency graph with preconditions/postconditions
    policy: Resource budgets and access control enforcement
    planner: Goal → capability routing with fallback chains
    health: Circuit breakers and degradation handling
    audit: Telemetry and security audit trail
    persistence: Registry snapshots and hot reload
    security: Token management and data classification
    introspection: XAI layer for "what/why/when" transparency

Governance:
    - SPEC-001: Resource budgets enforced
    - SPEC-007: Structured JSONL logging
    - SPEC-009: Registered in capabilities.yaml
    - SPEC-010: All I/O operations have 10s timeout
    - Tool-Integrity: Self-contained, testable, complete docstrings
    - D-REAM-Allowed-Stack: No prohibited utilities
"""

__version__ = "1.0.0"
__all__ = [
    "MCPClient",
    "MCPTransport",
    "CapabilityGraph",
    "PolicyEngine",
    "MCPPlanner",
    "HealthMonitor",
    "AuditLogger",
    "RegistryPersistence",
    "SecurityManager",
    "MCPIntrospection",
]
