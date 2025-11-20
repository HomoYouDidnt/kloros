"""
Surgical patch application with safety validation and rollback.

Builds on dev_agent/utils/diff_apply but adds:
- Git-based safety checks
- Automatic rollback on test regression
- Patch validation before application
"""
from pathlib import Path
import subprocess
import tempfile
import json
from typing import Optional, Tuple
from ..utils.diff_apply import apply_unified_diff, PatchError

class PatchApplicationError(Exception):
    """Raised when patch application fails."""
    pass

def check_git_clean(repo_root: Path) -> bool:
    """Check if git working tree is clean."""
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=repo_root,
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

def apply_patch_with_validation(
    repo_root: Path,
    diff_text: str,
    validate_fn: Optional[callable] = None,
    auto_rollback: bool = True
) -> dict:
    """
    Apply unified diff with safety checks.

    Args:
        repo_root: Repository root directory
        diff_text: Unified diff text
        validate_fn: Optional validation function (e.g., run tests)
        auto_rollback: Rollback on validation failure

    Returns:
        dict with keys: success, files_changed, created, modified, deleted,
                        validation_passed, rolled_back
    """
    repo_root = Path(repo_root).resolve()

    # Pre-flight checks
    if not repo_root.exists():
        raise PatchApplicationError(f"Repo root does not exist: {repo_root}")

    # Create git stash for safety
    stash_created = False
    try:
        subprocess.run(
            ["git", "stash", "push", "-m", "pre-patch-stash"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=10
        )
        stash_created = True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # No changes to stash, or not a git repo
        pass

    try:
        # Apply the patch using existing diff_apply infrastructure
        result = apply_unified_diff(str(repo_root), diff_text)

        # Track results
        patch_result = {
            "success": True,
            "files_changed": result.get("files_changed", 0),
            "created": result.get("created", []),
            "modified": result.get("modified", []),
            "deleted": result.get("deleted", []),
            "validation_passed": None,
            "rolled_back": False
        }

        # Run validation if provided
        if validate_fn:
            try:
                validation_passed = validate_fn()
                patch_result["validation_passed"] = validation_passed

                if not validation_passed and auto_rollback:
                    # Rollback the changes
                    subprocess.run(
                        ["git", "checkout", "HEAD", "."],
                        cwd=repo_root,
                        check=True,
                        timeout=10
                    )
                    patch_result["rolled_back"] = True
                    patch_result["success"] = False
            except Exception as e:
                patch_result["validation_error"] = str(e)
                patch_result["validation_passed"] = False

                if auto_rollback:
                    subprocess.run(
                        ["git", "checkout", "HEAD", "."],
                        cwd=repo_root,
                        timeout=10
                    )
                    patch_result["rolled_back"] = True
                    patch_result["success"] = False

        # Pop stash if we created one and didn't rollback
        if stash_created and not patch_result.get("rolled_back"):
            try:
                subprocess.run(
                    ["git", "stash", "drop"],
                    cwd=repo_root,
                    timeout=5
                )
            except (subprocess.SubprocessError, OSError):
                # Stash drop failed, not critical
                pass

        return patch_result

    except PatchError as e:
        # Patch application failed
        if stash_created:
            try:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=repo_root,
                    timeout=5
                )
            except (subprocess.SubprocessError, OSError):
                # Stash pop failed, not critical
                pass

        raise PatchApplicationError(f"Patch application failed: {e}") from e

def validate_diff_syntax(diff_text: str) -> Tuple[bool, Optional[str]]:
    """
    Validate unified diff syntax without applying.

    Returns:
        (is_valid, error_message)
    """
    try:
        # Use git apply --check with a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(diff_text)
            patch_file = f.name

        try:
            result = subprocess.run(
                ["git", "apply", "--check", patch_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return (True, None)
            else:
                return (False, result.stderr.strip())
        finally:
            Path(patch_file).unlink(missing_ok=True)
    except Exception as e:
        return (False, f"Validation error: {e}")

def compute_diff_stats(diff_text: str) -> dict:
    """
    Compute statistics about a diff without applying it.

    Returns:
        dict with: files_touched, insertions, deletions, net_change
    """
    lines = diff_text.splitlines()
    files_touched = set()
    insertions = 0
    deletions = 0

    for line in lines:
        if line.startswith('--- ') or line.startswith('+++ '):
            # Extract filename
            parts = line[4:].strip().split()
            if parts and not parts[0].startswith('/dev/null'):
                fname = parts[0]
                if fname.startswith('a/') or fname.startswith('b/'):
                    fname = fname[2:]
                files_touched.add(fname)
        elif line.startswith('+') and not line.startswith('+++'):
            insertions += 1
        elif line.startswith('-') and not line.startswith('---'):
            deletions += 1

    return {
        "files_touched": len(files_touched),
        "file_list": sorted(files_touched),
        "insertions": insertions,
        "deletions": deletions,
        "net_change": insertions - deletions,
        "total_changes": insertions + deletions
    }
