#!/usr/bin/env python3
"""
Bug Injection System for Code Repair Domain

Injects realistic, fixable bugs into sandbox copies of code for testing
the repair system's ability to detect and fix issues autonomously.

Bug Types:
- Syntax errors (missing colons, parentheses)
- Type errors (wrong types, missing imports)
- Logic errors (off-by-one, wrong operators)
- Name errors (undefined variables, typos)
"""
import ast
import random
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class InjectedBug:
    """Represents a bug injected into code."""
    bug_type: str  # "syntax", "type", "logic", "name"
    file_path: Path
    line_number: int
    original_line: str
    buggy_line: str
    description: str
    difficulty: str  # "easy", "medium", "hard"

class BugInjector:
    """Injects realistic bugs into Python code for testing."""

    # Bug templates by type - return None if no change
    @staticmethod
    def _remove_colon(line: str) -> Optional[str]:
        """Remove colon from end of line."""
        if line.rstrip().endswith(':'):
            return line.rstrip().rstrip(':') + '\n'
        return None

    @staticmethod
    def _missing_paren(line: str) -> Optional[str]:
        """Remove opening or closing parenthesis."""
        if '(' in line and ')' in line:
            # Remove last )
            idx = line.rfind(')')
            # Preserve newline if present
            if line.endswith('\n'):
                return line[:idx] + line[idx+1:-1] + '\n'
            return line[:idx] + line[idx+1:]
        return None

    @staticmethod
    def _missing_quote(line: str) -> Optional[str]:
        """Remove one quote from a string."""
        if line.count('"') >= 2:
            # Remove first quote - preserve newline
            result = line.replace('"', '', 1)
            if line.endswith('\n') and not result.endswith('\n'):
                result += '\n'
            return result
        return None

    SYNTAX_BUGS = [
        ("remove_colon", _remove_colon.__func__),
        ("missing_paren", _missing_paren.__func__),
        ("missing_quote", _missing_quote.__func__),
    ]

    @staticmethod
    def _off_by_one(line: str) -> Optional[str]:
        """Create off-by-one error in range."""
        if 'range(' in line and 'range(1,' not in line:
            return line.replace('range(', 'range(1, ', 1)
        return None

    @staticmethod
    def _wrong_operator(line: str) -> Optional[str]:
        """Change comparison operator."""
        if '==' in line:
            return line.replace('==', '!=', 1)
        return None

    LOGIC_BUGS = [
        ("off_by_one", _off_by_one.__func__),
        ("wrong_operator", _wrong_operator.__func__),
    ]

    @staticmethod
    def _typo_variable(line: str) -> Optional[str]:
        """Introduce typo in common variable name."""
        if 'result' in line and 'result' not in ['@', '#']:
            return line.replace('result', 'resutl', 1)
        return None

    NAME_BUGS = [
        ("typo_variable", _typo_variable.__func__),
    ]

    def __init__(self, repo_root: Path):
        """Initialize bug injector.

        Args:
            repo_root: Repository root directory
        """
        self.repo_root = repo_root
        self.random = random.Random(42)  # Deterministic for reproducibility

    def get_injectable_files(self, max_files: int = 5) -> List[Path]:
        """Find Python files suitable for bug injection.

        Args:
            max_files: Maximum number of files to return

        Returns:
            List of Python file paths
        """
        python_files = []
        src_dir = self.repo_root / "src"

        if not src_dir.exists():
            return []

        for py_file in src_dir.rglob("*.py"):
            # Skip __init__.py, test files, and generated files
            if py_file.name == "__init__.py":
                continue
            if "test_" in py_file.name or "_test.py" in py_file.name:
                continue
            if ".venv" in str(py_file) or "node_modules" in str(py_file):
                continue

            python_files.append(py_file)

        # Return random sample
        return self.random.sample(python_files, min(len(python_files), max_files))

    def inject_bug(self, file_path: Path, bug_type: str = "auto") -> Optional[InjectedBug]:
        """Inject a single bug into a file.

        Args:
            file_path: Path to Python file
            bug_type: Type of bug to inject ("syntax", "logic", "name", or "auto")

        Returns:
            InjectedBug if successful, None if injection failed
        """
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[bug-injector] Failed to read {file_path}: {e}")
            return None

        if len(lines) < 5:  # Skip very small files (need at least 5 lines)
            return None

        # Select bug type
        if bug_type == "auto":
            bug_type = self.random.choice(["syntax", "logic", "name"])

        # Get bug templates for this type
        if bug_type == "syntax":
            templates = self.SYNTAX_BUGS
        elif bug_type == "logic":
            templates = self.LOGIC_BUGS
        elif bug_type == "name":
            templates = self.NAME_BUGS
        else:
            return None

        # Try to inject bug (max 20 attempts)
        for _ in range(20):
            # Avoid first 2 and last 2 lines
            min_line = min(2, len(lines) - 3)
            max_line = max(min_line + 1, len(lines) - 2)

            if min_line >= max_line:
                return None  # File too small

            line_idx = self.random.randint(min_line, max_line)
            original_line = lines[line_idx]

            # Skip blank lines and comments
            if not original_line.strip() or original_line.strip().startswith('#'):
                continue

            # Try each template
            for bug_name, bug_func in templates:
                buggy_line = bug_func(original_line)

                # Check if bug actually changed the line (None means no change)
                if buggy_line is not None and buggy_line != original_line:
                    # Apply bug
                    lines[line_idx] = buggy_line

                    # Write modified file
                    try:
                        with open(file_path, 'w') as f:
                            f.writelines(lines)
                    except Exception as e:
                        print(f"[bug-injector] Failed to write {file_path}: {e}")
                        return None

                    return InjectedBug(
                        bug_type=bug_type,
                        file_path=file_path,
                        line_number=line_idx + 1,
                        original_line=original_line.rstrip(),
                        buggy_line=buggy_line.rstrip(),
                        description=f"{bug_name}: {original_line.strip()} → {buggy_line.strip()}",
                        difficulty="easy" if bug_type == "syntax" else "medium"
                    )

        return None

    def create_sandbox(self, target_dir: Optional[Path] = None) -> Path:
        """Create a sandbox copy of the repository.

        Args:
            target_dir: Optional target directory (default: temp dir)

        Returns:
            Path to sandbox directory
        """
        if target_dir is None:
            target_dir = Path(tempfile.mkdtemp(prefix="kloros_sandbox_"))

        # Copy critical files only (not entire repo)
        # Use ignore_errors to skip permission-denied files
        src_dir = self.repo_root / "src"
        if src_dir.exists():
            def ignore_permission_errors(src, names):
                """Ignore directories/files that cause permission errors."""
                ignored = []
                for name in names:
                    path = Path(src) / name
                    try:
                        # Try to access the path
                        path.stat()
                    except PermissionError:
                        ignored.append(name)
                return ignored

            try:
                shutil.copytree(
                    src_dir,
                    target_dir / "src",
                    dirs_exist_ok=True,
                    ignore=ignore_permission_errors
                )
            except shutil.Error as e:
                # Some files failed, but continue with what we have
                print(f"[bug-injector] Warning: Some files skipped due to permissions")

        # Copy pyproject.toml if exists
        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            try:
                shutil.copy(pyproject, target_dir / "pyproject.toml")
            except PermissionError:
                pass

        return target_dir

    def inject_sandbox_bugs(
        self,
        num_bugs: int = 3,
        bug_types: Optional[List[str]] = None
    ) -> Tuple[Path, List[InjectedBug]]:
        """Create sandbox and inject multiple bugs.

        Args:
            num_bugs: Number of bugs to inject
            bug_types: Optional list of bug types (default: all types)

        Returns:
            Tuple of (sandbox_path, list of injected bugs)
        """
        # Create sandbox
        sandbox = self.create_sandbox()

        # Get injectable files
        injectable_files = self.get_injectable_files(max_files=num_bugs)

        if not injectable_files:
            print("[bug-injector] No injectable files found")
            return sandbox, []

        # Inject bugs
        injected_bugs = []
        for file_path in injectable_files[:num_bugs]:
            # Map to sandbox path
            relative_path = file_path.relative_to(self.repo_root)
            sandbox_file = sandbox / relative_path

            if not sandbox_file.exists():
                continue

            # Inject bug
            bug_type = bug_types[len(injected_bugs)] if bug_types else "auto"
            bug = self.inject_bug(sandbox_file, bug_type=bug_type)

            if bug:
                injected_bugs.append(bug)

        print(f"[bug-injector] Injected {len(injected_bugs)} bugs in sandbox {sandbox}")
        for bug in injected_bugs:
            print(f"  - {bug.bug_type}: {bug.file_path.name}:{bug.line_number}")

        return sandbox, injected_bugs

def create_bug_simulation_test(
    repo_root: Path,
    num_bugs: int = 1,
    bug_types: Optional[List[str]] = None
) -> Dict:
    """Create a bug simulation test for PHASE.

    Args:
        repo_root: Repository root directory
        num_bugs: Number of bugs to inject
        bug_types: Optional list of bug types

    Returns:
        Dict with sandbox path, injected bugs, and test metadata
    """
    injector = BugInjector(repo_root)
    sandbox, bugs = injector.inject_sandbox_bugs(num_bugs=num_bugs, bug_types=bug_types)

    return {
        "sandbox_path": sandbox,
        "injected_bugs": bugs,
        "num_bugs": len(bugs),
        "bug_types": [b.bug_type for b in bugs]
    }
