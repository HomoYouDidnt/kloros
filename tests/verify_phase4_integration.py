#!/usr/bin/env python3
"""
Phase 4 Integration Verification

Verifies that both Phase 4 scanners are properly integrated into the
introspection daemon and functioning correctly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from kloros.introspection.introspection_daemon import IntrospectionDaemon
from kloros.introspection.scanners.cross_system_pattern_scanner import CrossSystemPatternScanner
from kloros.introspection.scanners.documentation_completeness_scanner import DocumentationCompletenessScanner


def test_daemon_imports():
    """Test that daemon can import Phase 4 scanners."""
    print("✓ Phase 4 scanner imports successful")
    return True


def test_daemon_initialization():
    """Test that daemon initializes with 11 scanners."""
    print("\n[Daemon Initialization Test]")

    daemon = IntrospectionDaemon()

    scanner_count = len(daemon.scanners)
    assert scanner_count == 11, f"Expected 11 scanners, got {scanner_count}"
    print(f"✓ Daemon initialized with {scanner_count} scanners")

    executor_workers = daemon.executor._max_workers
    assert executor_workers == 11, f"Expected 11 workers, got {executor_workers}"
    print(f"✓ ThreadPoolExecutor configured with {executor_workers} workers")

    return True


def test_scanner_metadata():
    """Test that Phase 4 scanners return correct metadata."""
    print("\n[Scanner Metadata Test]")

    pattern_scanner = CrossSystemPatternScanner()
    pattern_meta = pattern_scanner.get_metadata()
    print(f"✓ CrossSystemPatternScanner metadata:")
    print(f"  - Name: {pattern_meta.name}")
    print(f"  - Description: {pattern_meta.description}")
    print(f"  - Interval: {pattern_meta.interval_seconds}s")
    print(f"  - Priority: {pattern_meta.priority}")

    assert pattern_meta.name == "cross_system_pattern_scanner"
    assert pattern_meta.interval_seconds == 1800
    assert pattern_meta.priority == 1

    docs_scanner = DocumentationCompletenessScanner()
    docs_meta = docs_scanner.get_metadata()
    print(f"\n✓ DocumentationCompletenessScanner metadata:")
    print(f"  - Name: {docs_meta.name}")
    print(f"  - Description: {docs_meta.description}")
    print(f"  - Interval: {docs_meta.interval_seconds}s")
    print(f"  - Priority: {docs_meta.priority}")

    assert docs_meta.name == "documentation_completeness_scanner"
    assert docs_meta.interval_seconds == 1800
    assert docs_meta.priority == 1

    return True


def test_daemon_compatibility():
    """Test that Phase 4 scanners implement daemon compatibility interface."""
    print("\n[Daemon Compatibility Test]")

    pattern_scanner = CrossSystemPatternScanner()
    pattern_result = pattern_scanner.scan()
    assert isinstance(pattern_result, list), "scan() must return list"
    assert len(pattern_result) == 0, "scan() must return empty list per spec"
    print("✓ CrossSystemPatternScanner.scan() returns empty list (daemon compatible)")

    docs_scanner = DocumentationCompletenessScanner()
    docs_result = docs_scanner.scan()
    assert isinstance(docs_result, list), "scan() must return list"
    assert len(docs_result) == 0, "scan() must return empty list per spec"
    print("✓ DocumentationCompletenessScanner.scan() returns empty list (daemon compatible)")

    return True


def test_primary_methods():
    """Test that Phase 4 scanners primary methods return Dict."""
    print("\n[Primary Method Test]")

    pattern_scanner = CrossSystemPatternScanner()
    if pattern_scanner.available:
        pattern_findings = pattern_scanner.scan_patterns(lookback_minutes=30)
        assert isinstance(pattern_findings, dict), "scan_patterns() must return dict"
        print(f"✓ CrossSystemPatternScanner.scan_patterns() returns Dict")
        print(f"  - Keys: {list(pattern_findings.keys())}")
    else:
        print("⚠ CrossSystemPatternScanner not available (memory system unavailable)")

    docs_scanner = DocumentationCompletenessScanner()
    if docs_scanner.available:
        docs_findings = docs_scanner.scan_documentation(lookback_days=30)
        assert isinstance(docs_findings, dict), "scan_documentation() must return dict"
        print(f"\n✓ DocumentationCompletenessScanner.scan_documentation() returns Dict")
        print(f"  - Keys: {list(docs_findings.keys())}")
    else:
        print("⚠ DocumentationCompletenessScanner not available (knowledge.db unavailable)")

    return True


def test_scanner_availability():
    """Test scanner availability in daemon context."""
    print("\n[Scanner Availability Test]")

    daemon = IntrospectionDaemon()

    scanner_names = []
    for scanner in daemon.scanners:
        meta = scanner.get_metadata()
        scanner_names.append(meta.name)

    assert "cross_system_pattern_scanner" in scanner_names
    assert "documentation_completeness_scanner" in scanner_names

    print("✓ Phase 4 scanners present in daemon.scanners:")
    for name in scanner_names:
        print(f"  - {name}")

    return True


def main():
    """Run all verification tests."""
    print("="*70)
    print("PHASE 4 INTEGRATION VERIFICATION")
    print("="*70)

    tests = [
        ("Import Test", test_daemon_imports),
        ("Daemon Initialization", test_daemon_initialization),
        ("Scanner Metadata", test_scanner_metadata),
        ("Daemon Compatibility", test_daemon_compatibility),
        ("Primary Methods", test_primary_methods),
        ("Scanner Availability", test_scanner_availability)
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ {test_name} FAILED: {e}")
            failed += 1

    print("\n" + "="*70)
    print(f"VERIFICATION RESULTS: {passed} passed, {failed} failed")
    print("="*70)

    if failed == 0:
        print("\n✓ Phase 4 integration verified successfully!")
        return 0
    else:
        print(f"\n✗ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
