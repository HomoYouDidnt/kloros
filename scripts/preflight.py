#!/usr/bin/env python3
"""CLI wrapper for KLoROS preflight checker."""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.preflight import compute_overall_status, run_all_checks, write_json_summary


def format_check_line(status: str, name: str, details: str, width: int = 80) -> str:
    """Format a check result as an aligned line."""
    # Status column width: 4 characters (PASS/WARN/FAIL)
    # Name column width: 12 characters
    # Details: remaining space
    status_width = 4
    name_width = 12

    # Truncate name and details to fit within width
    name_truncated = name[:name_width].ljust(name_width)
    details_available_width = width - status_width - name_width - 2  # 2 for spaces

    if len(details) > details_available_width:
        details_truncated = details[:details_available_width - 3] + "..."
    else:
        details_truncated = details

    return f"{status} {name_truncated} {details_truncated}"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="KLoROS preflight checker - inspect environment and system readiness"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=str(Path.home() / ".kloros" / "preflight.json"),
        help="JSON output path (default: ~/.kloros/preflight.json)"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip optional imports for faster run; still run smoke on mock"
    )
    parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="Skip system smoke test"
    )

    args = parser.parse_args()

    try:
        # Run all checks
        check_results = run_all_checks(quick=args.quick, skip_smoke=args.no_smoke)
        overall_status = compute_overall_status(check_results)

        # Print results in aligned format
        for result in check_results:
            status, name, details, meta = result
            print(format_check_line(status, name, details))

        # Write JSON summary
        try:
            json_path = write_json_summary(check_results, overall_status, args.json_out)
            print(f"\nOVERALL: {overall_status} (written: {json_path})")
        except Exception as e:
            print(f"\nOVERALL: {overall_status} (JSON write failed: {e})")

        # Exit with appropriate code
        if overall_status == "PASS":
            sys.exit(0)
        elif overall_status == "WARN":
            sys.exit(2)
        else:  # FAIL
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nPreflight check interrupted")
        sys.exit(3)
    except Exception as e:
        print(f"Unrecoverable error: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
