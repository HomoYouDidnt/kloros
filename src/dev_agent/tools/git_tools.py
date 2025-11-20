import subprocess, shlex, pathlib
from src.tools.tracker import track_tool

def _run(cmd, cwd):
    p = subprocess.run(shlex.split(cmd), cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout[-4000:], p.stderr[-4000:]

@track_tool()
def ensure_repo(path: str):
    p = pathlib.Path(path).resolve()
    if not (p/".git").exists():
        _run("git init", p)
        _run('git config user.email "kloros@example.local"', p)
        _run('git config user.name "KLoROS"', p)
    return {"ok": True}

@track_tool()
def branch(path: str, name: str):
    ensure_repo(path)
    code, out, err = _run(f"git checkout -B {name}", path)
    return {"ok": code==0, "stdout": out, "stderr": err}

@track_tool()
def commit(path: str, message: str):
    ensure_repo(path)
    _run("git add -A", path)
    code, out, err = _run(f'git commit -m "{message.replace(chr(34),"\"")}"', path)
    return {"ok": code==0, "stdout": out, "stderr": err}

@track_tool()
def pr_stub(path: str, title: str, body_md: str, target: str="main"):
    return {"ok": True, "title": title, "target": target, "body": body_md[:2000]}
