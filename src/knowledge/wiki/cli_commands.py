"""
Wiki CLI commands for klorosctl integration.

Implements:
- wiki sync
- wiki status
- wiki show capability <id>
"""

import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

KLOROS_HOME = Path("/home/kloros")
WIKI_DIR = KLOROS_HOME / "wiki"
INDEX_PATH = WIKI_DIR / "index.json"
CAPABILITIES_DIR = WIKI_DIR / "capabilities"


def run_wiki_indexer() -> Tuple[int, str]:
    """Run wiki_indexer.py and return (exit_code, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "src.wiki"],
        cwd=str(KLOROS_HOME),
        capture_output=True,
        text=True,
        env={**dict(__import__('os').environ), "PYTHONPATH": str(KLOROS_HOME)},
    )
    return result.returncode, result.stdout + result.stderr


def run_capability_docgen() -> Tuple[int, str]:
    """Run capability_docgen.py and return (exit_code, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "src.wiki.capability_docgen"],
        cwd=str(KLOROS_HOME),
        capture_output=True,
        text=True,
        env={**dict(__import__('os').environ), "PYTHONPATH": str(KLOROS_HOME)},
    )
    return result.returncode, result.stdout + result.stderr


def read_index() -> Optional[Dict]:
    """Read and parse index.json, return None if not found."""
    if not INDEX_PATH.exists():
        return None
    try:
        with open(INDEX_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def count_capabilities_with_drift() -> Dict[str, int]:
    """Count capabilities by drift status."""
    if not CAPABILITIES_DIR.exists():
        return {"ok": 0, "missing_module": 0, "mismatch": 0}

    counts = {"ok": 0, "missing_module": 0, "mismatch": 0}

    for md_file in CAPABILITIES_DIR.glob("*.md"):
        try:
            with open(md_file) as f:
                content = f.read()

            if "drift_status: ok" in content or "Status: OK" in content:
                counts["ok"] += 1
            elif "missing_module" in content.lower():
                counts["missing_module"] += 1
            elif "mismatch" in content.lower():
                counts["mismatch"] += 1
            else:
                counts["ok"] += 1
        except IOError:
            pass

    return counts


def get_capabilities_with_drift_issues() -> List[Tuple[str, str]]:
    """Return list of (capability_id, drift_status) for capabilities with drift."""
    if not CAPABILITIES_DIR.exists():
        return []

    issues = []

    for md_file in CAPABILITIES_DIR.glob("*.md"):
        try:
            with open(md_file) as f:
                content = f.read()

            cap_id = md_file.stem

            if "missing_module" in content.lower():
                issues.append((cap_id, "missing_module"))
            elif "mismatch" in content.lower():
                issues.append((cap_id, "mismatch"))

        except IOError:
            pass

    return issues


def wiki_sync() -> int:
    """Execute wiki sync: run indexer and docgen, report results."""
    logger.info("=" * 80)
    logger.info("Syncing wiki: running indexer and capability generator...")
    logger.info("=" * 80)

    logger.info("\n[1/2] Running wiki indexer...")
    exit_code_1, output_1 = run_wiki_indexer()
    if exit_code_1 != 0:
        logger.error(f"Wiki indexer failed with exit code {exit_code_1}")
        logger.error(output_1)
        return 1
    logger.info("✓ Wiki indexer completed")

    logger.info("\n[2/2] Running capability docgen...")
    exit_code_2, output_2 = run_capability_docgen()
    if exit_code_2 != 0:
        logger.error(f"Capability docgen failed with exit code {exit_code_2}")
        logger.error(output_2)
        return 1
    logger.info("✓ Capability docgen completed")

    index = read_index()
    if index:
        num_modules = len(index.get("modules", {}))
        drift_counts = count_capabilities_with_drift()

        logger.info("\n" + "=" * 80)
        logger.info("Sync Summary:")
        logger.info("=" * 80)
        logger.info(f"  Modules indexed: {num_modules}")
        logger.info(f"  Capabilities documented: {sum(drift_counts.values())}")
        logger.info(f"  Drift status:")
        logger.info(f"    - OK: {drift_counts['ok']}")
        logger.info(f"    - Missing module: {drift_counts['missing_module']}")
        logger.info(f"    - Mismatch: {drift_counts['mismatch']}")
        logger.info("=" * 80)
    else:
        logger.warning("Could not read index.json for summary")

    return 0


def wiki_status() -> int:
    """Show wiki status overview."""
    index = read_index()

    if not index:
        logger.error("Could not read wiki index. Run 'klorosctl wiki sync' first.")
        return 1

    num_modules = len(index.get("modules", {}))
    drift_counts = count_capabilities_with_drift()
    total_capabilities = sum(drift_counts.values())
    drift_issues = get_capabilities_with_drift_issues()

    logger.info("=" * 80)
    logger.info("Wiki Status")
    logger.info("=" * 80)

    logger.info(f"\nModule Count:")
    logger.info(f"  Total modules: {num_modules}")

    logger.info(f"\nCapability Count:")
    logger.info(f"  Total capabilities: {total_capabilities}")

    logger.info(f"\nDrift Summary:")
    logger.info(f"  OK: {drift_counts['ok']}")
    logger.info(f"  Missing module: {drift_counts['missing_module']}")
    logger.info(f"  Mismatch: {drift_counts['mismatch']}")

    if drift_issues:
        logger.info(f"\nCapabilities with drift issues:")
        for cap_id, status in drift_issues:
            logger.info(f"  - {cap_id}: {status}")
    else:
        logger.info(f"\nNo capabilities with drift issues found.")

    logger.info("=" * 80)
    return 0


def wiki_show_capability(cap_id: str) -> int:
    """Display a capability markdown file."""
    cap_path = CAPABILITIES_DIR / f"{cap_id}.md"

    if not cap_path.exists():
        logger.error(f"Capability '{cap_id}' not found at {cap_path}")
        return 1

    try:
        with open(cap_path) as f:
            content = f.read()

        logger.info("=" * 80)
        logger.info(f"Capability: {cap_id}")
        logger.info("=" * 80)
        logger.info(content)
        logger.info("=" * 80)

        return 0
    except IOError as e:
        logger.error(f"Error reading capability file: {e}")
        return 1


def main():
    """Main entry point for wiki commands."""
    if len(sys.argv) < 2:
        logger.error("Usage: python -m src.wiki.cli_commands <command> [args]")
        logger.error("Commands: sync, status, show")
        return 1

    command = sys.argv[1]

    if command == "sync":
        return wiki_sync()
    elif command == "status":
        return wiki_status()
    elif command == "show":
        if len(sys.argv) < 4 or sys.argv[2] != "capability":
            logger.error("Usage: python -m src.wiki.cli_commands show capability <id>")
            return 1
        cap_id = sys.argv[3]
        return wiki_show_capability(cap_id)
    else:
        logger.error(f"Unknown wiki command: {command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
