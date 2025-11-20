import os
from ..tools.repo import repo_init, apply_patch
from ..tools.deps import deps_sync
from ..tools.sandbox import run_cmd
from ..tools.git_tools import branch, commit, pr_stub

def run_task(spec: dict):
    path = spec.get("path","./_scratch/work/app")
    template = spec.get("template","python")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = {"init": repo_init(path, template), "steps": []}
    for t in spec.get("tasks", []):
        step = {"task": t.get("name")}
        step["apply_patch"] = apply_patch(path, t.get("patch",""))
        if t.get("manifest"):
            step["deps_sync"] = deps_sync(path, t["manifest"], "install")
        if t.get("test_cmd"):
            r = run_cmd(path, t["test_cmd"], timeout_sec=180, lang=template)
            step["run"] = r
        out["steps"].append(step)
    if "git" in spec:
        g = spec["git"]
        out["git_branch"] = branch(path, g.get("branch","feat-kloros"))
        out["git_commit"] = commit(path, g.get("title","feat: change"))
        out["git_pr"] = pr_stub(path, g.get("title","feat"), g.get("body",""), g.get("target","main"))
    return out
