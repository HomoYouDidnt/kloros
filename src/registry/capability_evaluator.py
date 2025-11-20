#!/usr/bin/env python3
"""
Capability Evaluator - Health Checks and State Matrix Generator

Loads capabilities_enhanced.yaml, evaluates preconditions and health checks,
generates self_state.json with status matrix for introspection.

Governance:
- Tool-Integrity: Self-contained, testable, complete docstrings
- D-REAM-Allowed-Stack: Uses pytest, JSON, subprocess with timeouts
- Structured logging to /var/log/kloros/structured.jsonl

Purpose:
    Generate real-time capability status matrix enabling "I can / I can't" self-awareness

Outcomes:
    - Evaluates all capabilities in capabilities_enhanced.yaml
    - Writes /home/kloros/.kloros/self_state.json with status matrix
    - Logs evaluation results to structured.jsonl
    - Returns CapabilityMatrix object for programmatic access
"""

import os
import sys
import json
import subprocess
import yaml
import time
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

# Setup structured logging
logger = logging.getLogger(__name__)


class CapabilityState(Enum):
    """Capability health status."""
    OK = "ok"
    DEGRADED = "degraded"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass
class CapabilityCost:
    """Resource cost for capability execution."""
    cpu: int = 0  # CPU percentage
    mem: int = 0  # Memory in MB
    risk: str = "low"  # low, medium, high


@dataclass
class CapabilityRecord:
    """Single capability evaluation result."""
    key: str
    kind: str
    state: CapabilityState
    why: str
    provides: List[str] = field(default_factory=list)
    cost: CapabilityCost = field(default_factory=CapabilityCost)
    last_checked: str = field(default_factory=lambda: datetime.now().isoformat())
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "kind": self.kind,
            "state": self.state.value,
            "why": self.why,
            "provides": self.provides,
            "cost": asdict(self.cost),
            "last_checked": self.last_checked,
            "enabled": self.enabled
        }


@dataclass
class CapabilityMatrix:
    """Complete capability state matrix."""
    capabilities: List[CapabilityRecord] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_count: int = 0
    ok_count: int = 0
    degraded_count: int = 0
    missing_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "capabilities": [cap.to_dict() for cap in self.capabilities],
            "evaluated_at": self.evaluated_at,
            "summary": {
                "total": self.total_count,
                "ok": self.ok_count,
                "degraded": self.degraded_count,
                "missing": self.missing_count
            }
        }


class CapabilityEvaluator:
    """
    Evaluates system capabilities and generates state matrix.

    Purpose:
        Enable KLoROS to have accurate self-awareness of what she can and cannot do

    Outcomes:
        - Validates preconditions for each capability
        - Runs health checks (shell commands, Python functions, HTTP checks)
        - Generates self_state.json with capability status
        - Provides affordance-ready data for curiosity system
    """

    def __init__(self, registry_path: Optional[Path] = None, state_path: Optional[Path] = None):
        """
        Initialize capability evaluator.

        Parameters:
            registry_path: Path to capabilities_enhanced.yaml
            state_path: Path to write self_state.json
        """
        if registry_path is None:
            registry_path = Path(__file__).parent / "capabilities_enhanced.yaml"
        if state_path is None:
            state_path = Path("/home/kloros/.kloros/self_state.json")

        self.registry_path = registry_path
        self.state_path = state_path
        self.capabilities_raw: List[Dict[str, Any]] = []
        self.matrix: Optional[CapabilityMatrix] = None

    def load_capabilities(self) -> List[Dict[str, Any]]:
        """Load capabilities from YAML registry."""
        if not self.registry_path.exists():
            logger.error(f"[capability_evaluator] Registry not found: {self.registry_path}")
            return []

        try:
            with open(self.registry_path, 'r') as f:
                data = yaml.safe_load(f)
                if isinstance(data, list):
                    self.capabilities_raw = data
                    logger.info(f"[capability_evaluator] Loaded {len(data)} capabilities")
                    return data
                else:
                    logger.error(f"[capability_evaluator] Invalid YAML format (expected list)")
                    return []
        except Exception as e:
            logger.error(f"[capability_evaluator] Failed to load YAML: {e}")
            return []

    def check_precondition(self, precondition: str) -> Tuple[bool, str]:
        """
        Check a single precondition.

        Precondition formats:
            - "group:audio" → user in group
            - "path:/dev/snd readable" → path exists and is readable
            - "pipewire_session" → environment/process check
            - "module:chromadb importable" → Python module available
            - "command:piper available" → command in PATH
            - "network:internet reachable" → network connectivity
            - "env:KLR_ENABLE_CURIOSITY=1" → environment variable check
            - "systemd:dream.service active" → systemd unit status
            - "http:http://example.com reachable" → HTTP endpoint check
            - "{capability_key}:ok" → dependency on another capability

        Returns:
            (success: bool, reason: str)
        """
        try:
            # Group membership check
            if precondition.startswith("group:"):
                group = precondition.split(":", 1)[1]
                result = subprocess.run(["groups"], capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and group in result.stdout:
                    return (True, f"User in group '{group}'")
                else:
                    return (False, f"User not in group '{group}'")

            # Path existence/permission check
            elif precondition.startswith("path:"):
                parts = precondition.split(":", 1)[1].rsplit(" ", 1)
                path_str = parts[0]
                mode = parts[1] if len(parts) > 1 else "exists"

                path = Path(path_str)
                if not path.exists():
                    return (False, f"Path '{path_str}' does not exist")

                if mode == "readable":
                    if os.access(path, os.R_OK):
                        return (True, f"Path '{path_str}' is readable")
                    else:
                        return (False, f"Path '{path_str}' not readable")
                elif mode == "writable" or mode == "rw":
                    if os.access(path, os.R_OK | os.W_OK):
                        return (True, f"Path '{path_str}' is read/write")
                    else:
                        return (False, f"Path '{path_str}' not writable")
                else:
                    return (True, f"Path '{path_str}' exists")

            # Module importable check
            elif precondition.startswith("module:"):
                parts = precondition.split(":", 1)[1].split(" ", 1)
                module_name = parts[0]
                try:
                    __import__(module_name)
                    return (True, f"Module '{module_name}' importable")
                except ImportError:
                    return (False, f"Module '{module_name}' not available")

            # Command available check
            elif precondition.startswith("command:"):
                parts = precondition.split(":", 1)[1].split(" ", 1)
                command = parts[0]
                result = subprocess.run(["which", command], capture_output=True, timeout=2)
                if result.returncode == 0:
                    return (True, f"Command '{command}' available")
                else:
                    return (False, f"Command '{command}' not in PATH")

            # Environment variable check
            elif precondition.startswith("env:"):
                env_spec = precondition.split(":", 1)[1]

                # Check for numeric comparisons FIRST (before splitting on =)
                if ">=" in env_spec:
                    var, threshold_str = env_spec.split(">=", 1)
                    actual = os.getenv(var, "")
                    # Strip inline comments
                    if "#" in actual:
                        actual = actual.split("#", 1)[0].strip()
                    else:
                        actual = actual.strip()
                    try:
                        actual_num = int(actual) if actual else 0
                        threshold = int(threshold_str)
                        if actual_num >= threshold:
                            return (True, f"{var}={actual_num} >= {threshold}")
                        else:
                            return (False, f"{var}={actual_num} < {threshold}")
                    except ValueError:
                        return (False, f"Invalid numeric comparison: {env_spec}")

                elif "=" in env_spec:
                    var, expected = env_spec.split("=", 1)
                    actual = os.getenv(var, "")
                    # Strip inline comments (handles values like "1  # Enable proactive exploration")
                    if "#" in actual:
                        actual = actual.split("#", 1)[0].strip()
                    else:
                        actual = actual.strip()
                    # String comparison
                    if actual == expected:
                        return (True, f"{var}={actual}")
                    else:
                        return (False, f"{var}={actual} (expected {expected})")
                else:
                    # Just check if set
                    var = env_spec
                    if os.getenv(var):
                        return (True, f"{var} is set")
                    else:
                        return (False, f"{var} not set")

            # Systemd unit check
            elif precondition.startswith("systemd:"):
                parts = precondition.split(":", 1)[1].rsplit(" ", 1)
                unit = parts[0]
                expected_state = parts[1] if len(parts) > 1 else "active"
                result = subprocess.run(
                    ["systemctl", "is-active", unit],
                    capture_output=True, text=True, timeout=5
                )
                actual_state = result.stdout.strip()
                if actual_state == expected_state:
                    return (True, f"{unit} is {expected_state}")
                else:
                    return (False, f"{unit} is {actual_state} (expected {expected_state})")

            # HTTP endpoint check
            elif precondition.startswith("http:"):
                url = precondition.split(":", 1)[1].split()[0]  # Strip descriptive suffix like "reachable"
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code < 500:
                        return (True, f"{url} reachable (status {response.status_code})")
                    else:
                        return (False, f"{url} returned {response.status_code}")
                except requests.RequestException as e:
                    return (False, f"{url} unreachable: {str(e)[:50]}")

            # Network connectivity check
            elif precondition.startswith("network:"):
                network_type = precondition.split(":", 1)[1]
                if network_type == "internet reachable":
                    try:
                        response = requests.get("https://api.github.com", timeout=3)
                        if response.status_code < 500:
                            return (True, "Internet reachable")
                        else:
                            return (False, f"Internet check returned {response.status_code}")
                    except requests.RequestException:
                        return (False, "Internet not reachable")
                else:
                    return (False, f"Unknown network check: {network_type}")

            # PipeWire session check
            elif precondition == "pipewire_session":
                xdg_runtime = os.getenv("XDG_RUNTIME_DIR", "")
                if xdg_runtime:
                    pw_socket = Path(xdg_runtime) / "pipewire-0"
                    if pw_socket.exists():
                        return (True, "PipeWire session active")
                    else:
                        return (False, "PipeWire socket not found")
                else:
                    return (False, "XDG_RUNTIME_DIR not set")

            # Capability dependency check (format: "capability_key:ok")
            elif ":" in precondition:
                parts = precondition.split(":", 1)
                if parts[1] == "ok":
                    # Dependency on another capability - will be resolved later
                    return (True, f"Dependency check deferred: {parts[0]}")
                else:
                    return (False, f"Unknown precondition format: {precondition}")

            else:
                return (False, f"Unknown precondition: {precondition}")

        except Exception as e:
            logger.error(f"[capability_evaluator] Precondition check failed: {precondition} - {e}")
            return (False, f"Check error: {str(e)[:50]}")

    def run_health_check(self, health_check: str) -> Tuple[bool, str]:
        """
        Run a health check command.

        Health check formats:
            - "pactl list short sources" → shell command
            - "python:pragma_quick_check" → Python function call
            - "http:http://example.com" → HTTP GET request
            - "bash:test -w /path" → bash test command
            - "command:which piper" → command existence check
            - "env:KLR_ENABLE_CURIOSITY" → environment variable check
            - "systemd:dream.service status" → systemd unit status

        Returns:
            (success: bool, reason: str)
        """
        try:
            # Python function call
            if health_check.startswith("python:"):
                func_name = health_check.split(":", 1)[1]
                # Delegate to Python health check functions
                result, reason = self._run_python_health_check(func_name)
                return (result, reason)

            # HTTP GET request
            elif health_check.startswith("http:"):
                url = health_check.split(":", 1)[1]
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code < 500:
                        return (True, f"HTTP {response.status_code}")
                    else:
                        return (False, f"HTTP {response.status_code}")
                except requests.RequestException as e:
                    return (False, f"HTTP error: {str(e)[:50]}")

            # Bash test command
            elif health_check.startswith("bash:"):
                cmd = health_check.split(":", 1)[1]
                result = subprocess.run(
                    ["bash", "-c", cmd],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return (True, "Test passed")
                else:
                    return (False, f"Test failed: {result.stderr[:50]}")

            # Command which check
            elif health_check.startswith("command:"):
                cmd = health_check.split(":", 1)[1]
                result = subprocess.run(
                    cmd.split(),
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return (True, "Command succeeded")
                else:
                    return (False, f"Command failed: rc={result.returncode}")

            # Environment variable check
            elif health_check.startswith("env:"):
                var = health_check.split(":", 1)[1]
                value = os.getenv(var)
                if value:
                    # Strip inline comments (handles values like "1  # Enable proactive exploration")
                    if "#" in value:
                        value = value.split("#", 1)[0].strip()
                    else:
                        value = value.strip()
                    return (True, f"{var}={value}")
                else:
                    return (False, f"{var} not set")

            # Systemd status check
            elif health_check.startswith("systemd:"):
                parts = health_check.split(":", 1)[1].rsplit(" ", 1)
                unit = parts[0]
                result = subprocess.run(
                    ["systemctl", "is-active", unit],
                    capture_output=True, text=True, timeout=5
                )
                state = result.stdout.strip()
                if state == "active":
                    return (True, f"{unit} active")
                else:
                    return (False, f"{unit} {state}")

            # Generic shell command
            else:
                result = subprocess.run(
                    health_check.split(),
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout.strip()[:100]
                    return (True, f"OK: {output}" if output else "OK")
                else:
                    return (False, f"Failed: rc={result.returncode}")

        except subprocess.TimeoutExpired:
            return (False, "Health check timeout")
        except Exception as e:
            logger.error(f"[capability_evaluator] Health check failed: {health_check} - {e}")
            return (False, f"Error: {str(e)[:50]}")

    def _run_python_health_check(self, func_name: str) -> Tuple[bool, str]:
        """
        Run Python health check functions.

        Supported functions:
            - pragma_quick_check: SQLite PRAGMA quick_check
            - chroma_collection_count: Count ChromaDB collections
            - rag_document_count: Count RAG documents
            - vosk_model_loaded: Check Vosk model directory
            - tool_synthesis_quota_check: Check tool synthesis quotas
            - introspection_tool_count: Count introspection tools
            - playwright_browser_check: Check Playwright installation
        """
        try:
            if func_name == "pragma_quick_check":
                import sqlite3
                db_path = "/home/kloros/.kloros/memory.db"
                if not Path(db_path).exists():
                    return (False, f"Database not found: {db_path}")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA quick_check")
                result = cursor.fetchone()
                conn.close()
                if result and result[0] == "ok":
                    return (True, "SQLite quick_check: ok")
                else:
                    return (False, f"SQLite check failed: {result}")

            elif func_name == "chroma_collection_count":
                # Check if ChromaDB directory exists
                chroma_path = Path("/home/kloros/.kloros/chroma_data")
                if chroma_path.exists():
                    return (True, f"ChromaDB directory exists")
                else:
                    return (False, "ChromaDB directory not found")

            elif func_name == "rag_document_count":
                rag_path = Path("/home/kloros/rag_data/rag_store.npz")
                if rag_path.exists():
                    return (True, f"RAG store exists ({rag_path.stat().st_size} bytes)")
                else:
                    return (False, "RAG store not found")

            elif func_name == "vosk_model_loaded":
                model_path = Path("/home/kloros/models/vosk/model")
                if model_path.exists() and model_path.is_dir():
                    return (True, "Vosk model directory exists")
                else:
                    return (False, "Vosk model not found")

            elif func_name == "tool_synthesis_quota_check":
                # Check if tool synthesis database exists
                db_path = Path("/home/kloros/.kloros/synthesized_tools/tools.db")
                if db_path.exists():
                    return (True, "Tool synthesis DB exists")
                else:
                    return (False, "Tool synthesis DB not found")

            elif func_name == "introspection_tool_count":
                # Check if introspection_tools module exists
                # Note: We don't try to import it here because it requires sounddevice
                # and other runtime dependencies that are only available in KLoROS's full environment
                introspection_path = Path("/home/kloros/src/introspection_tools.py")
                if introspection_path.exists():
                    return (True, "Introspection tools module available")
                else:
                    return (False, "Introspection tools module not found")

            elif func_name == "playwright_browser_check":
                try:
                    __import__("playwright")
                    return (True, "Playwright module available")
                except ImportError:
                    return (False, "Playwright not installed")

            elif func_name == "dev_agent_check":
                # Check if dev_agent implementation exists and is functional
                dev_agent_path = Path("/home/kloros/src/dev_agent")
                policy_path = dev_agent_path / "security" / "policy.yaml"

                if not dev_agent_path.exists():
                    return (False, "Dev agent directory not found")

                if not policy_path.exists():
                    return (False, "Dev agent policy.yaml not found")

                # Check if sandbox engine is available (docker, podman, or local)
                try:
                    import shutil
                    if shutil.which("docker"):
                        return (True, "Dev agent ready (docker)")
                    elif shutil.which("podman"):
                        return (True, "Dev agent ready (podman)")
                    else:
                        return (True, "Dev agent ready (local execution)")
                except Exception:
                    return (True, "Dev agent available")

            elif func_name == "dream_availability_check":
                # Check if D-REAM is available for on-demand invocation
                # Note: D-REAM is now invoked by KLoROS autonomously, not run as persistent service
                dream_service_path = Path("/home/kloros/src/dream/dream_domain_service.py")
                dream_config_path = Path("/home/kloros/src/dream/config/dream.yaml")

                if not dream_service_path.exists():
                    return (False, "D-REAM service module not found")
                if not dream_config_path.exists():
                    return (False, "D-REAM config not found")

                # Check if at least one experiment is enabled in config
                try:
                    import yaml
                    with open(dream_config_path) as f:
                        config = yaml.safe_load(f)

                    enabled_experiments = [
                        exp for exp in config.get("experiments", [])
                        if exp.get("enabled", False)
                    ]

                    if not enabled_experiments:
                        return (False, "No experiments enabled in D-REAM config")

                    return (True, f"D-REAM ready ({len(enabled_experiments)} experiments enabled)")
                except Exception as e:
                    return (False, f"D-REAM config error: {str(e)[:50]}")

            else:
                return (False, f"Unknown Python health check: {func_name}")

        except Exception as e:
            return (False, f"Python check error: {str(e)[:50]}")

    def evaluate_capability(self, cap_data: Dict[str, Any]) -> CapabilityRecord:
        """
        Evaluate a single capability.

        Returns:
            CapabilityRecord with state, why, and metadata
        """
        key = cap_data.get("key", "unknown")
        kind = cap_data.get("kind", "unknown")
        provides = cap_data.get("provides", [])
        preconditions = cap_data.get("preconditions", [])
        health_check = cap_data.get("health_check", "")
        cost_data = cap_data.get("cost", {})
        enabled = cap_data.get("enabled", True)

        cost = CapabilityCost(
            cpu=cost_data.get("cpu", 0),
            mem=cost_data.get("mem", 0),
            risk=cost_data.get("risk", "low")
        )

        # Check if disabled in config
        if not enabled:
            return CapabilityRecord(
                key=key, kind=kind, state=CapabilityState.MISSING,
                why="Disabled in config", provides=provides, cost=cost, enabled=False
            )

        # Check preconditions
        for precond in preconditions:
            success, reason = self.check_precondition(precond)
            if not success:
                return CapabilityRecord(
                    key=key, kind=kind, state=CapabilityState.MISSING,
                    why=f"Precondition failed: {reason}", provides=provides, cost=cost
                )

        # Run health check
        if health_check:
            success, reason = self.run_health_check(health_check)
            if success:
                return CapabilityRecord(
                    key=key, kind=kind, state=CapabilityState.OK,
                    why=reason, provides=provides, cost=cost
                )
            else:
                return CapabilityRecord(
                    key=key, kind=kind, state=CapabilityState.DEGRADED,
                    why=f"Health check failed: {reason}", provides=provides, cost=cost
                )
        else:
            # No health check - assume OK if preconditions pass
            return CapabilityRecord(
                key=key, kind=kind, state=CapabilityState.OK,
                why="Preconditions met (no health check)", provides=provides, cost=cost
            )

    def evaluate_all(self) -> CapabilityMatrix:
        """
        Evaluate all capabilities and generate matrix.

        Returns:
            CapabilityMatrix with all evaluated capabilities
        """
        if not self.capabilities_raw:
            self.load_capabilities()

        records = []
        for cap_data in self.capabilities_raw:
            record = self.evaluate_capability(cap_data)
            records.append(record)

        # Count states
        ok_count = sum(1 for r in records if r.state == CapabilityState.OK)
        degraded_count = sum(1 for r in records if r.state == CapabilityState.DEGRADED)
        missing_count = sum(1 for r in records if r.state == CapabilityState.MISSING)

        self.matrix = CapabilityMatrix(
            capabilities=records,
            total_count=len(records),
            ok_count=ok_count,
            degraded_count=degraded_count,
            missing_count=missing_count
        )

        return self.matrix

    def write_state_json(self) -> bool:
        """
        Write self_state.json to disk.

        Returns:
            True if successful, False otherwise
        """
        if not self.matrix:
            logger.error("[capability_evaluator] No matrix to write (call evaluate_all first)")
            return False

        try:
            # Ensure directory exists
            self.state_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON
            with open(self.state_path, 'w') as f:
                json.dump(self.matrix.to_dict(), f, indent=2)

            logger.info(f"[capability_evaluator] Wrote state to {self.state_path}")
            return True

        except Exception as e:
            logger.error(f"[capability_evaluator] Failed to write state: {e}")
            return False

    def get_summary_text(self) -> str:
        """
        Generate human-readable summary of capability matrix.

        Returns:
            Formatted string for display
        """
        if not self.matrix:
            return "No capability matrix available"

        lines = []
        lines.append("CAPABILITY MATRIX")
        lines.append("=" * 60)
        lines.append(f"Total: {self.matrix.total_count} | OK: {self.matrix.ok_count} | "
                     f"Degraded: {self.matrix.degraded_count} | Missing: {self.matrix.missing_count}")
        lines.append("")

        # Group by state
        for state in [CapabilityState.OK, CapabilityState.DEGRADED, CapabilityState.MISSING]:
            caps = [c for c in self.matrix.capabilities if c.state == state]
            if caps:
                lines.append(f"{state.value.upper()} ({len(caps)}):")
                for cap in caps:
                    lines.append(f"  • {cap.key}: {cap.why}")
                lines.append("")

        return "\n".join(lines)


def main():
    """Self-test and demonstration."""
    print("=== Capability Evaluator Self-Test ===\n")

    evaluator = CapabilityEvaluator()
    matrix = evaluator.evaluate_all()

    print(evaluator.get_summary_text())

    # Write state file
    if evaluator.write_state_json():
        print(f"✓ Wrote state to {evaluator.state_path}")
    else:
        print(f"✗ Failed to write state")

    return matrix


if __name__ == "__main__":
    main()
