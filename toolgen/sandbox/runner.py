"""
ToolGen Sandbox Runner: Execute tests in resource-limited subprocess.

For PoC, we use subprocess with timeout. Production would use containers/cgroups.
"""
import subprocess
import sys
import pathlib
from typing import Dict, Any

def run_tests_sandboxed(bundle_dir: pathlib.Path, spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run pytest in sandboxed environment with resource limits.
    
    Args:
        bundle_dir: Path to tool bundle directory
        spec: Tool specification with constraints
    
    Returns:
        Dict with keys:
            - returncode: int (0 = all tests passed)
            - stdout: str
            - stderr: str
            - timeout: bool (True if timed out)
    """
    max_runtime = spec["constraints"]["max_runtime_sec"]
    pytest_path = pathlib.Path(sys.executable).parent / "pytest"
    
    try:
        proc = subprocess.run(
            [str(pytest_path), "-q", "test_tool.py"],
            cwd=bundle_dir,
            timeout=max_runtime,
            capture_output=True,
            text=True
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timeout": False
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Test execution exceeded {max_runtime}s timeout",
            "timeout": True
        }
