from fastapi import FastAPI, Body
from pydantic import BaseModel
from .controller.dev_loop import run_task
from .tools.repo import repo_init, apply_patch
from .tools.deps import deps_sync
from .tools.sandbox import run_cmd
from .tools.git_tools import branch, commit, pr_stub

app = FastAPI(title="KLoROS Dev-Agent Tools", version="0.1.0")

class PatchReq(BaseModel):
    path: str
    patch_unified: str

@app.post("/repo.init")
def api_repo_init(path: str, template: str = "python"):
    return repo_init(path, template)

@app.post("/repo.apply_patch")
def api_apply_patch(req: PatchReq):
    return apply_patch(req.path, req.patch_unified)

@app.post("/deps.sync")
def api_deps_sync(path: str, manifest: str, strategy: str = "install"):
    return deps_sync(path, manifest, strategy)

@app.post("/code_sandbox.run")
def api_run(path: str, cmd: str, timeout_sec: int = 120, lang: str = "python"):
    return run_cmd(path, cmd, timeout_sec, lang)

@app.post("/git.branch")
def api_branch(path: str, name: str):
    return branch(path, name)

@app.post("/git.commit")
def api_commit(path: str, message: str):
    return commit(path, message)

@app.post("/git.pr")
def api_pr(path: str, title: str, body_md: str, target: str = "main"):
    return pr_stub(path, title, body_md, target)

@app.post("/dev_loop.run_task")
def api_dev_loop(spec: dict = Body(...)):
    return run_task(spec)
