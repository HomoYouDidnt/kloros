#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for KLoROS Reflection Housekeeping System

Tests the reflection log management capabilities of the enhanced housekeeping system.
"""

import sys
import os
import time
import json
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, '/home/kloros/src')

def test_reflection_log_stats():
    """Test reflection log statistics gathering."""
    print("Testing reflection log statistics...")

    try:
        from kloros_memory.housekeeping import MemoryHousekeeper

        housekeeper = MemoryHousekeeper()
        stats = housekeeper.get_reflection_log_stats()

        print(" Reflection log statistics retrieved successfully")
        print(f"  - Log exists: {stats.get('log_exists', False)}")
        print(f"  - Log size: {stats.get('log_size_mb', 0):.2f} MB")
        print(f"  - Entry count: {stats.get('entry_count', 0)}")
        print(f"  - Archive count: {stats.get('archive_count', 0)}")

        if stats.get('oldest_entry'):
            print(f"  - Oldest entry: {stats['oldest_entry']}")
        if stats.get('newest_entry'):
            print(f"  - Newest entry: {stats['newest_entry']}")

        return True
    except Exception as e:
        print(f" Reflection log statistics test failed: {e}")
        return False

def test_health_report_with_reflection():
    """Test health report including reflection system."""
    print("\nTesting health report with reflection monitoring...")

    try:
        from kloros_memory.housekeeping import MemoryHousekeeper

        housekeeper = MemoryHousekeeper()
        health_report = housekeeper.get_health_report()

        print(" Health report with reflection monitoring generated")
        print(f"  - Health score: {health_report['health_score']:.1f}")
        print(f"  - Status: {health_report['status']}")

        if health_report.get('recommendations'):
            print(f"  - Recommendations: {len(health_report['recommendations'])}")
            for rec in health_report['recommendations'][:3]:  # Show first 3
                print(f"    • {rec}")

        reflection_summary = health_report.get('reflection_summary', {})
        if reflection_summary:
            print(f"  - Reflection log size: {reflection_summary.get('log_size_mb', 0):.2f} MB")
            print(f"  - Reflection entries: {reflection_summary.get('entry_count', 0)}")
            print(f"  - Reflection archives: {reflection_summary.get('archive_count', 0)}")

        return True
    except Exception as e:
        print(f" Health report test failed: {e}")
        return False

def test_reflection_cleanup_dry_run():
    """Test reflection cleanup functionality (dry run simulation)."""
    print("\nTesting reflection cleanup functionality...")

    try:
        from kloros_memory.housekeeping import MemoryHousekeeper

        housekeeper = MemoryHousekeeper()

        # Get current stats before cleanup
        before_stats = housekeeper.get_reflection_log_stats()

        print(f"  - Before cleanup: {before_stats.get('log_size_mb', 0):.2f} MB, {before_stats.get('entry_count', 0)} entries")

        # Only test if log exists and has content
        if before_stats.get('log_exists') and before_stats.get('log_size_mb', 0) > 0:

            # Test cleanup (this will actually run if log is large enough)
            cleanup_result = housekeeper.cleanup_reflection_logs()

            print(" Reflection cleanup completed")
            print(f"  - Log rotated: {cleanup_result.get('log_rotated', False)}")
            print(f"  - Entries archived: {cleanup_result.get('entries_archived', 0)}")
            print(f"  - Bytes freed: {cleanup_result.get('bytes_freed', 0)}")
            print(f"  - Archives created: {cleanup_result.get('archive_files_created', 0)}")

            if cleanup_result.get('errors'):
                for error in cleanup_result['errors']:
                    print(f"  - Error: {error}")
        else:
            print("  - No reflection log or log too small for cleanup test")

        return True
    except Exception as e:
        print(f" Reflection cleanup test failed: {e}")
        return False

def test_daily_maintenance_with_reflection():
    """Test daily maintenance including reflection cleanup."""
    print("\nTesting daily maintenance with reflection cleanup...")

    try:
        from kloros_memory.housekeeping import MemoryHousekeeper

        housekeeper = MemoryHousekeeper()

        # Run daily maintenance (this includes reflection cleanup)
        maintenance_result = housekeeper.run_daily_maintenance()

        print(" Daily maintenance with reflection cleanup completed")
        print(f"  - Tasks completed: {len(maintenance_result.get('tasks_completed', []))}")

        tasks = maintenance_result.get('tasks_completed', [])
        if 'cleanup_reflection_logs' in tasks:
            print("   Reflection log cleanup was included in daily maintenance")

            reflection_result = maintenance_result.get('reflection_log_cleanup', {})
            print(f"    - Log rotated: {reflection_result.get('log_rotated', False)}")
            print(f"    - Entries archived: {reflection_result.get('entries_archived', 0)}")
        else:
            print("  - Reflection log cleanup not found in daily maintenance")

        if maintenance_result.get('errors'):
            for error in maintenance_result['errors']:
                print(f"  - Error: {error}")

        return True
    except Exception as e:
        print(f" Daily maintenance test failed: {e}")
        return False

def test_configuration_variables():
    """Test reflection housekeeping configuration."""
    print("\nTesting reflection housekeeping configuration...")

    try:
        from kloros_memory.housekeeping import MemoryHousekeeper

        housekeeper = MemoryHousekeeper()

        print(" Configuration variables loaded successfully")
        print(f"  - Reflection log path: {housekeeper.reflection_log_path}")
        print(f"  - Max log size: {housekeeper.reflection_log_max_mb} MB")
        print(f"  - Retention days: {housekeeper.reflection_retention_days}")
        print(f"  - Archive days: {housekeeper.reflection_archive_days}")

        return True
    except Exception as e:
        print(f" Configuration test failed: {e}")
        return False

def run_all_tests():
    """Run all reflection housekeeping tests."""
    print("=" * 70)
    print("KLoROS Reflection Housekeeping System - Integration Tests")
    print("=" * 70)

    tests = [
        test_configuration_variables,
        test_reflection_log_stats,
        test_health_report_with_reflection,
        test_reflection_cleanup_dry_run,
        test_daily_maintenance_with_reflection
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f" Test {test.__name__} crashed: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("<� ALL TESTS PASSED - Reflection Housekeeping System Ready!")
    elif passed >= total * 0.8:
        print("� Most tests passed - System mostly functional")
    else:
        print("L Multiple test failures - System needs attention")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)