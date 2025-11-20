# src/dream/runner/main.py
import os, json, argparse, pathlib, random
try:
    import tomllib
except ImportError:
    import tomli as tomllib

from src.dream.runtime.workspace import snapshot_create, snapshot_restore, diff_report, enforce_allowlist, check_forbidden_patterns, ARTS
from src.dream.metrics.ledger import log_run
from src.dream.fitness.shaper import shape_constraints
from src.dream.testforge.engine import load_template, instantiate, apply_mutators
from src.dream.schedule.ucb import pick
from src.dream.runner.tools import run_pytest
from src.dream.agent.llm import generate_edit

with open("src/dream/policy/config.toml","rb") as f:
    CFG = tomllib.load(f)
with open("src/dream/policy/capabilities.toml","rb") as f:
    CAP = tomllib.load(f)

def load_candidate(path):
    return json.loads(pathlib.Path(path).read_text())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    args = ap.parse_args()
    cand = load_candidate(args.candidate)

    # 1) choose family/template
    families = CAP["families"]["list"]
    family = pick(families)
    tmpl_paths = CAP["family_templates"][family]
    tmpl = load_template(random.choice(tmpl_paths))

    # 2) instantiate + shape
    fam2, payload, base = instantiate(tmpl)
    assert fam2 == family
    base.setdefault("diff_limit", CFG["scoring"]["max_diff_lines_default"])
    constraints, reason, rate = shape_constraints(family, base)
    constraints = apply_mutators(constraints, family, last_passed=False, tmpl=tmpl)

    # 3) snapshot
    sid = snapshot_create(label=family)

    # 4) LLM agent performs code edit based on payload + constraints
    repo_path = cand["context"]["repo_path"]
    edit_success = generate_edit(repo_path, payload, constraints)
    if not edit_success:
        snapshot_restore(sid)
        log_run({"run_id": sid, "cand_id": cand["cand_id"], "family": family, "passed": False,
                 "metrics":{"edit_applied": False}})
        print("FAIL (no_edit)"); return

    # 5) diff & safety rails
    rep = diff_report(sid)
    changed = [c["file"] for c in rep["changes"]]
    diff_lines = sum(c["diff"].count("\n") for c in rep["changes"])
    all_diffs = "".join(c["diff"] for c in rep["changes"])

    # Safety checks
    allow_ok = enforce_allowlist(changed)
    safe, violations = check_forbidden_patterns(all_diffs)

    if not allow_ok or not safe or diff_lines > constraints["diff_limit"]:
        snapshot_restore(sid)
        metrics = {"allow_ok": allow_ok, "diff_size_lines": diff_lines, "safe": safe}
        if violations:
            metrics["violations"] = violations
        log_run({"run_id": sid, "cand_id": cand["cand_id"], "family": family, "passed": False,
                 "metrics": metrics})
        print(f"FAIL (policy: allow={allow_ok} safe={safe} violations={violations})"); return

    # 6) test
    art_dir = ARTS / sid; art_dir.mkdir(parents=True, exist_ok=True)
    res = run_pytest(cand["context"]["test_cmd"], cand["context"]["repo_path"], str(art_dir))

    # 7) score + rollback
    passed = res["ok"]
    if not passed: snapshot_restore(sid)
    log_run({"run_id": sid, "cand_id": cand["cand_id"], "family": family, "passed": passed,
             "metrics":{"tests_green": res["ok"], "diff_size_lines": diff_lines,
                        "changed_files": len(changed)}})
    print("PASS" if passed else "FAIL")

if __name__ == "__main__":
    main()
