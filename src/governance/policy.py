"""Policy enforcement for tool execution."""
import fnmatch
from typing import Dict, Any, List, Optional


class ActionPolicy:
    """Enforces policies for tool execution."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize action policy.

        Args:
            config: Policy configuration
        """
        self.config = config or {}

        # Network policies
        self.allow_net = self.config.get("allow_net", ["https://*"])
        self.deny_net = self.config.get("deny_net", [])

        # Filesystem policies
        self.deny_fs_globs = self.config.get("deny_fs_globs", [
            "**/*.key",
            "**/.env",
            "**/*token*",
            "**/*secret*",
            "**/*password*",
            "**/.ssh/*",
            "**/id_rsa*",
            "**/credentials*"
        ])

        # Tool allowlist (if specified, only these tools are allowed)
        self.tool_allowlist = self.config.get("tool_allowlist", [])

        # Tool denylist (these tools are explicitly blocked)
        self.tool_denylist = self.config.get("tool_denylist", [])

        # Risk thresholds
        self.max_risk_auto = self.config.get("max_risk_auto", 0.5)  # Auto-approve below this
        self.max_risk_escrow = self.config.get("max_risk_escrow", 0.9)  # Escrow below this
        # Above max_risk_escrow = hard deny

    def is_allowed(self, tool_name: str, args: Dict[str, Any], risk_score: float = 0.0) -> tuple[bool, Optional[str]]:
        """Check if tool execution is allowed.

        Args:
            tool_name: Name of tool
            args: Tool arguments
            risk_score: Risk assessment score

        Returns:
            (allowed, reason) tuple
        """
        # Check tool allowlist/denylist
        if self.tool_allowlist and tool_name not in self.tool_allowlist:
            return False, f"Tool '{tool_name}' not in allowlist"

        if tool_name in self.tool_denylist:
            return False, f"Tool '{tool_name}' is explicitly denied"

        # Check risk score
        if risk_score >= self.max_risk_escrow:
            return False, f"Risk score {risk_score:.2f} exceeds maximum {self.max_risk_escrow}"

        # Check filesystem access
        if "path" in args or "file" in args or "file_path" in args:
            path = args.get("path") or args.get("file") or args.get("file_path")
            if path and not self._check_fs_path(path):
                return False, f"Filesystem access denied for path: {path}"

        # Check network access
        if "url" in args:
            url = args["url"]
            if not self._check_net_url(url):
                return False, f"Network access denied for URL: {url}"

        return True, None

    def requires_escrow(self, tool_name: str, args: Dict[str, Any], risk_score: float) -> bool:
        """Check if tool execution requires escrow approval.

        Args:
            tool_name: Tool name
            args: Tool arguments
            risk_score: Risk score

        Returns:
            True if escrow required
        """
        # High-risk actions require escrow
        if risk_score >= self.max_risk_auto:
            return True

        # Certain sensitive operations always require escrow
        sensitive_keywords = ["delete", "remove", "drop", "truncate", "destroy"]
        if any(kw in tool_name.lower() for kw in sensitive_keywords):
            return True

        return False

    def _check_fs_path(self, path: str) -> bool:
        """Check if filesystem path is allowed.

        Args:
            path: Filesystem path

        Returns:
            True if allowed
        """
        for glob in self.deny_fs_globs:
            if fnmatch.fnmatch(path, glob):
                return False
        return True

    def _check_net_url(self, url: str) -> bool:
        """Check if network URL is allowed.

        Args:
            url: URL to check

        Returns:
            True if allowed
        """
        # Check deny list first
        for pattern in self.deny_net:
            if fnmatch.fnmatch(url, pattern):
                return False

        # Check allow list
        if not self.allow_net:
            return True  # No restrictions

        for pattern in self.allow_net:
            if fnmatch.fnmatch(url, pattern):
                return True

        return False

    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of active policies.

        Returns:
            Policy summary dict
        """
        return {
            "allow_net": self.allow_net,
            "deny_net": self.deny_net,
            "deny_fs_globs": self.deny_fs_globs,
            "tool_allowlist": self.tool_allowlist,
            "tool_denylist": self.tool_denylist,
            "max_risk_auto": self.max_risk_auto,
            "max_risk_escrow": self.max_risk_escrow
        }


# Global policy instance
_policy = ActionPolicy()


def is_allowed(tool_name: str, args: Dict[str, Any], risk_score: float = 0.0) -> tuple[bool, Optional[str]]:
    """Check if action is allowed (convenience function).

    Args:
        tool_name: Tool name
        args: Tool arguments
        risk_score: Risk score

    Returns:
        (allowed, reason) tuple
    """
    return _policy.is_allowed(tool_name, args, risk_score)


def requires_escrow(tool_name: str, args: Dict[str, Any], risk_score: float) -> bool:
    """Check if action requires escrow (convenience function).

    Args:
        tool_name: Tool name
        args: Tool arguments
        risk_score: Risk score

    Returns:
        True if escrow required
    """
    return _policy.requires_escrow(tool_name, args, risk_score)
