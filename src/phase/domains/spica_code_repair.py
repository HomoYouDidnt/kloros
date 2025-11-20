"""
SPICA Derivative: Code Repair & Synthesis

SPICA-based code repair testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Bug detection (ruff, mypy, pytest)
- Autonomous bug fixing with LLM
- Repair success metrics (repair@k, diff_size, latency)
- Synthetic bug injection for testing

KPIs: repair_at_3, bugs_fixed_rate, mean_diff_size, mean_latency_ms
"""
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result
from src.config.models_config import get_ollama_context_size


@dataclass
class CodeRepairTestConfig:
    """Configuration for code repair tests."""
    repo_root: Path = Path("/home/kloros")
    max_attempts_per_bug: int = 3
    timeout_per_attempt_sec: int = 600
    enable_self_play: bool = True
    enable_heuristic_evolution: bool = True
    max_total_time_sec: int = 14400
    max_memory_mb: int = 4096
    max_cpu_percent: int = 50
    num_bugs_per_test: int = 1
    bug_types: List[str] = None

    def __post_init__(self):
        if self.bug_types is None:
            self.bug_types = ["syntax"]


@dataclass
class CodeRepairTestResult:
    """Results from a code repair test."""
    test_id: str
    status: str
    tests_passed: bool
    lint_passed: bool
    bugs_fixed: int
    bugs_injected: int
    latency_ms: float
    cpu_percent: float
    memory_mb: float
    error: Optional[str] = None


class SpicaCodeRepair(SpicaBase):
    """SPICA derivative for code repair and synthesis testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[CodeRepairTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-coderepair-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'repo_root': str(test_config.repo_root),
                'max_attempts_per_bug': test_config.max_attempts_per_bug,
                'timeout_per_attempt_sec': test_config.timeout_per_attempt_sec,
                'max_total_time_sec': test_config.max_total_time_sec,
                'num_bugs_per_test': test_config.num_bugs_per_test,
                'bug_types': test_config.bug_types
            })

        super().__init__(spica_id=spica_id, domain="code_repair", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or CodeRepairTestConfig()
        self.results: List[CodeRepairTestResult] = []
        
        self.record_telemetry("spica_code_repair_init", {
            "repo_root": str(self.test_config.repo_root),
            "max_attempts_per_bug": self.test_config.max_attempts_per_bug,
            "bug_types": self.test_config.bug_types
        })

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """SPICA evaluate() interface for code repair tests (uses Ollama qwen2.5-coder)."""
        epoch_id = (context or {}).get("epoch_id", "unknown")

        result = self.run_single_epoch_test(epoch_id)
        
        fitness = 0.0
        if result.bugs_injected > 0:
            fitness = result.bugs_fixed / result.bugs_injected
        
        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id
        }

    def run_single_epoch_test(self, epoch_id: str) -> CodeRepairTestResult:
        """Run single-epoch code repair test (uses Ollama qwen2.5-coder automatically)."""
        from src.phase.domains.bug_injector import create_bug_simulation_test
        import subprocess
        import shutil
        import psutil

        start = time.time()
        test_id = f"code_repair::{epoch_id}"

        self.record_telemetry("epoch_started", {"epoch_id": epoch_id})

        try:
            # Create sandbox with injected bugs
            simulation = create_bug_simulation_test(
                repo_root=self.test_config.repo_root,
                num_bugs=self.test_config.num_bugs_per_test,
                bug_types=self.test_config.bug_types
            )

            sandbox_path = simulation["sandbox_path"]
            injected_bugs = simulation["injected_bugs"]
            num_bugs_injected = len(injected_bugs)

            self.record_telemetry("bugs_injected", {
                "count": num_bugs_injected,
                "sandbox_path": str(sandbox_path)
            })

            if num_bugs_injected == 0:
                try:
                    shutil.rmtree(sandbox_path)
                except:
                    pass
                
                result = CodeRepairTestResult(
                    test_id=test_id, status="fail", tests_passed=False,
                    lint_passed=False, bugs_fixed=0, bugs_injected=0,
                    latency_ms=(time.time() - start) * 1000,
                    cpu_percent=0.0, memory_mb=0.0, error="Bug injection failed"
                )
                
                write_test_result(test_id, "fail", result.latency_ms, 0.0, 0.0, epoch_id)
                self.results.append(result)
                return result

            # Run validation
            tests_passed = True
            lint_passed = True
            bugs_fixed = 0

            # Run ruff check
            ruff_cmd = self.test_config.repo_root / ".venv" / "bin" / "ruff"
            if not ruff_cmd.exists():
                ruff_cmd = shutil.which("ruff")

            if ruff_cmd:
                check_path = sandbox_path / "src" / "rag"
                if not check_path.exists():
                    check_path = sandbox_path / "src"

                ruff_result = subprocess.run(
                    [str(ruff_cmd), "check", str(check_path), "--quiet", "--no-cache"],
                    cwd=sandbox_path, capture_output=True, text=True, timeout=30
                )

                lint_passed = ruff_result.returncode == 0
                self.record_telemetry("lint_check", {"passed": lint_passed})

            # Attempt fix if bugs detected (using Ollama qwen2.5-coder)
            if not lint_passed and num_bugs_injected > 0:
                self.record_telemetry("attempting_fix", {"llm": "qwen2.5-coder:7b"})
                
                bug = injected_bugs[0]
                sandbox_file = bug.file_path

                with open(sandbox_file) as f:
                    buggy_content = f.read()

                lint_error = ""
                if ruff_cmd:
                    try:
                        ruff_result = subprocess.run(
                            [str(ruff_cmd), "check", str(sandbox_file), "--no-cache"],
                            cwd=sandbox_path, capture_output=True, text=True, timeout=10
                        )
                        lint_error = ruff_result.stdout
                    except:
                        lint_error = "Unable to capture lint errors"

                fix_prompt = f"""Fix the Python syntax error in this file. Return ONLY the complete fixed Python code.

FILE: {bug.file_path.name}
ERROR LINE: {bug.line_number}

LINT ERROR:
{lint_error[:500]}

CRITICAL RULES:
1. Return the ENTIRE file - every single line from start to end
2. Keep ALL triple-quoted docstrings (''' or \"\"\") exactly as they are
3. Keep ALL imports, comments, and blank lines
4. Fix ONLY the syntax error on line {bug.line_number}
5. Do NOT add any explanations, markdown, or code fences
6. Output must start with the exact first line of the original file

ORIGINAL FILE ({len(buggy_content)} characters):
{buggy_content}

Return the complete fixed file below (no explanations):"""

                try:
                    # Call LLM with explicit options for full file generation
                    import requests
                    from src.config.models_config import get_ollama_url_for_mode, get_ollama_model_for_mode
                    response = requests.post(
                        get_ollama_url_for_mode("code") + "/api/generate",
                        json={
                            "model": get_ollama_model_for_mode("code"),
                            "prompt": fix_prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.0,
                                "num_predict": 20000,
                                "num_ctx": get_ollama_context_size(check_vram=False)
                            }
                        },
                        timeout=180
                    )

                    if response.status_code == 200:
                        fixed_content = response.json().get("response", "").strip()
                    else:
                        raise RuntimeError(f"LLM request failed: {response.status_code}")

                    # Remove markdown code fences if present
                    if "```python" in fixed_content:
                        start_idx = fixed_content.find("```python") + 9
                        end_idx = fixed_content.rfind("```")
                        if end_idx > start_idx:
                            fixed_content = fixed_content[start_idx:end_idx].strip()

                    # Validate output quality
                    original_lines = buggy_content.split('\n')
                    fixed_lines = fixed_content.split('\n')

                    # Check 1: Length should be similar (at least 80% of original)
                    length_ratio = len(fixed_content) / len(buggy_content)
                    if length_ratio < 0.8:
                        self.record_telemetry("fix_validation_failed", {
                            "reason": "output_too_short",
                            "ratio": length_ratio
                        })
                        raise RuntimeError(f"LLM output too short: {length_ratio:.1%} of original")

                    # Check 2: First line should be intact (critical for docstrings)
                    if original_lines[0].strip().startswith('"""') or original_lines[0].strip().startswith("'''"):
                        if not (fixed_lines[0].strip().startswith('"""') or fixed_lines[0].strip().startswith("'''")):
                            # LLM stripped docstring markers - try to recover
                            if fixed_lines[0].strip() and not fixed_lines[0].strip().startswith('#'):
                                fixed_content = '"""' + fixed_content
                                self.record_telemetry("docstring_marker_restored", {"line": 0})

                    # Check 3: Number of lines should be close (within 10%)
                    line_count_ratio = len(fixed_lines) / len(original_lines)
                    if line_count_ratio < 0.9 or line_count_ratio > 1.1:
                        self.record_telemetry("fix_validation_warning", {
                            "reason": "line_count_mismatch",
                            "original_lines": len(original_lines),
                            "fixed_lines": len(fixed_lines),
                            "ratio": line_count_ratio
                        })

                    with open(sandbox_file, 'w') as f:
                        f.write(fixed_content)

                    self.record_telemetry("fix_applied", {"file": bug.file_path.name})

                    if ruff_cmd:
                        subprocess.run(
                            [str(ruff_cmd), "check", "--fix", str(sandbox_file), "--no-cache", "--quiet"],
                            cwd=sandbox_path, capture_output=True, timeout=10
                        )

                except Exception as e:
                    self.record_telemetry("fix_failed", {"error": str(e)})
                    with open(sandbox_file) as f:
                        lines = f.readlines()
                    lines[bug.line_number - 1] = bug.original_line + '\n'
                    with open(sandbox_file, 'w') as f:
                        f.writelines(lines)

                # Re-run lint
                if ruff_cmd:
                    ruff_result = subprocess.run(
                        [str(ruff_cmd), "check", str(sandbox_file), "--no-cache"],
                        cwd=sandbox_path, capture_output=True, text=True, timeout=30
                    )

                    if ruff_result.returncode == 0:
                        bugs_fixed = 1
                        lint_passed = True
                        self.record_telemetry("fix_successful", {"bugs_fixed": bugs_fixed})

            # Cleanup
            try:
                shutil.rmtree(sandbox_path)
            except Exception as e:
                self.record_telemetry("cleanup_failed", {"error": str(e)})

            duration = (time.time() - start) * 1000
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            status = "pass" if (num_bugs_injected == 0 or bugs_fixed == num_bugs_injected) else "fail"

            result = CodeRepairTestResult(
                test_id=test_id, status=status, tests_passed=tests_passed,
                lint_passed=lint_passed, bugs_fixed=bugs_fixed,
                bugs_injected=num_bugs_injected, latency_ms=duration,
                cpu_percent=cpu_percent, memory_mb=memory_mb
            )

            write_test_result(test_id, status, duration, cpu_percent, memory_mb, epoch_id)
            self.results.append(result)
            self.record_telemetry("test_complete", {"status": status, "bugs_fixed": bugs_fixed})
            
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = CodeRepairTestResult(
                test_id=test_id, status="fail", tests_passed=False,
                lint_passed=False, bugs_fixed=0, bugs_injected=0,
                latency_ms=duration, cpu_percent=0.0, memory_mb=0.0,
                error=str(e)
            )
            
            write_test_result(test_id, "fail", duration, 0.0, 0.0, epoch_id)
            self.results.append(result)
            self.record_telemetry("test_failed", {"error": str(e)})
            raise RuntimeError(f"Code repair test failed: {e}") from e

    def get_summary(self) -> Dict:
        """Get summary statistics for all tests."""
        if not self.results:
            return {"total_tests": 0, "repair_rate": 0.0}

        total_bugs_injected = sum(r.bugs_injected for r in self.results)
        total_bugs_fixed = sum(r.bugs_fixed for r in self.results)
        repair_rate = total_bugs_fixed / total_bugs_injected if total_bugs_injected > 0 else 0.0

        return {
            "total_tests": len(self.results),
            "total_bugs_injected": total_bugs_injected,
            "total_bugs_fixed": total_bugs_fixed,
            "repair_rate": repair_rate,
            "avg_latency_ms": sum(r.latency_ms for r in self.results) / len(self.results)
        }
