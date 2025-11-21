#!/usr/bin/env python3
"""
CLI Demo Script for TestCoverageScanner

Demonstrates the test coverage scanner functionality by analyzing a small
sample codebase.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '/home/kloros/src')

from kloros.introspection.scanners.test_coverage_scanner import (
    TestCoverageScanner,
    scan_test_coverage_standalone
)


def create_sample_codebase():
    """Create a sample codebase with tests for demonstration."""
    tmp_dir = tempfile.mkdtemp(prefix='coverage_demo_')
    base_path = Path(tmp_dir)

    src_dir = base_path / 'src'
    src_dir.mkdir()

    test_dir = base_path / 'tests'
    test_dir.mkdir()

    module1 = src_dir / 'calculator.py'
    module1.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def power(a, b):
    return a ** b

def modulo(a, b):
    return a % b
""")

    module2 = src_dir / 'data_processor.py'
    module2.write_text("""
def process_data(data):
    if not data:
        return []
    return [x * 2 for x in data]

def validate_data(data):
    if not isinstance(data, list):
        raise TypeError("Data must be a list")
    return True

def save_results(results, filename):
    with open(filename, 'w') as f:
        for item in results:
            f.write(f"{item}\\n")

def load_data(filename):
    with open(filename, 'r') as f:
        return [line.strip() for line in f]

def delete_critical_data(filename):
    import os
    if os.path.exists(filename):
        os.remove(filename)
""")

    test_file1 = test_dir / 'test_calculator.py'
    test_file1.write_text("""
import sys
sys.path.insert(0, 'src')
from calculator import add, subtract, multiply

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2

def test_multiply():
    assert multiply(4, 3) == 12
""")

    test_file2 = test_dir / 'test_data_processor.py'
    test_file2.write_text("""
import sys
sys.path.insert(0, 'src')
from data_processor import process_data, validate_data

def test_process_data():
    assert process_data([1, 2, 3]) == [2, 4, 6]

def test_validate_data():
    assert validate_data([1, 2, 3]) == True
""")

    return str(src_dir), str(test_dir), tmp_dir


def main():
    print("="*70)
    print("TEST COVERAGE SCANNER - CLI DEMONSTRATION")
    print("="*70)
    print()

    print("Step 1: Initializing TestCoverageScanner...")
    scanner = TestCoverageScanner()

    if not scanner.available:
        print("ERROR: Scanner not available!")
        print("  - coverage.py available:", scanner.coverage_available)
        print("  - pytest available:", scanner.pytest_available)
        sys.exit(1)

    print("SUCCESS: Scanner initialized")
    print(f"  - coverage.py: {scanner.coverage_available}")
    print(f"  - pytest: {scanner.pytest_available}")
    print()

    print("Step 2: Scanner Metadata...")
    metadata = scanner.get_metadata()
    print(f"  Name: {metadata.name}")
    print(f"  Description: {metadata.description}")
    print(f"  Interval: {metadata.interval_seconds}s")
    print(f"  Priority: {metadata.priority}")
    print()

    print("Step 3: Creating sample codebase for testing...")
    src_dir, test_dir, tmp_dir = create_sample_codebase()
    print(f"  Source directory: {src_dir}")
    print(f"  Test directory: {test_dir}")
    print()

    print("Step 4: Running coverage scan (threshold: 70%)...")
    print("  This will analyze test coverage on the sample codebase...")
    print()

    findings = scanner.scan_test_coverage(
        threshold=70.0,
        target_path=src_dir
    )

    print("Step 5: Coverage Analysis Results...")
    print("-" * 70)
    print()

    if findings:
        summary = findings.get('coverage_summary', {})
        if summary:
            print(f"Overall Coverage: {summary.get('percent_covered', 0):.1f}%")
            print(f"Total Statements: {summary.get('total_statements', 0)}")
            print(f"Covered Statements: {summary.get('total_covered', 0)}")
            print()

        uncovered = findings.get('uncovered_modules', [])
        if uncovered:
            print(f"Uncovered Modules: {len(uncovered)}")
            for module in uncovered[:3]:
                print(f"  - {Path(module['module']).name}: {module['coverage_percent']:.1f}%")
                print(f"    Severity: {module['severity']}")
                print(f"    Lines: {module['lines_covered']}/{module['lines_total']}")

                if 'uncovered_critical' in module:
                    print(f"    Critical Functions:")
                    for func in module['uncovered_critical'][:2]:
                        print(f"      * {func['function']} (risk: {func['risk']})")
                print()

        test_patterns = findings.get('test_patterns', [])
        if test_patterns:
            print("Test Patterns Detected:")
            for pattern in test_patterns:
                print(f"  - {pattern['description']}: {pattern['value']}")
            print()

    print("Step 6: Formatted Report...")
    print("-" * 70)
    report = scanner.format_findings(findings)
    print(report)
    print()

    print("Step 7: Testing standalone function...")
    findings2, report2 = scan_test_coverage_standalone(
        threshold=80.0,
        target_path=src_dir
    )
    print("SUCCESS: Standalone function works correctly")
    print()

    print("Step 8: Cleanup...")
    import shutil
    shutil.rmtree(tmp_dir)
    print(f"Removed temporary directory: {tmp_dir}")
    print()

    print("="*70)
    print("DEMONSTRATION COMPLETE")
    print("="*70)
    print()
    print("Key Features Demonstrated:")
    print("  1. Scanner initialization with tool availability checks")
    print("  2. Metadata retrieval for introspection daemon integration")
    print("  3. Coverage analysis using coverage.py")
    print("  4. Identification of uncovered modules and critical functions")
    print("  5. Risk assessment for uncovered functions")
    print("  6. Test pattern analysis")
    print("  7. Human-readable report formatting")
    print("  8. Standalone CLI entry point")
    print()
    print("The scanner is ready for integration into the introspection daemon!")


if __name__ == "__main__":
    main()
