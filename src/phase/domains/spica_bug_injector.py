"""
SPICA Derivative: Bug Injection System

SPICA-based bug injection for code repair testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Realistic, fixable bug injection (syntax, logic, name errors)
- Sandbox creation for isolated testing
- Deterministic bug generation for reproducibility

KPIs: injection_success_rate, bugs_per_file, sandbox_creation_latency
"""
import ast
import random
import tempfile
import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase


@dataclass
class BugInjectionConfig:
    """Configuration for bug injection."""
    repo_root: Path = Path("/home/kloros")
    max_files: int = 5
    seed: int = 42
    bug_types: List[str] = None

    def __post_init__(self):
        if self.bug_types is None:
            self.bug_types = ["syntax", "logic", "name"]


@dataclass
class InjectedBug:
    """Represents a bug injected into code."""
    bug_type: str
    file_path: Path
    line_number: int
    original_line: str
    buggy_line: str
    description: str
    difficulty: str


class SpicaBugInjector(SpicaBase):
    """SPICA derivative for bug injection and sandbox creation."""

    # Bug templates by type
    @staticmethod
    def _remove_colon(line: str) -> Optional[str]:
        if line.rstrip().endswith(':'):
            return line.rstrip().rstrip(':') + '\n'
        return None

    @staticmethod
    def _missing_paren(line: str) -> Optional[str]:
        if '(' in line and ')' in line:
            idx = line.rfind(')')
            if line.endswith('\n'):
                return line[:idx] + line[idx+1:-1] + '\n'
            return line[:idx] + line[idx+1:]
        return None

    @staticmethod
    def _missing_quote(line: str) -> Optional[str]:
        if line.count('"') >= 2:
            result = line.replace('"', '', 1)
            if line.endswith('\n') and not result.endswith('\n'):
                result += '\n'
            return result
        return None

    @staticmethod
    def _off_by_one(line: str) -> Optional[str]:
        if 'range(' in line and 'range(1,' not in line:
            return line.replace('range(', 'range(1, ', 1)
        return None

    @staticmethod
    def _wrong_operator(line: str) -> Optional[str]:
        if '==' in line:
            return line.replace('==', '!=', 1)
        return None

    @staticmethod
    def _typo_variable(line: str) -> Optional[str]:
        if 'result' in line and 'result' not in ['@', '#']:
            return line.replace('result', 'resutl', 1)
        return None

    SYNTAX_BUGS = [
        ("remove_colon", _remove_colon.__func__),
        ("missing_paren", _missing_paren.__func__),
        ("missing_quote", _missing_quote.__func__),
    ]

    LOGIC_BUGS = [
        ("off_by_one", _off_by_one.__func__),
        ("wrong_operator", _wrong_operator.__func__),
    ]

    NAME_BUGS = [
        ("typo_variable", _typo_variable.__func__),
    ]

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 injection_config: Optional[BugInjectionConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-buginjector-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if injection_config:
            base_config.update({
                'repo_root': str(injection_config.repo_root),
                'max_files': injection_config.max_files,
                'seed': injection_config.seed,
                'bug_types': injection_config.bug_types
            })

        super().__init__(spica_id=spica_id, domain="bug_injector", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.injection_config = injection_config or BugInjectionConfig()
        self.random = random.Random(self.injection_config.seed)
        self.injected_bugs: List[InjectedBug] = []
        
        self.record_telemetry("spica_bug_injector_init", {
            "repo_root": str(self.injection_config.repo_root),
            "seed": self.injection_config.seed,
            "bug_types": self.injection_config.bug_types
        })

    def get_injectable_files(self, max_files: int = 5) -> List[Path]:
        """Find Python files suitable for bug injection."""
        python_files = []
        src_dir = self.injection_config.repo_root / "src"

        if not src_dir.exists():
            self.record_telemetry("no_src_dir", {"path": str(src_dir)})
            return []

        for py_file in src_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            if "test_" in py_file.name or "_test.py" in py_file.name:
                continue
            if ".venv" in str(py_file) or "node_modules" in str(py_file):
                continue
            python_files.append(py_file)

        sampled = self.random.sample(python_files, min(len(python_files), max_files))
        self.record_telemetry("files_selected", {"count": len(sampled)})
        return sampled

    def inject_bug(self, file_path: Path, bug_type: str = "auto") -> Optional[InjectedBug]:
        """Inject a single bug into a file."""
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except Exception as e:
            self.record_telemetry("file_read_failed", {"file": str(file_path), "error": str(e)})
            return None

        if len(lines) < 5:
            return None

        if bug_type == "auto":
            bug_type = self.random.choice(["syntax", "logic", "name"])

        if bug_type == "syntax":
            templates = self.SYNTAX_BUGS
        elif bug_type == "logic":
            templates = self.LOGIC_BUGS
        elif bug_type == "name":
            templates = self.NAME_BUGS
        else:
            return None

        for _ in range(20):
            min_line = min(2, len(lines) - 3)
            max_line = max(min_line + 1, len(lines) - 2)

            if min_line >= max_line:
                return None

            line_idx = self.random.randint(min_line, max_line)
            original_line = lines[line_idx]

            if not original_line.strip() or original_line.strip().startswith('#'):
                continue

            for bug_name, bug_func in templates:
                buggy_line = bug_func(original_line)

                if buggy_line is not None and buggy_line != original_line:
                    lines[line_idx] = buggy_line

                    try:
                        with open(file_path, 'w') as f:
                            f.writelines(lines)
                    except Exception as e:
                        self.record_telemetry("file_write_failed", {"file": str(file_path), "error": str(e)})
                        return None

                    bug = InjectedBug(
                        bug_type=bug_type,
                        file_path=file_path,
                        line_number=line_idx + 1,
                        original_line=original_line.rstrip(),
                        buggy_line=buggy_line.rstrip(),
                        description=f"{bug_name}: {original_line.strip()} → {buggy_line.strip()}",
                        difficulty="easy" if bug_type == "syntax" else "medium"
                    )

                    self.record_telemetry("bug_injected", {
                        "bug_type": bug_type,
                        "file": file_path.name,
                        "line": line_idx + 1
                    })

                    return bug

        return None

    def create_sandbox(self, target_dir: Optional[Path] = None) -> Path:
        """Create a sandbox copy of the repository."""
        if target_dir is None:
            target_dir = Path(tempfile.mkdtemp(prefix="kloros_sandbox_"))

        src_dir = self.injection_config.repo_root / "src"
        if src_dir.exists():
            def ignore_permission_errors(src, names):
                ignored = []
                for name in names:
                    path = Path(src) / name
                    try:
                        path.stat()
                    except PermissionError:
                        ignored.append(name)
                return ignored

            try:
                shutil.copytree(src_dir, target_dir / "src", dirs_exist_ok=True, ignore=ignore_permission_errors)
            except shutil.Error:
                pass

        pyproject = self.injection_config.repo_root / "pyproject.toml"
        if pyproject.exists():
            try:
                shutil.copy(pyproject, target_dir / "pyproject.toml")
            except PermissionError:
                pass

        self.record_telemetry("sandbox_created", {"path": str(target_dir)})
        return target_dir

    def inject_sandbox_bugs(
        self,
        num_bugs: int = 3,
        bug_types: Optional[List[str]] = None
    ) -> Tuple[Path, List[InjectedBug]]:
        """Create sandbox and inject multiple bugs."""
        sandbox = self.create_sandbox()

        injectable_files = self.get_injectable_files(max_files=num_bugs)

        if not injectable_files:
            self.record_telemetry("no_injectable_files", {})
            return sandbox, []

        injected_bugs = []
        for file_path in injectable_files[:num_bugs]:
            relative_path = file_path.relative_to(self.injection_config.repo_root)
            sandbox_file = sandbox / relative_path

            if not sandbox_file.exists():
                continue

            bug_type = bug_types[len(injected_bugs)] if bug_types else "auto"
            bug = self.inject_bug(sandbox_file, bug_type=bug_type)

            if bug:
                injected_bugs.append(bug)

        self.injected_bugs = injected_bugs
        self.record_telemetry("bugs_injected_complete", {
            "sandbox": str(sandbox),
            "bugs_count": len(injected_bugs)
        })

        return sandbox, injected_bugs

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """SPICA evaluate() interface for bug injection."""
        num_bugs = test_input.get("num_bugs", 1)
        bug_types = test_input.get("bug_types")
        
        sandbox, bugs = self.inject_sandbox_bugs(num_bugs=num_bugs, bug_types=bug_types)
        
        fitness = len(bugs) / num_bugs if num_bugs > 0 else 0.0
        
        return {
            "fitness": fitness,
            "test_id": f"bug_injector::{self.spica_id}",
            "status": "pass" if len(bugs) > 0 else "fail",
            "metrics": {
                "sandbox_path": str(sandbox),
                "bugs_injected": len(bugs),
                "bugs_requested": num_bugs
            },
            "spica_id": self.spica_id
        }

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        return {
            "total_bugs_injected": len(self.injected_bugs),
            "bug_types": [b.bug_type for b in self.injected_bugs]
        }
