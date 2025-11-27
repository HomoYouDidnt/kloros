import os, subprocess, shlex, pathlib
from src.tools.tracker import track_tool

@track_tool()
def deps_sync(path: str, manifest: str, strategy: str = "install"):
    p = pathlib.Path(path).resolve()
    if manifest == "pip":
        cmd = "python -m pip install -r requirements.txt" if (p/'requirements.txt').exists() else "python -m pip install ."
    elif manifest == "uv":
        cmd = "uv pip install -r requirements.txt"
    elif manifest == "npm":
        cmd = "npm install"
    elif manifest == "pnpm":
        cmd = "pnpm install"
    else:
        raise RuntimeError("Unknown manifest")
    proc = subprocess.run(shlex.split(cmd), cwd=str(p), capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
