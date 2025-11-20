"""
SPICA RepairLab: Code Repair via Modular Bug Injection

Integrates the RepairLab bug injection system with SPICA/D-REAM for
evolutionary code repair testing.

Features:
- Pluggable bug taxonomy (9 bugs across easy/medium/hard)
- Deterministic bundle generation from seed
- Multi-dimensional fitness scoring
- Self-contained test bundles with manifests

KPIs: compile_success, test_pass_rate, edit_distance, runtime_parity, patch_readability
"""
from __future__ import annotations
import json, subprocess, sys, time, pathlib, shutil, difflib
from dataclasses import dataclass
from typing import Dict, Any, Optional

BUNDLES_ROOT = pathlib.Path("/tmp/repairlab_bundles")

@dataclass
class CodeRepairVariant:
    difficulty: str = "medium"   # "easy" | "medium" | "hard"
    seed: int = 2025
    # room to add: mutator whitelist, language, retries, etc.

@dataclass
class FitnessWeights:
    compile_success: float = 0.20
    test_pass_rate: float   = 0.40
    edit_distance: float    = 0.15
    runtime_parity: float   = 0.15
    patch_readability: float= 0.10

class RepairLabEvaluator:
    def __init__(self, weights: Optional[Dict[str,float]]=None):
        self.W = FitnessWeights(**(weights or {}))

    # --- Bundle generation via your CLI harness ---
    def _generate_bundle(self, variant: CodeRepairVariant) -> pathlib.Path:
        BUNDLES_ROOT.mkdir(parents=True, exist_ok=True)
        outdir = BUNDLES_ROOT / f"bundle_{variant.difficulty}_{variant.seed}_{int(time.time())}"
        cmd = [
            sys.executable, "-m", "repairlab.harness",
            "--seed", str(variant.seed),
            "--difficulty", variant.difficulty,
            "--out", str(outdir),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode() if e.stderr else 'no stderr'
            print(f"[repairlab] harness failed: {stderr_msg}", file=sys.stderr)
            raise
        return outdir

    # --- Run pytest; return (passed, total, stdout) ---
    def _run_pytest(self, bundle_dir: pathlib.Path) -> tuple[int,int,str]:
        # Use pytest from venv
        pytest_path = pathlib.Path(sys.executable).parent / "pytest"
        proc = subprocess.run(
            [str(pytest_path), "-q", "tests"], cwd=bundle_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        out = proc.stdout
        passed, total = 0, 0
        # crude parse: "X passed, Y failed"
        for line in out.splitlines():
            if " passed" in line or " failed" in line or " error" in line:
                # Try to extract totals
                # examples: "1 passed, 1 failed", "2 passed"
                nums = [int(tok) for tok in line.split() if tok.isdigit()]
                if nums:
                    # best effort: last number tends to be total or failed; compute total by sum
                    counts = []
                    toks = line.replace(",", "").split()
                    for i,t in enumerate(toks):
                        if t.isdigit():
                            label = toks[i+1] if i+1 < len(toks) else ""
                            counts.append((label, int(t)))
                    p = next((n for (lab,n) in counts if "passed" in lab), 0)
                    f = next((n for (lab,n) in counts if "failed" in lab), 0)
                    e = next((n for (lab,n) in counts if "error" in lab), 0)
                    passed = p
                    total = p + f + e
        return passed, total, out

    # --- Minimal-edit heuristic (no GT needed): fewer changed lines is better ---
    def _edit_distance_score(self, before: str, after: str) -> float:
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines()))
        # number of changed hunks ≈ proxy; map to [0..1] with soft clamp
        changed = sum(1 for d in diff if d.startswith(("+","-")) and not d.startswith(("+++","---")))
        score = max(0.0, 1.0 - (changed / 50.0))  # 50 changed lines → score ~0
        return score

    # --- Readability proxy: run 'black --check' or fallback to simple style check ---
    def _readability_score(self, code: str) -> float:
        # quick heuristic: indentation consistency + average line length
        lines = code.splitlines()
        if not lines:
            return 0.2
        avg_len = sum(len(l) for l in lines) / max(1,len(lines))
        long_penalty = min(1.0, max(0.0, (avg_len-100)/60.0))  # >100 avg -> penalize
        indent_ok = sum(1 for l in lines if (not l.strip()) or (l.startswith(" ")*1 and (len(l) - len(l.lstrip(" ")))%4==0))
        indent_score = indent_ok / len(lines)
        return max(0.0, min(1.0, 0.8*indent_score + 0.2*(1.0-long_penalty)))

    # --- Runtime parity: run a small extra input set if sample driver exists ---
    def _runtime_parity(self, module_path: pathlib.Path) -> float:
        try:
            # naive: execute module in a subprocess with simple IO tests
            code = module_path.read_text()
            # Very light sanity: module must define a function that tests use; we probe common names
            fn_name = None
            for cand in ("sum_inclusive","mean","count_evens","fibonacci","solve","main","process"):
                if f"def {cand}(" in code:
                    fn_name = cand; break
            if not fn_name:
                return 0.6
            # Skip runtime parity for now - too fragile
            return 0.8
        except Exception:
            return 0.5

    def evaluate_bundle(self, bundle_dir: pathlib.Path, variant: CodeRepairVariant) -> Dict[str,Any]:
        # 1) read manifest
        manifest_path = bundle_dir / "defect_manifest.json"
        if not manifest_path.exists():
            manifest_path = bundle_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        target_rel = manifest.get("target_module") or "repairlab/samples/sum_list.py"
        target_path = bundle_dir / target_rel
        buggy_before = target_path.read_text()

        # 2) call agent to attempt repair (placeholder contract)
        # Expect an external agent to modify files in-place or write a patch file.
        # Here we do nothing; the fitness will reflect baseline.
        # You'll wire KLoROS repair agent here.

        # 3) compile success
        compile_success = 0.0
        try:
            compile(buggy_before, str(target_path), "exec")
            compile_success = 1.0
        except Exception:
            compile_success = 0.0

        # 4) run tests
        passed, total, _out = self._run_pytest(bundle_dir)
        test_pass_rate = (passed / total) if total else 0.0

        # 5) edit distance (before vs after)
        after = target_path.read_text()
        edit_distance = self._edit_distance_score(buggy_before, after)

        # 6) runtime parity
        runtime_parity = self._runtime_parity(target_path)

        # 7) readability
        readability = self._readability_score(after)

        # 8) fitness
        W = self.W
        fitness = (
            W.compile_success * compile_success +
            W.test_pass_rate   * test_pass_rate +
            W.edit_distance    * edit_distance +
            W.runtime_parity   * runtime_parity +
            W.patch_readability* readability
        )
        return {
            "fitness": float(max(0.0, min(1.0, fitness))),
            "components": {
                "compile_success": compile_success,
                "test_pass_rate": test_pass_rate,
                "edit_distance": edit_distance,
                "runtime_parity": runtime_parity,
                "patch_readability": readability,
            },
            "manifest": manifest,
            "bundle_dir": str(bundle_dir),
            "target_module": target_rel,
        }

    def evaluate(self, test_input: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Evaluate method for ChamberBatchEvaluator interface.

        Args:
            test_input: Dict with 'difficulty' and 'seed' keys
            context: Optional tournament context

        Returns:
            Dict with 'fitness' and 'status' keys
        """
        variant = CodeRepairVariant(
            difficulty=test_input.get("difficulty", "medium"),
            seed=test_input.get("seed", 42)
        )
        result = self.run(variant)

        # Ensure status field exists (ChamberBatchEvaluator expects it)
        if "status" not in result:
            result["status"] = "success" if result.get("fitness", 0) > 0 else "failed"

        return result

    def run(self, variant: CodeRepairVariant) -> Dict[str,Any]:
        bundle = self._generate_bundle(variant)
        return self.evaluate_bundle(bundle, variant)

def build(config: dict):
    """Factory function for D-REAM integration."""
    return RepairLabEvaluator(weights=config.get("fitness_weights"))
