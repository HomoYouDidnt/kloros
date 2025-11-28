"""
ToolGen Evaluator: Orchestrate synthesis → sandbox → scoring pipeline.

This is the core evaluator that coordinates all components.
"""
from __future__ import annotations
import ast
import hashlib
import json
import pathlib
import time
import importlib.util
from typing import Dict, Any, Tuple, Optional

from src.toolgen.synthesizer import planner, codegen, testgen, docgen
from src.toolgen.sandbox import static_check, permissions, runner

# Phase 3: Pattern library reuse telemetry
LIBROOT = pathlib.Path.home() / "toolgen" / "library" / "patterns"


def _ast_fingerprint(code: str) -> str:
    """Generate AST fingerprint for code."""
    try:
        tree = ast.parse(code)
        dump = ast.dump(tree, annotate_fields=False, include_attributes=False)
        return "ast:" + hashlib.sha256(dump.encode()).hexdigest()
    except Exception:
        return "ast:ERR"


def _reuse_telemetry(bundle_dir: str, spec_path: str) -> Tuple[bool, Optional[str], Optional[str], Optional[Dict]]:
    """
    Detect library pattern reuse and return telemetry.

    Priority:
      1) library_seed.json marker (from codegen seeding)
      2) AST fingerprint match against library

    Args:
        bundle_dir: Path to tool bundle directory
        spec_path: Path to spec JSON file

    Returns:
        Tuple of (reuse_hit, pattern_id, pattern_source, pattern_quality)
        - reuse_hit: True if pattern was reused
        - pattern_id: "{spec_id}:{cluster_id}" if matched
        - pattern_source: "seed" | "match" | None
        - pattern_quality: Quality metrics dict or None
    """
    bundle_path = pathlib.Path(bundle_dir)

    # Priority 1: Check for seed marker
    marker_file = bundle_path / "library_seed.json"
    if marker_file.exists():
        try:
            marker = json.loads(marker_file.read_text())
            return (
                True,
                marker.get("pattern_id"),
                marker.get("source", "seed"),
                marker.get("pattern_quality", {})
            )
        except Exception:
            pass

    # Priority 2: AST fingerprint match
    tool_file = bundle_path / "tool" / "tool.py"
    if not tool_file.exists():
        return False, None, None, None

    try:
        code = tool_file.read_text()
        afp = _ast_fingerprint(code)
    except Exception:
        return False, None, None, None

    spec_id = pathlib.Path(spec_path).stem
    pattern_dir = LIBROOT / spec_id

    if not pattern_dir.exists():
        return False, None, None, None

    # Find best matching cluster
    best_pattern = None
    best_quality = None

    for cluster_path in sorted(pattern_dir.iterdir()):
        manifest_file = cluster_path / "manifest.json"
        if not manifest_file.exists():
            continue

        try:
            manifest = json.loads(manifest_file.read_text())
            fingerprints = set(manifest.get("fingerprints", []))

            if afp in fingerprints:
                quality = manifest.get("quality", {})
                score = (quality.get("median_ms", float('inf')), -quality.get("wins", 0))

                if best_pattern is None or score < best_pattern[0]:
                    pattern_id = f'{manifest["spec_id"]}:{manifest["cluster_id"]}'
                    best_pattern = (score, pattern_id)
                    best_quality = quality
        except Exception:
            continue

    if best_pattern:
        return True, best_pattern[1], "match", best_quality

    return False, None, None, None


def _annealed_budgets(epoch: int) -> tuple[float, float]:
    """
    Calculate annealed time and memory budgets based on epoch.

    Epoch 0→40: time 2000ms→1000ms, mem 128MB→64MB (clamped)

    Args:
        epoch: Current epoch number

    Returns:
        Tuple of (timeout_sec, mem_mb)
    """
    k = min(max(epoch, 0), 40) / 40.0
    timeout_sec = 2.0 - (2.0 - 1.0) * k  # 2.0s → 1.0s
    mem_mb = 128 - (128 - 64) * k  # 128MB → 64MB
    return timeout_sec, int(mem_mb)


def _diversity_bonus(impl_style: str, correctness: float, anneal_temp: float = 1.0) -> float:
    """
    Calculate diversity bonus for alternative implementation styles.

    Rewards correct alternative implementations to encourage exploration.

    Args:
        impl_style: Implementation style (set/trie/lsh/suffixarray)
        correctness: Correctness score [0.0, 1.0]
        anneal_temp: Annealing temperature for bonus scaling

    Returns:
        Diversity bonus [0.0, 0.02]
    """
    if correctness < 0.9:
        return 0.0

    fam_bonus = {
        "set": 0.00,
        "trie": 0.02,
        "lsh": 0.02,
        "suffixarray": 0.02,
    }.get(impl_style, 0.01)

    return min(fam_bonus, 0.02) * min(1.0, anneal_temp)


def _time_call(fn, *args, repeats: int = 50, **kwargs) -> float:
    """
    Time a function call and return median latency in milliseconds.

    Args:
        fn: Callable to time
        args: Positional arguments
        repeats: Number of repetitions for median calculation
        kwargs: Keyword arguments

    Returns:
        Median latency in milliseconds
    """
    latencies = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    return latencies[len(latencies) // 2]  # median ms


def _perf_score(bundle_dir: pathlib.Path, spec: Dict[str, Any], time_budget_ms: int) -> tuple[float, float]:
    """
    Measure actual performance against annealed time budget.

    Args:
        bundle_dir: Path to tool bundle
        spec: Tool specification dict
        time_budget_ms: Annealed time budget in milliseconds

    Returns:
        Tuple of (performance_score, median_latency_ms)
    """
    spec_id = spec.get("id", spec.get("tool_id", ""))
    tool_module_path = bundle_dir / "tool.py"

    if not tool_module_path.exists():
        return 0.0, 0.0

    try:
        # Dynamically load the generated tool module
        spec_obj = importlib.util.spec_from_file_location("tool_mod", tool_module_path)
        if spec_obj is None or spec_obj.loader is None:
            return 0.0, 0.0

        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        # Select function and benchmark input based on spec
        if "text_deduplicate" in spec_id:
            fn = module.deduplicate_lines
            args = ("\n".join(["alpha beta"] * 200), 0.8)
        elif "json_flatten" in spec_id:
            fn = module.flatten_json
            args = ({"a": [{"b": i, "c": [j for j in range(5)]} for i in range(50)]},)
        else:
            # Unknown spec, return neutral score
            return 0.8, 0.0

        # Measure median latency
        median_ms = _time_call(fn, *args, repeats=30)

        # Score: 1.0 if under budget, proportional penalty if over
        score = max(0.0, min(1.0, time_budget_ms / max(1.0, median_ms)))

        return score, median_ms

    except Exception:
        # If benchmarking fails, return neutral score
        return 0.0, 0.0


class ToolGenEvaluator:
    """
    Main evaluator coordinating tool synthesis and evaluation.
    """
    
    def __init__(self, weights: Dict[str, float] | None = None):
        """
        Initialize evaluator with fitness weights.
        
        Args:
            weights: Dict mapping dimension → weight (defaults to equal weights)
        """
        self.weights = weights or {
            "correctness": 0.40,
            "safety": 0.25,
            "performance": 0.15,
            "robustness": 0.10,
            "documentation": 0.10
        }
    
    def evaluate(self, spec_path: pathlib.Path, output_dir: pathlib.Path,
                 epoch: int = 0, impl_style: str = "set", anneal_temp: float = 1.0) -> Dict[str, Any]:
        """
        Full synthesis → test → score pipeline with annealing and diversity.

        Args:
            spec_path: Path to tool specification JSON
            output_dir: Directory to write bundle artifacts
            epoch: Current epoch number for budget annealing
            impl_style: Implementation style (set/trie/lsh/suffixarray)
            anneal_temp: Temperature for diversity bonus scaling

        Returns:
            Dict with keys:
                - fitness: float [0.0, 1.0]
                - components: dict of individual scores
                - bundle_path: str (path to generated bundle)
                - budgets: dict with annealed time/mem budgets
                - impl_style: str
                - epoch: int
        """
        # Calculate annealed budgets
        timeout_sec, mem_mb = _annealed_budgets(epoch)

        # Load spec
        spec = json.loads(spec_path.read_text())
        tool_id = spec.get("tool_id", spec.get("id", "unknown"))

        # 1. Prepare bundle directory
        bundle_dir = output_dir / tool_id
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # 2. Try seeding from pattern library first
        seeded = codegen.seed_from_library(str(bundle_dir), str(spec_path))

        if seeded:
            # Read seeded code for static checks
            code = (bundle_dir / "tool" / "tool.py").read_text()
        else:
            # 3. Synthesize from templates
            plan = planner.plan_tool_implementation(spec)
            code = codegen.generate_code(spec, plan)

            # Add license header to code
            licensed_code = docgen.add_license_header(code)
            (bundle_dir / "tool.py").write_text(licensed_code)

        # 4. Generate tests and docs
        tests = testgen.generate_tests(spec)
        docs = docgen.generate_docs(spec, code)

        # Generate and write SBOM
        sbom = docgen.generate_sbom(spec, str(spec_path), impl_style)
        (bundle_dir / "SBOM.json").write_text(json.dumps(sbom, indent=2))

        # Write other bundle files
        (bundle_dir / "test_tool.py").write_text(tests)
        (bundle_dir / "README.md").write_text(docs)
        (bundle_dir / "spec.json").write_text(json.dumps(spec, indent=2))
        
        # 3. Static checks
        safety_result = static_check.check_code_safety(code, spec)
        perm_result = permissions.validate_permissions(spec, code)
        
        # 4. Run tests in sandbox (twice for flake detection)
        test_result_1 = runner.run_tests_sandboxed(bundle_dir, spec)
        test_result_2 = runner.run_tests_sandboxed(bundle_dir, spec)

        # Calculate stability score (1.0 if consistent, 0.5 if flaky)
        passed_1 = test_result_1["returncode"] == 0
        passed_2 = test_result_2["returncode"] == 0
        stability = 1.0 if passed_1 == passed_2 else 0.5

        # 5. Score dimensions
        correctness = 1.0 if test_result_1["returncode"] == 0 else 0.0
        safety = 1.0 if safety_result["safe"] else 0.0

        # Real performance micro-bench (measure actual latency vs budget)
        performance, median_ms = _perf_score(bundle_dir, spec, int(timeout_sec * 1000))

        robustness = 1.0 if not test_result_1["timeout"] else 0.7
        documentation = 1.0 if len(docs) > 100 else 0.5  # Simplified

        # 6. Calculate diversity bonus
        diversity_bonus = _diversity_bonus(impl_style, correctness, anneal_temp)

        # 7. Aggregate fitness with diversity bonus and stability penalty
        base_fitness = (
            self.weights["correctness"] * correctness +
            self.weights["safety"] * safety +
            self.weights["performance"] * performance +
            self.weights["robustness"] * robustness +
            self.weights["documentation"] * documentation
        )
        fitness = min(1.0, (base_fitness + diversity_bonus) * stability)

        # 8. Cross-domain handoff (ToolGen → RepairLab)
        handoff_path = None
        if correctness < 1.0:
            import os
            qdir = pathlib.Path("/tmp/repairlab_queue")
            qdir.mkdir(exist_ok=True, parents=True)
            handoff = {
                "ts": time.time(),
                "source": "toolgen",
                "spec_path": str(spec_path),
                "bundle_dir": str(bundle_dir),
                "epoch": epoch,
                "impl_style": impl_style,
                "reason": "toolgen_incorrect",
                "metrics": {"correctness": correctness, "fitness": fitness}
            }
            handoff_path = qdir / f"handoff_{int(handoff['ts'])}.json"
            handoff_path.write_text(json.dumps(handoff, indent=2))

        # 8. Detect library pattern reuse
        reuse_hit, pattern_id, pattern_source, pattern_quality = _reuse_telemetry(str(bundle_dir), str(spec_path))

        return {
            "fitness": fitness,
            "components": {
                "correctness": correctness,
                "safety": safety,
                "performance": performance,
                "robustness": robustness,
                "documentation": documentation,
                "diversity_bonus": diversity_bonus,
                "stability": stability
            },
            "budgets": {
                "time_ms": int(timeout_sec * 1000),
                "mem_mb": mem_mb
            },
            "bundle_path": str(bundle_dir),
            "test_output": test_result_1["stdout"],
            "test_output_run2": test_result_2["stdout"],
            "violations": safety_result["violations"],
            "tool_id": tool_id,
            "impl_style": impl_style,
            "epoch": epoch,
            "anneal_temp": anneal_temp,
            "median_ms": median_ms,
            "handoff": str(handoff_path) if handoff_path else None,
            "reuse_hit": bool(reuse_hit),
            "pattern_id": pattern_id,
            "pattern_source": pattern_source,
            "pattern_quality": pattern_quality
        }
