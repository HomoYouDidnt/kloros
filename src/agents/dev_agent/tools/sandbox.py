import os, subprocess, shlex, yaml, pathlib
from src.tools.tracker import track_tool

def load_policy(path="security/policy.yaml"):
    # Try to load from src/dev_agent/security first, then fall back to relative path
    script_dir = pathlib.Path(__file__).resolve().parent.parent
    policy_path = script_dir / "security" / "policy.yaml"
    if not policy_path.exists():
        policy_path = pathlib.Path(path)
    with open(policy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _engine():
    import shutil
    if shutil.which("docker"): return "docker"
    if shutil.which("podman"): return "podman"
    return "local"

@track_tool()
def run_cmd(path: str, cmd: str, timeout_sec: int | None = None, lang: str = "python"):
    pol = load_policy()
    engine = pol.get("sandbox",{}).get("engine") or _engine()
    work_root = pathlib.Path(pol["sandbox"]["work_dir"]).resolve()
    os.makedirs(work_root, exist_ok=True)
    host_path = pathlib.Path(path).resolve()
    assert str(host_path).startswith(str(work_root)), "Path not within allowed work root"
    if engine == "local":
        proc = subprocess.run(cmd, shell=True, cwd=str(host_path), capture_output=True, text=True, timeout=timeout_sec or pol["sandbox"]["timeout_sec"])
        return {"exit_code": proc.returncode, "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-8000:]}
    image = pol["sandbox"]["image_python"] if lang=="python" else pol["sandbox"]["image_node"]
    net = pol["sandbox"]["network"]
    mem = pol["sandbox"]["mem_limit"]; cpu = str(pol["sandbox"]["cpu_shares"])
    target = pol["sandbox"]["mount_target"]
    docker_cmd = [engine, "run", "--rm", "-v", f"{host_path}:{target}", "-w", target, "--network", net, "--memory", mem, "--cpu-shares", cpu, "--pids-limit","256","--read-only","--tmpfs","/tmp:rw,size=64m", image, "sh", "-lc", cmd]
    proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout_sec or pol["sandbox"]["timeout_sec"])
    return {"exit_code": proc.returncode, "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-8000:]}
