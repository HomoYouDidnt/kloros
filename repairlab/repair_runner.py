"""
RepairLab Auto-Repair Harness

Standalone tool for running repair agents on bug bundles.
Loads an agent module, applies it to a bundle, and reports test results.

Usage:
    python -m repairlab.repair_runner --bundle /tmp/bundle --agent agent.py
"""
from __future__ import annotations
import argparse, pathlib, json, importlib.util, sys, subprocess

def load_agent(agent_path: str):
    """Load repair agent from Python file.
    
    The agent module must expose:
        repair(bundle_dir: str) -> None
    
    The function should modify files in-place to fix bugs.
    """
    spec = importlib.util.spec_from_file_location("agent_mod", agent_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # expect mod.repair(bundle_dir: str) -> None (modifies files in place)
    return mod.repair

def main():
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(
        description="Run repair agent on bug bundle"
    )
    ap.add_argument("--bundle", required=True, help="Path to bundle dir")
    ap.add_argument("--agent", required=True, help="Path to python file exposing repair()")
    args = ap.parse_args()
    
    bundle = pathlib.Path(args.bundle)
    if not bundle.exists():
        print(f"Error: Bundle not found: {bundle}")
        return 1
    
    # Load agent
    try:
        repair = load_agent(args.agent)
    except Exception as e:
        print(f"Error loading agent: {e}")
        return 1

    # Run repair
    try:
        print(f"Running repair agent on {bundle}...")
        repair(str(bundle))
        print("Repair complete.")
    except Exception as e:
        print(f"Error during repair: {e}")
        return 1

    # Run pytest and print JSON result for SPICA
    print("Running tests...")
    # Support both "tests" directory and "test_*.py" files
    test_path = "tests" if (bundle / "tests").exists() else "."
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", test_path],
        cwd=bundle,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    result = {
        "returncode": proc.returncode,
        "output": proc.stdout
    }
    print("\nTest Results:")
    print(json.dumps(result, indent=2))
    
    return 0 if proc.returncode == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
