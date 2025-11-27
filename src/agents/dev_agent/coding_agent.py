"""
Coding Agent: Surgical code repair and synthesis.

Agent loop:
1. Plan (what to change; list target files/symbols)
2. Edit (small diffs only; no file sprawl)
3. Validate (tests + linters)
4. Diagnose (if red: root cause → next patch)
5. Summarize (why it worked; what changed)
"""
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.agents.dev_agent.tools.repo_indexer import RepoIndex, ContextPacker
from src.agents.dev_agent.tools.patcher import (
    apply_patch_with_validation,
    validate_diff_syntax,
    compute_diff_stats
)
from src.agents.dev_agent.tools.validate import (
    run_validation,
    run_tests_only,
    extract_test_failures,
    ValidationResult
)
from src.agents.dev_agent.tools.metrics import MetricsTracker, TaskMetrics

@dataclass
class PlanStep:
    """A single step in the execution plan."""
    description: str
    target_files: List[str]
    target_symbols: List[str]

@dataclass
class EditResult:
    """Result of an edit attempt."""
    success: bool
    diff: str
    files_changed: int
    validation_passed: bool
    error_message: Optional[str] = None

class CodingAgent:
    """
    KLoROS coding agent for surgical code repair and synthesis.

    Capabilities:
    - Bug fixing from failing tests (≥90% fix@3)
    - Feature implementation from specs
    - Refactoring with invariant preservation
    - Test generation
    """

    def __init__(
        self,
        repo_root: Path,
        llm_callable: callable,
        metrics_dir: Optional[Path] = None
    ):
        """
        Initialize coding agent.

        Args:
            repo_root: Repository root directory
            llm_callable: Function to call LLM (takes prompt, returns response)
            metrics_dir: Directory for metrics storage
        """
        self.repo_root = Path(repo_root).resolve()
        self.llm = llm_callable

        # Initialize metrics tracker
        if metrics_dir is None:
            metrics_dir = self.repo_root / ".kloros" / "coding_metrics"
        self.metrics = MetricsTracker(metrics_dir)

        # Build or load repo index
        index_file = self.repo_root / ".kloros" / "repo_index.json"
        if index_file.exists():
            self.index = RepoIndex.load(index_file)
        else:
            self.index = RepoIndex(self.repo_root)
            self.index.build()
            index_file.parent.mkdir(parents=True, exist_ok=True)
            self.index.save(index_file)

        self.context_packer = ContextPacker(self.index)

    def fix_bug_from_tests(
        self,
        failing_test_output: str,
        max_attempts: int = 3
    ) -> Tuple[bool, List[EditResult]]:
        """
        Fix bug from failing test output.

        Args:
            failing_test_output: Pytest output showing failures
            max_attempts: Maximum fix attempts

        Returns:
            (success, edit_results)
        """
        task_id = f"bug_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = time.time()

        # Extract failing tests
        failures = extract_test_failures(failing_test_output)

        if not failures:
            return (False, [])

        attempts = []

        for attempt in range(1, max_attempts + 1):
            print(f"\n=== Attempt {attempt}/{max_attempts} ===")

            # Step 1: Plan
            plan = self._plan_bug_fix(failures, failing_test_output)

            # Step 2: Edit
            diff = self._generate_fix_diff(plan, failures, failing_test_output)

            if not diff:
                attempts.append(EditResult(
                    success=False,
                    diff="",
                    files_changed=0,
                    validation_passed=False,
                    error_message="Failed to generate diff"
                ))
                continue

            # Step 3: Validate diff syntax
            is_valid, error = validate_diff_syntax(diff)
            if not is_valid:
                attempts.append(EditResult(
                    success=False,
                    diff=diff,
                    files_changed=0,
                    validation_passed=False,
                    error_message=f"Invalid diff syntax: {error}"
                ))
                continue

            # Compute diff stats
            stats = compute_diff_stats(diff)

            # Step 4: Apply patch with validation
            def validate_fn():
                results = run_validation(self.repo_root)
                return all(r.passed for r in results)

            try:
                patch_result = apply_patch_with_validation(
                    self.repo_root,
                    diff,
                    validate_fn=validate_fn,
                    auto_rollback=True
                )

                edit_result = EditResult(
                    success=patch_result["success"] and patch_result.get("validation_passed", False),
                    diff=diff,
                    files_changed=patch_result["files_changed"],
                    validation_passed=patch_result.get("validation_passed", False)
                )

                attempts.append(edit_result)

                if edit_result.success:
                    # Record successful fix
                    duration = (time.time() - start_time) * 1000

                    task_metric = TaskMetrics(
                        task_id=task_id,
                        task_type="bug_fix",
                        timestamp=datetime.now().isoformat(),
                        duration_ms=duration,
                        attempts=attempt,
                        success=True,
                        diff_size=stats["total_changes"],
                        files_changed=stats["files_touched"],
                        insertions=stats["insertions"],
                        deletions=stats["deletions"],
                        tests_passed=True,
                        linter_passed=True,
                        type_check_passed=True,
                        security_passed=True
                    )

                    self.metrics.record_task(task_metric)

                    return (True, attempts)

            except Exception as e:
                attempts.append(EditResult(
                    success=False,
                    diff=diff,
                    files_changed=stats["files_touched"],
                    validation_passed=False,
                    error_message=str(e)
                ))

        # All attempts failed
        duration = (time.time() - start_time) * 1000

        task_metric = TaskMetrics(
            task_id=task_id,
            task_type="bug_fix",
            timestamp=datetime.now().isoformat(),
            duration_ms=duration,
            attempts=max_attempts,
            success=False,
            diff_size=0,
            files_changed=0,
            insertions=0,
            deletions=0,
            tests_passed=False,
            linter_passed=False,
            type_check_passed=False,
            security_passed=False
        )

        self.metrics.record_task(task_metric)

        return (False, attempts)

    def _plan_bug_fix(
        self,
        failures: List[Dict[str, str]],
        test_output: str
    ) -> PlanStep:
        """Generate plan for bug fix."""
        # Extract relevant context
        test_files = list(set(f["file"] for f in failures))

        # Pack context
        context = self.context_packer.pack_context(
            task_description=" ".join(f["reason"] for f in failures),
            failing_tests=[f["test_name"] for f in failures]
        )

        # Build prompt
        prompt = self._build_bug_fix_prompt(failures, test_output, context)

        # Call LLM to get plan
        response = self.llm(prompt)

        # Parse plan (simplified - real version would parse structured output)
        # For now, return a simple plan
        return PlanStep(
            description="Fix failing tests",
            target_files=test_files,
            target_symbols=[]
        )

    def _generate_fix_diff(
        self,
        plan: PlanStep,
        failures: List[Dict[str, str]],
        test_output: str
    ) -> Optional[str]:
        """Generate unified diff for the fix."""
        # Pack context
        context = self.context_packer.pack_context(
            task_description=" ".join(f["reason"] for f in failures),
            failing_tests=[f["test_name"] for f in failures]
        )

        # Build prompt
        prompt = self._build_fix_diff_prompt(plan, failures, test_output, context)

        # Call LLM to generate diff
        response = self.llm(prompt)

        # Extract diff from response (look for ```diff ... ``` block)
        import re
        diff_match = re.search(r'```diff\n(.*?)\n```', response, re.DOTALL)

        if diff_match:
            return diff_match.group(1)

        return None

    def _build_bug_fix_prompt(
        self,
        failures: List[Dict[str, str]],
        test_output: str,
        context: Dict[str, str]
    ) -> str:
        """Build prompt for bug fix planning."""
        context_str = "\n\n".join(
            f"# {file}\n```python\n{content}\n```"
            for file, content in context.items()
        )

        failures_str = "\n".join(
            f"- {f['test_name']} in {f['file']}: {f['reason']}"
            for f in failures
        )

        return f"""You are KLoROS, a surgical code repair agent.

GOAL: Make the tests pass by the smallest correct change.

FAILING TESTS:
{failures_str}

TEST OUTPUT:
```
{test_output[-2000:]}
```

RELEVANT CODE:
{context_str}

CONSTRAINTS:
- Do NOT create new files unless explicitly required by the error.
- Keep diffs minimal; prefer local fixes.
- If a public API changes, update its callers and tests in the same patch.

PLAN (1-3 bullets):
1. Root cause hypothesis (reference line numbers)
2. Proposed minimal fix
3. Expected post-patch behavior
"""

    def _build_fix_diff_prompt(
        self,
        plan: PlanStep,
        failures: List[Dict[str, str]],
        test_output: str,
        context: Dict[str, str]
    ) -> str:
        """Build prompt for generating fix diff."""
        context_str = "\n\n".join(
            f"# {file}\n```python\n{content}\n```"
            for file, content in context.items()
        )

        return f"""You are KLoROS, a surgical code repair agent.

PLAN: {plan.description}

CONTEXT:
{context_str}

TASK: Generate a minimal unified diff to fix the failing tests.

CONSTRAINTS:
- Output ONLY the diff in ```diff ... ``` format
- Keep changes minimal (prefer ≤20 lines changed)
- Preserve existing code structure
- Include file headers (--- a/file.py, +++ b/file.py)

OUTPUT FORMAT:
```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -line,count +line,count @@
 context line
-removed line
+added line
 context line
```
"""

    def rebuild_index(self):
        """Rebuild the repository index."""
        self.index = RepoIndex(self.repo_root)
        self.index.build()

        index_file = self.repo_root / ".kloros" / "repo_index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        self.index.save(index_file)

        self.context_packer = ContextPacker(self.index)

    def get_metrics_summary(self) -> Dict:
        """Get current metrics summary."""
        run_metrics = self.metrics.compute_run_metrics()

        return {
            "pass_at_1": run_metrics.pass_at_1,
            "pass_at_3": run_metrics.pass_at_3,
            "repair_at_3": run_metrics.repair_at_3,
            "mean_diff_size": run_metrics.mean_diff_size,
            "revert_rate": run_metrics.revert_rate,
            "tasks_total": run_metrics.tasks_total,
            "tasks_succeeded": run_metrics.tasks_succeeded
        }
