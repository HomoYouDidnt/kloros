#!/usr/bin/env python3
"""
KLoROS Self-Health Check

Simple script that KLoROS can call to check if her critical processes are running
and restart them if needed.

Can be called from:
- KLoROS voice agent (via tool)
- Idle reflection
- Scheduled cron
- Observer/introspection
"""

import sys
import os

# Add src to path
sys.path.insert(0, '/home/kloros')

from src.self_heal.service_health import ServiceHealthMonitor, check_and_heal_services
import json


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="KLoROS self-health check and healing")
    parser.add_argument(
        "--heal",
        action="store_true",
        help="Automatically restart unhealthy services"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output if services are unhealthy"
    )

    args = parser.parse_args()

    monitor = ServiceHealthMonitor()

    if args.heal:
        # Heal mode: check and fix
        report = check_and_heal_services()

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            # Human-readable output
            healed = report.get("healed_services", {})

            if healed:
                print("🔧 Healed services:")
                for service, success in healed.items():
                    status = "✓" if success else "✗"
                    print(f"  {status} {service}")
            else:
                if not args.quiet:
                    print("✓ All critical services are healthy")

            # Show current status
            if not args.quiet or healed:
                print("\nCurrent status:")
                summary = report["summary"]
                print(f"  Active: {summary['active']}/{summary['total']}")
                if summary['inactive'] > 0:
                    print(f"  ⚠ Inactive: {summary['inactive']}")
                if summary['failed'] > 0:
                    print(f"  ✗ Failed: {summary['failed']}")

    else:
        # Report mode: just check
        report = monitor.get_health_report()

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            # Human-readable output
            all_healthy = (
                report["summary"]["active"] == report["summary"]["total"]
                and report["summary"]["failed"] == 0
            )

            if all_healthy and args.quiet:
                # Don't output anything if all healthy and quiet mode
                sys.exit(0)

            print("🏥 KLoROS Health Report")
            print(f"   Timestamp: {report['timestamp']}\n")

            summary = report["summary"]
            print(f"Status: {summary['active']}/{summary['total']} active")

            if not all_healthy:
                print()
                for service_name, info in report['services'].items():
                    if not info['active'] or info['failed']:
                        status_icon = "✗"
                        enabled_text = "enabled" if info['enabled'] else "disabled"

                        print(f"{status_icon} {service_name} ({enabled_text})")
                        print(f"   {info['description']}")

                        if info['failed']:
                            print(f"   Status: FAILED")
                        else:
                            print(f"   Status: Inactive")

                        if info['consecutive_failures'] > 0:
                            print(f"   Consecutive failures: {info['consecutive_failures']}")

                        print()

                print("💡 Run with --heal to automatically restart unhealthy services")

            elif not args.quiet:
                print("✓ All critical services are healthy\n")

                # Show active services
                for service_name, info in report['services'].items():
                    if info['active']:
                        print(f"  ✓ {service_name}")

    # Exit code: 0 if all healthy, 1 if any unhealthy
    if report["summary"]["active"] < report["summary"]["total"] or report["summary"]["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
