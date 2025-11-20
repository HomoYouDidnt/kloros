#!/usr/bin/env python3
"""
D-REAM Safety Gate Module
Centralized safety controls and resource limits.
"""

import os
import signal
import resource
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    """Safety configuration with limits and constraints."""
    allowed_paths: List[str] = field(default_factory=lambda: ["/home/kloros/"])
    blocked_paths: List[str] = field(default_factory=lambda: ["/", "/etc", "/usr", "/bin"])
    max_cpu_s: int = 300
    max_mem_mb: int = 4096
    max_file_size_mb: int = 100
    max_files_open: int = 100
    dry_run: bool = True
    require_approval: bool = True
    allow_network: bool = False
    timeout_s: int = 600

    @classmethod
    def from_yaml(cls, path: str) -> 'SafetyConfig':
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: str):
        """Save configuration to YAML file."""
        import yaml
        data = {
            'allowed_paths': self.allowed_paths,
            'blocked_paths': self.blocked_paths,
            'max_cpu_s': self.max_cpu_s,
            'max_mem_mb': self.max_mem_mb,
            'max_file_size_mb': self.max_file_size_mb,
            'max_files_open': self.max_files_open,
            'dry_run': self.dry_run,
            'require_approval': self.require_approval,
            'allow_network': self.allow_network,
            'timeout_s': self.timeout_s
        }
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


class SafetyGate:
    """Safety gate with resource limits and access control."""

    def __init__(self, cfg: SafetyConfig):
        """
        Initialize safety gate.

        Args:
            cfg: Safety configuration
        """
        self.cfg = cfg
        self.start_time = time.time()
        self.violations = []
        self.approved_operations = set()
        self._timeout_timer = None

    def enforce_limits(self):
        """Enforce resource limits on current process."""
        try:
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, 
                             (self.cfg.max_cpu_s, self.cfg.max_cpu_s))
            logger.info(f"CPU limit set to {self.cfg.max_cpu_s}s")

            # Memory limit (address space)
            mem_bytes = self.cfg.max_mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            logger.info(f"Memory limit set to {self.cfg.max_mem_mb}MB")

            # File size limit
            file_bytes = self.cfg.max_file_size_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
            logger.info(f"File size limit set to {self.cfg.max_file_size_mb}MB")

            # Number of open files
            resource.setrlimit(resource.RLIMIT_NOFILE, 
                             (self.cfg.max_files_open, self.cfg.max_files_open))
            logger.info(f"Open files limit set to {self.cfg.max_files_open}")

            # Set up timeout
            if self.cfg.timeout_s > 0:
                self._setup_timeout()

        except Exception as e:
            logger.warning(f"Failed to set some limits: {e}")

    def _setup_timeout(self):
        """Set up process timeout."""
        def timeout_handler():
            logger.error(f"Process timeout after {self.cfg.timeout_s}s")
            os.kill(os.getpid(), signal.SIGTERM)

        self._timeout_timer = threading.Timer(self.cfg.timeout_s, timeout_handler)
        self._timeout_timer.daemon = True
        self._timeout_timer.start()

    def cancel_timeout(self):
        """Cancel timeout timer if set."""
        if self._timeout_timer:
            self._timeout_timer.cancel()

    def check_path(self, path: str, operation: str = "write") -> bool:
        """
        Check if path operation is allowed.

        Args:
            path: Path to check
            operation: Type of operation (read/write/execute)

        Returns:
            True if allowed

        Raises:
            PermissionError if blocked
        """
        path = Path(path).resolve()
        path_str = str(path)

        # Check blocked paths first
        for blocked in self.cfg.blocked_paths:
            if path_str.startswith(blocked):
                self._record_violation(f"{operation} blocked", path_str)
                raise PermissionError(f"{operation} blocked: {path_str}")

        # Check allowed paths
        allowed = any(path_str.startswith(allowed) for allowed in self.cfg.allowed_paths)
        if not allowed:
            self._record_violation(f"{operation} not in allowlist", path_str)
            raise PermissionError(f"{operation} not in allowlist: {path_str}")

        logger.debug(f"Path check passed: {operation} {path_str}")
        return True

    def check_network(self, host: str, port: int) -> bool:
        """
        Check if network access is allowed.

        Args:
            host: Target host
            port: Target port

        Returns:
            True if allowed

        Raises:
            PermissionError if blocked
        """
        if not self.cfg.allow_network:
            self._record_violation("network access blocked", f"{host}:{port}")
            raise PermissionError(f"Network access blocked: {host}:{port}")
        return True

    def allow_mutation(self) -> bool:
        """
        Check if mutations are allowed.

        Returns:
            True if not in dry-run mode
        """
        if self.cfg.dry_run:
            logger.info("Dry-run mode: mutations blocked")
            return False
        return True

    def request_approval(self, operation: str, details: Dict[str, Any]) -> bool:
        """
        Request approval for an operation.

        Args:
            operation: Operation type
            details: Operation details

        Returns:
            True if approved
        """
        if not self.cfg.require_approval:
            return True

        # Generate approval key
        approval_key = f"{operation}:{hash(frozenset(details.items()))}"
        
        if approval_key in self.approved_operations:
            return True

        # In production, this would interact with approval system
        logger.warning(f"Approval required for {operation}: {details}")
        
        # For testing, auto-approve in non-dry-run mode
        if not self.cfg.dry_run:
            self.approved_operations.add(approval_key)
            return True

        return False

    def _record_violation(self, violation_type: str, details: str):
        """Record a safety violation."""
        violation = {
            'time': time.time() - self.start_time,
            'type': violation_type,
            'details': details
        }
        self.violations.append(violation)
        logger.warning(f"Safety violation: {violation_type} - {details}")

    def get_violations(self) -> List[Dict[str, Any]]:
        """Get list of recorded violations."""
        return self.violations

    def check_resource_usage(self) -> Dict[str, Any]:
        """Check current resource usage against limits."""
        usage = {}
        
        try:
            # CPU time
            cpu_usage = resource.getrusage(resource.RUSAGE_SELF)
            usage['cpu_time'] = cpu_usage.ru_utime + cpu_usage.ru_stime
            usage['cpu_limit'] = self.cfg.max_cpu_s
            usage['cpu_percent'] = (usage['cpu_time'] / self.cfg.max_cpu_s * 100) if self.cfg.max_cpu_s > 0 else 0

            # Memory
            usage['mem_mb'] = cpu_usage.ru_maxrss / 1024  # Convert KB to MB
            usage['mem_limit'] = self.cfg.max_mem_mb
            usage['mem_percent'] = (usage['mem_mb'] / self.cfg.max_mem_mb * 100) if self.cfg.max_mem_mb > 0 else 0

            # Time elapsed
            usage['elapsed_s'] = time.time() - self.start_time
            usage['timeout_s'] = self.cfg.timeout_s

            # Check if approaching limits
            if usage['cpu_percent'] > 80:
                logger.warning(f"Approaching CPU limit: {usage['cpu_percent']:.1f}%")
            if usage['mem_percent'] > 80:
                logger.warning(f"Approaching memory limit: {usage['mem_percent']:.1f}%")

        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")

        return usage


class SafeContext:
    """Context manager for safe execution."""

    def __init__(self, safety_gate: SafetyGate):
        self.gate = safety_gate

    def __enter__(self):
        """Enter safe context."""
        self.gate.enforce_limits()
        logger.info("Entered safe execution context")
        return self.gate

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit safe context."""
        self.gate.cancel_timeout()
        
        if exc_type:
            logger.error(f"Exception in safe context: {exc_val}")
        
        # Report resource usage
        usage = self.gate.check_resource_usage()
        logger.info(f"Resource usage: CPU={usage.get('cpu_time', 0):.1f}s "
                   f"({usage.get('cpu_percent', 0):.1f}%), "
                   f"Mem={usage.get('mem_mb', 0):.1f}MB "
                   f"({usage.get('mem_percent', 0):.1f}%)")

        # Report violations
        violations = self.gate.get_violations()
        if violations:
            logger.warning(f"Safety violations: {len(violations)}")
            for v in violations:
                logger.warning(f"  - {v['type']}: {v['details']}")


def create_default_config() -> SafetyConfig:
    """Create default safety configuration."""
    return SafetyConfig(
        allowed_paths=[
            "/home/kloros/src/",
            "/home/kloros/.kloros/",
            "/tmp/dream/"
        ],
        blocked_paths=[
            "/etc",
            "/usr",
            "/bin",
            "/boot",
            "/dev",
            "/proc",
            "/sys"
        ],
        max_cpu_s=600,
        max_mem_mb=8192,
        max_file_size_mb=100,
        dry_run=True
    )


def create_allowlist_yaml(path: str = "safety/allowlist.yaml"):
    """Create example allowlist YAML."""
    config = create_default_config()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    config.to_yaml(path)
    logger.info(f"Created allowlist at {path}")
