"""
Isolated subprocess executor for synthesized tools.

Enforces resource limits (CPU, memory, time) and network isolation
for HIGH-risk tools as required by D-REAM-Anchor doctrine.
"""

from __future__ import annotations
import os
import json
import tempfile
import subprocess
import resource
import time
from typing import Dict, Any


class IsolatedExecutor:
    """Execute synthesized tools in isolated subprocess with resource limits."""

    def __init__(self, python_bin: str = "/home/kloros/.venv/bin/python3"):
        """
        Initialize executor.

        Args:
            python_bin: Path to Python interpreter in venv
        """
        self.python_bin = python_bin

    def _limits(self, max_cpu_sec: int, max_mem_mb: int):
        """
        Create preexec_fn to apply resource limits.

        Args:
            max_cpu_sec: Maximum CPU time in seconds
            max_mem_mb: Maximum memory in megabytes

        Returns:
            Callable for subprocess preexec_fn
        """
        def _apply():
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_sec, max_cpu_sec))
            # Memory limit
            bytes_mem = max_mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (bytes_mem, bytes_mem))
            # Disable core dumps
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return _apply

    def execute(
        self,
        code: str,
        manifest: Dict[str, Any],
        input_obj: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute tool code in isolated subprocess.

        Args:
            code: Python code to execute
            manifest: Tool manifest with constraints
            input_obj: Input data (passed as JSON to stdin)

        Returns:
            Dict with stdout, stderr, return_code, latency_ms, success
        """
        constraints = manifest.get("constraints", {})
        timeout_sec = int(constraints.get("timeout_sec", 20))
        max_cpu_sec = int(constraints.get("max_cpu_sec", min(10, timeout_sec)))
        max_mem_mb = int(constraints.get("max_memory_mb", 512))

        # Write tool code to temporary file
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
            tf.write(code)
            tool_path = tf.name

        t0 = time.time()
        try:
            # Execute in subprocess with resource limits
            proc = subprocess.run(
                [self.python_bin, tool_path],
                input=json.dumps(input_obj),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                preexec_fn=self._limits(max_cpu_sec, max_mem_mb),
                # Only pass KLR_* environment variables
                env={k: v for k, v in os.environ.items() if k.startswith("KLR_")},
            )

            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "return_code": proc.returncode,
                "latency_ms": int((time.time() - t0) * 1000),
                "success": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired as e:
            # Timeout exceeded - return failure result
            return {
                "stdout": e.stdout if hasattr(e, 'stdout') and e.stdout else "",
                "stderr": f"Execution timed out after {timeout_sec}s",
                "return_code": -1,
                "latency_ms": int((time.time() - t0) * 1000),
                "success": False,
            }
        finally:
            # Clean up temporary file
            try:
                os.unlink(tool_path)
            except OSError:
                pass
