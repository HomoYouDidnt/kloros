"""
Policy Enforcement for Synthesized Tools

Enforces runtime policies like:
- Broker/topic allowlists (MQTT)
- Rate limiting (calls per hour)
- Schema validation (payload structure)
- Dry-run mode (high-risk tools)
- Resource budgets (side effect limits)
"""

import json
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class ToolBudget:
    """Resource budget for a tool."""
    max_calls_per_hour: int
    max_side_effect_bytes: int
    max_execution_time_ms: int


class PolicyEnforcer:
    """
    Enforces runtime policies for synthesized tools.

    Prevents high-risk tools from causing chaos by validating:
    - Allowlists (brokers, topics, endpoints)
    - Rate limits (calls per hour)
    - Schema (payload structure)
    - Dry-run mode (no actual side effects)
    """

    def __init__(self, policy_file: str = "/home/kloros/config/synthesis_policy.json"):
        self.policy_file = Path(policy_file)
        self.policies = self._load_policies()

        # Rate limiting tracking
        self.call_history = {}  # tool_name -> [timestamps]

    def _load_policies(self) -> Dict:
        """Load policy configuration."""
        if not self.policy_file.exists():
            return self._get_default_policies()

        try:
            with open(self.policy_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[policy] Failed to load policies: {e}, using defaults")
            return self._get_default_policies()

    def _get_default_policies(self) -> Dict:
        """Get default policies."""
        return {
            "mqtt_publish": {
                "risk": "high",
                "budget": {
                    "max_calls_per_hour": 10,
                    "max_side_effect_bytes": 1048576,
                    "max_execution_time_ms": 30000
                },
                "allowed_brokers": ["127.0.0.1:1883"],
                "allowed_topics": ["kloros/status/#", "ace/summary/published"],
                "payload_schema": {
                    "type": "object",
                    "required": ["type", "payload"],
                    "properties": {
                        "type": {"enum": ["status", "event", "summary"]},
                        "payload": {"type": "object"}
                    }
                },
                "dry_run_by_default": True,
                "requires_env": "ALLOW_PROD_WRITES=1"
            },
            "gpu_status": {
                "risk": "low",
                "budget": {
                    "max_calls_per_hour": 1000,
                    "max_side_effect_bytes": 0,
                    "max_execution_time_ms": 5000
                },
                "read_only": True
            }
        }

    def check_policy(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if tool execution is allowed by policy.

        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        policy = self.policies.get(tool_name)
        if not policy:
            # No policy = allowed (LOW risk assumed)
            return True, None

        # Check rate limit
        budget = policy.get('budget', {})
        max_calls = budget.get('max_calls_per_hour', 1000)

        if not self._check_rate_limit(tool_name, max_calls):
            return False, f"Rate limit exceeded: {max_calls} calls/hour"

        # Check dry-run requirement
        if policy.get('dry_run_by_default', False):
            requires_env = policy.get('requires_env')
            if requires_env:
                import os
                env_var, env_val = requires_env.split('=')
                if os.getenv(env_var) != env_val:
                    return False, f"Dry-run mode: Set {requires_env} to execute"

        # Check MQTT-specific policies
        if tool_name == 'mqtt_publish':
            allowed, reason = self._check_mqtt_policy(policy, args)
            if not allowed:
                return False, reason

        # Check schema if defined
        if 'payload_schema' in policy:
            if not self._validate_schema(args, policy['payload_schema']):
                return False, "Payload does not match required schema"

        return True, None

    def _check_rate_limit(self, tool_name: str, max_calls_per_hour: int) -> bool:
        """Check if tool is within rate limit."""
        now = time.time()
        hour_ago = now - 3600

        # Clean old calls
        if tool_name not in self.call_history:
            self.call_history[tool_name] = []

        self.call_history[tool_name] = [
            ts for ts in self.call_history[tool_name]
            if ts > hour_ago
        ]

        # Check limit
        if len(self.call_history[tool_name]) >= max_calls_per_hour:
            return False

        # Record this call
        self.call_history[tool_name].append(now)
        return True

    def _check_mqtt_policy(self, policy: Dict, args: Dict) -> Tuple[bool, Optional[str]]:
        """Check MQTT-specific policy."""
        # Check broker allowlist
        broker = args.get('broker', '127.0.0.1:1883')
        allowed_brokers = policy.get('allowed_brokers', [])

        if allowed_brokers and broker not in allowed_brokers:
            return False, f"Broker '{broker}' not in allowlist: {allowed_brokers}"

        # Check topic allowlist (with wildcard support)
        topic = args.get('topic', '')
        allowed_topics = policy.get('allowed_topics', [])

        if allowed_topics:
            topic_allowed = False
            for allowed in allowed_topics:
                if self._topic_matches(topic, allowed):
                    topic_allowed = True
                    break

            if not topic_allowed:
                return False, f"Topic '{topic}' not in allowlist: {allowed_topics}"

        return True, None

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if MQTT topic matches pattern (with # wildcard)."""
        if pattern == topic:
            return True

        if pattern.endswith('/#'):
            prefix = pattern[:-2]
            return topic.startswith(prefix)

        return False

    def _validate_schema(self, data: Dict, schema: Dict) -> bool:
        """Simple schema validation (subset of JSON Schema)."""
        # Check type
        if schema.get('type') == 'object':
            if not isinstance(data, dict):
                return False

            # Check required fields
            required = schema.get('required', [])
            for field in required:
                if field not in data:
                    return False

            # Check properties
            properties = schema.get('properties', {})
            for field, field_schema in properties.items():
                if field in data:
                    value = data[field]

                    # Check enum
                    if 'enum' in field_schema:
                        if value not in field_schema['enum']:
                            return False

                    # Check type
                    if 'type' in field_schema:
                        expected_type = field_schema['type']
                        if expected_type == 'object' and not isinstance(value, dict):
                            return False
                        elif expected_type == 'array' and not isinstance(value, list):
                            return False
                        elif expected_type == 'string' and not isinstance(value, str):
                            return False
                        elif expected_type == 'number' and not isinstance(value, (int, float)):
                            return False

        return True

    def get_policy(self, tool_name: str) -> Optional[Dict]:
        """Get policy for a tool."""
        return self.policies.get(tool_name)

    def get_budget(self, tool_name: str) -> Optional[ToolBudget]:
        """Get resource budget for a tool."""
        policy = self.policies.get(tool_name)
        if not policy or 'budget' not in policy:
            return None

        budget = policy['budget']
        return ToolBudget(
            max_calls_per_hour=budget.get('max_calls_per_hour', 1000),
            max_side_effect_bytes=budget.get('max_side_effect_bytes', 0),
            max_execution_time_ms=budget.get('max_execution_time_ms', 5000)
        )

    def reset_rate_limits(self, tool_name: Optional[str] = None) -> None:
        """Reset rate limits (for testing/admin)."""
        if tool_name:
            if tool_name in self.call_history:
                del self.call_history[tool_name]
        else:
            self.call_history.clear()


    def check_manifest_permissions(self, tool_name: str, manifest: dict, operation: dict) -> Tuple[bool, Optional[str]]:
        """
        Check manifest-based permissions for network, filesystem, and env.

        Args:
            tool_name: Name of the tool
            manifest: Tool manifest dictionary
            operation: Operation details like {"type": "network", "url": "..."} or {"type": "filesystem", "path": "..."}

        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        from .logging import log

        op_type = operation.get("type")

        if op_type == "network":
            allowed, reason = self._check_network_permission(tool_name, manifest, operation)
            if not allowed:
                log("policy.denied", tool=tool_name, type="network", reason=reason,
                    url=operation.get("url"))
            return allowed, reason

        elif op_type == "filesystem":
            allowed, reason = self._check_filesystem_permission(tool_name, manifest, operation)
            if not allowed:
                log("policy.denied", tool=tool_name, type="filesystem", reason=reason,
                    path=operation.get("path"))
            return allowed, reason

        elif op_type == "env":
            allowed, reason = self._check_env_requirements(tool_name, manifest)
            if not allowed:
                log("policy.denied", tool=tool_name, type="env", reason=reason)
            return allowed, reason

        # Unknown operation type
        return True, None

    def _check_network_permission(self, tool_name: str, manifest: dict, operation: dict) -> Tuple[bool, Optional[str]]:
        """Check if network operation is allowed by manifest."""
        permissions = manifest.get("permissions", {})
        network = permissions.get("network", {})

        allow_domains = network.get("allow_domains", [])
        if not allow_domains:
            # No restrictions defined
            return True, None

        url = operation.get("url", "")
        if not url:
            return False, "No URL provided for network operation"

        # Extract domain from URL
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]

            # Check if domain is in allowlist
            for allowed_domain in allow_domains:
                if domain == allowed_domain or domain.endswith('.' + allowed_domain):
                    return True, None

            return False, f"Domain '{domain}' not in allowlist: {allow_domains}"

        except Exception as e:
            return False, f"Invalid URL: {e}"

    def _check_filesystem_permission(self, tool_name: str, manifest: dict, operation: dict) -> Tuple[bool, Optional[str]]:
        """Check if filesystem operation is allowed by manifest."""
        permissions = manifest.get("permissions", {})
        filesystem = permissions.get("filesystem", {})

        allow_paths = filesystem.get("allow_paths", [])
        if not allow_paths:
            # No restrictions defined
            return True, None

        path = operation.get("path", "")
        if not path:
            return False, "No path provided for filesystem operation"

        from pathlib import Path
        try:
            target = Path(path).resolve()

            # Check if path is within allowlist
            for allowed_path in allow_paths:
                allowed = Path(allowed_path).resolve()
                try:
                    target.relative_to(allowed)
                    return True, None  # Path is within allowed directory
                except ValueError:
                    continue  # Not within this allowed path

            return False, f"Path '{path}' not in allowlist: {allow_paths}"

        except Exception as e:
            return False, f"Invalid path: {e}"

    def _check_env_requirements(self, tool_name: str, manifest: dict) -> Tuple[bool, Optional[str]]:
        """Check if required environment variables are present."""
        permissions = manifest.get("permissions", {})
        env_requirements = permissions.get("env_requirements", [])

        if not env_requirements:
            return True, None

        import os
        missing = []

        for env_var in env_requirements:
            if os.getenv(env_var) is None:
                missing.append(env_var)

        if missing:
            return False, f"Missing required environment variables: {', '.join(missing)}"

        return True, None

    def get_rate_limit_status(self, tool_name: str) -> Dict:
        """Get current rate limit status for a tool."""
        policy = self.policies.get(tool_name)
        if not policy:
            return {"error": "No policy defined"}

        max_calls = policy.get('budget', {}).get('max_calls_per_hour', 1000)

        now = time.time()
        hour_ago = now - 3600

        # Count recent calls
        recent_calls = [
            ts for ts in self.call_history.get(tool_name, [])
            if ts > hour_ago
        ]

        return {
            "tool_name": tool_name,
            "max_calls_per_hour": max_calls,
            "calls_last_hour": len(recent_calls),
            "remaining": max(0, max_calls - len(recent_calls)),
            "rate_limit_reached": len(recent_calls) >= max_calls
        }
