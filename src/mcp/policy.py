#!/usr/bin/env python3
"""Policy engine for MCP capability access control and resource budgets.

Purpose:
    Enforce resource budgets, access control, and safety gates per SPEC-001.

Governance:
    - SPEC-001: Resource budgets (max_runtime=600s, cpu=90%, memory=8GB)
    - Tool-Integrity: Complete docstrings, graceful error handling
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Pattern
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class DataClass(Enum):
    """Data classification levels."""
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SECRET = "SECRET"


@dataclass
class PolicyRule:
    """Policy rule for capability access control and resource limits.

    Attributes:
        rule_id: Unique rule identifier
        capability_id: Capability this rule applies to

        # Resource limits (SPEC-001)
        max_time_ms: Maximum execution time
        max_cpu_pct: Max CPU percentage (default 90% per SPEC-001)
        max_memory_mb: Max memory MB (default 8192MB = 8GB per SPEC-001)

        # Access control
        allowed_users: List of allowed user IDs (None = all users)
        forbidden_patterns: Regex patterns to block in inputs

        # Data governance
        allow_egress: Whether data can leave the system
        pii_redaction: Whether to redact PII
        data_classification: Data classification level
    """
    rule_id: str
    capability_id: str

    # SPEC-001 resource limits
    max_time_ms: int = 5000
    max_cpu_pct: int = 90
    max_memory_mb: int = 8192  # 8GB

    # Access control
    allowed_users: Optional[List[str]] = None
    forbidden_patterns: List[str] = field(default_factory=list)

    # Data governance
    allow_egress: bool = False
    pii_redaction: bool = True
    data_classification: DataClass = DataClass.INTERNAL


@dataclass
class PolicyDecision:
    """Result of policy evaluation.

    Attributes:
        allowed: Whether action is allowed
        rules_applied: List of rule IDs that were evaluated
        violations: List of policy violations if denied
        budget_enforced: Resource budget that will be enforced
    """
    allowed: bool
    rules_applied: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    budget_enforced: Optional[dict] = None


class PolicyEngine:
    """Policy enforcement engine for MCP capabilities.

    Purpose:
        Evaluate access requests against policy rules and enforce
        resource budgets per SPEC-001.

    Outcomes:
        - PolicyDecision for each request
        - Resource budget enforcement
        - Access control validation
        - Data governance compliance
    """

    def __init__(self):
        """Initialize policy engine."""
        self.rules: dict[str, PolicyRule] = {}
        logger.info("[mcp.policy] Policy engine initialized")

    def add_rule(self, rule: PolicyRule) -> None:
        """Add policy rule.

        Parameters:
            rule: PolicyRule to add
        """
        self.rules[rule.rule_id] = rule
        logger.info(f"[mcp.policy] Added rule: {rule.rule_id} for {rule.capability_id}")

    def evaluate(
        self,
        capability_id: str,
        user_id: str,
        input_text: Optional[str] = None
    ) -> PolicyDecision:
        """Evaluate policy for capability access request.

        Purpose:
            Check all applicable rules and return policy decision.

        Parameters:
            capability_id: Capability being accessed
            user_id: User making the request
            input_text: Optional input text to check for forbidden patterns

        Outcomes:
            PolicyDecision with allowed/denied status and violations

        Returns:
            PolicyDecision object
        """
        decision = PolicyDecision(allowed=True)

        # Find applicable rules
        applicable_rules = [
            rule for rule in self.rules.values()
            if rule.capability_id == capability_id
        ]

        if not applicable_rules:
            # No rules = allow by default
            logger.debug(f"[mcp.policy] No rules for {capability_id}, allowing")
            return decision

        for rule in applicable_rules:
            decision.rules_applied.append(rule.rule_id)

            # Check user access
            if rule.allowed_users is not None and user_id not in rule.allowed_users:
                decision.allowed = False
                decision.violations.append(
                    f"User {user_id} not in allowed users for {capability_id}"
                )

            # Check forbidden patterns
            if input_text and rule.forbidden_patterns:
                for pattern_str in rule.forbidden_patterns:
                    try:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        if pattern.search(input_text):
                            decision.allowed = False
                            decision.violations.append(
                                f"Input matches forbidden pattern: {pattern_str}"
                            )
                    except re.error as e:
                        logger.error(f"[mcp.policy] Invalid regex pattern {pattern_str}: {e}")

            # Set budget enforcement
            if decision.budget_enforced is None:
                decision.budget_enforced = {
                    "max_time_ms": rule.max_time_ms,
                    "max_cpu_pct": rule.max_cpu_pct,
                    "max_memory_mb": rule.max_memory_mb
                }

        return decision


if __name__ == "__main__":
    # Self-test
    print("=== Policy Engine Self-Test ===\n")

    engine = PolicyEngine()

    # Add rule for memory.search
    rule = PolicyRule(
        rule_id="memory_search_policy",
        capability_id="memory.search",
        max_time_ms=5000,
        max_cpu_pct=90,
        max_memory_mb=512,
        allowed_users=["operator", "admin"],
        forbidden_patterns=[r"password", r"secret"],
        allow_egress=False,
        pii_redaction=True
    )
    engine.add_rule(rule)

    # Test allowed access
    decision1 = engine.evaluate("memory.search", "operator", "search for recent events")
    print(f"Test 1 - Allowed user, clean input: {decision1.allowed}")
    print(f"  Rules applied: {decision1.rules_applied}")
    print(f"  Budget: {decision1.budget_enforced}\n")

    # Test forbidden pattern
    decision2 = engine.evaluate("memory.search", "operator", "what is my password")
    print(f"Test 2 - Forbidden pattern: {decision2.allowed}")
    print(f"  Violations: {decision2.violations}\n")

    # Test unauthorized user
    decision3 = engine.evaluate("memory.search", "guest", "search for events")
    print(f"Test 3 - Unauthorized user: {decision3.allowed}")
    print(f"  Violations: {decision3.violations}\n")

    # Test capability with no rules
    decision4 = engine.evaluate("rag.search", "anyone", "test")
    print(f"Test 4 - No rules (default allow): {decision4.allowed}")
