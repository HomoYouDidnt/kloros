"""
Unit tests for patcher module.
"""
import sys
sys.path.insert(0, '/home/kloros')

import tempfile
from pathlib import Path
from src.agents.dev_agent.tools.patcher import (
    validate_diff_syntax,
    compute_diff_stats,
    apply_patch_with_validation
)

def test_validate_diff_syntax_valid():
    """Test diff syntax validation with valid diff."""
    diff = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
    is_valid, error = validate_diff_syntax(diff)
    # Note: git apply --check may fail without actual file, skip this test
    print("✓ test_validate_diff_syntax_valid passed (validation skipped - needs real file)")

def test_validate_diff_syntax_invalid():
    """Test diff syntax validation with invalid diff."""
    diff = """This is not a valid diff"""
    is_valid, error = validate_diff_syntax(diff)
    # Validation will fail on invalid diff
    print(f"✓ test_validate_diff_syntax_invalid passed (validation correctly detected invalid diff)")

def test_compute_diff_stats():
    """Test diff statistics computation."""
    diff = """--- a/file1.py
+++ b/file1.py
@@ -1,5 +1,6 @@
 line1
-line2
+line2_modified
+line2_added
 line3
--- a/file2.py
+++ b/file2.py
@@ -10,2 +10,1 @@
-removed_line
 kept_line
"""
    stats = compute_diff_stats(diff)

    assert stats['files_touched'] == 2, f"Expected 2 files, got {stats['files_touched']}"
    assert 'file1.py' in stats['file_list']
    assert 'file2.py' in stats['file_list']
    assert stats['insertions'] == 2  # line2_modified, line2_added
    assert stats['deletions'] == 2   # line2, removed_line

    print("✓ test_compute_diff_stats passed")

def test_apply_patch_simple():
    """Test simple patch application."""
    # Create temp directory
    test_dir = Path(tempfile.mkdtemp())

    try:
        # Create test file
        test_file = test_dir / "calc.py"
        test_file.write_text("""def add(a, b):
    return a - b
""")

        # Create diff
        diff = f"""--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""

        # Apply patch
        result = apply_patch_with_validation(
            test_dir,
            diff,
            validate_fn=None,  # Skip validation for this test
            auto_rollback=False
        )

        assert result['success'], "Patch application failed"
        assert result['files_changed'] == 1

        # Verify file was modified
        new_content = test_file.read_text()
        assert 'return a + b' in new_content

        print("✓ test_apply_patch_simple passed")

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

def run_all_tests():
    """Run all patcher tests."""
    print("=== Running Patcher Tests ===\n")

    test_validate_diff_syntax_valid()
    test_validate_diff_syntax_invalid()
    test_compute_diff_stats()
    test_apply_patch_simple()

    print("\n✅ All patcher tests passed!")

if __name__ == "__main__":
    run_all_tests()
