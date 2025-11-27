import os, sys, subprocess, difflib, pathlib, yaml, shlex

ROOT = pathlib.Path("/home/kloros")
TASK = ROOT / "_tasks"
CFG  = ROOT / "src/selfcoder/selfcoder.yaml"

def run(cmd, check=True, capture=True):
    print(f"[$] {cmd}")
    res = subprocess.run(cmd, shell=True, text=True,
                         stdout=subprocess.PIPE if capture else None,
                         stderr=subprocess.STDOUT)
    if check and res.returncode != 0:
        raise RuntimeError(res.stdout)
    return res.stdout if capture else ""

def load_cfg():
    with open(CFG) as f: return yaml.safe_load(f)

def safe_path(p, allow_paths):
    p = str(pathlib.Path(p).resolve())
    return any(p.startswith(a) for a in allow_paths)

def write_patch(task_dir, patch):
    cfg = load_cfg()
    if len(patch.encode()) > cfg["limits"]["max_patch_bytes"]:
        raise RuntimeError("Patch too large")
    touched = []
    for line in patch.splitlines():
        if line.startswith('+++ ') or line.startswith('--- '):
            fn = line.split('\t')[0][4:].strip()
            if fn not in ("", "/dev/null") and fn.startswith("/"):
                touched.append(fn)
    files = sorted(set(touched))
    if len(files) > cfg["limits"]["max_files_changed"]:
        raise RuntimeError("Too many files changed")
    for fn in files:
        if not safe_path(fn, cfg["allow_paths"]):
            raise RuntimeError(f"Illegal path: {fn}")
        for pat in cfg.get("deny_globs", []):
            if pathlib.Path(fn).match(pat):
                raise RuntimeError(f"Denied by policy: {fn}")
    (task_dir / "PATCH.diff").write_text(patch, encoding="utf-8")

def unified_diff(old_text, new_text, filename):
    return "".join(difflib.unified_diff(
        old_text.splitlines(True), new_text.splitlines(True),
        fromfile=filename, tofile=filename, n=3))

def read_file(path): return pathlib.Path(path).read_text(encoding="utf-8")

def start_task(name):
    run(f"/home/kloros/scripts/task start {name}")

def evidence(task, commands):
    for c in commands:
        run(f"/home/kloros/scripts/task evidence {task} {shlex.quote(c)}")

def apply_task(name):
    run(f"/home/kloros/scripts/task apply {name}")

def main():
    if len(sys.argv) < 3:
        print("Usage: selfcoder <task-name> <mode> [args..]")
        print("Modes: plan, patch <file> <search> <replace>, apply")
        sys.exit(2)

    name, mode = sys.argv[1], sys.argv[2]
    task_dir = TASK / name
    cfg = load_cfg()

    if mode == "plan":
        start_task(name)
        ev = [
            "rg -n \"def create_stt_backend|WhisperModel\" -S src",
            "rg -n \"@track_tool|def .*\\(\" -S src/tools",
            "python - <<'PY'\nimport importlib;mods=['kloros_voice','stt.base','voice.tts.router'];print({m:bool(importlib.import_module(m)) for m in mods})\nPY"
        ]
        evidence(name, ev)
        print(f"[OK] Task scaffolded at {task_dir}")
        return

    if mode == "patch":
        if len(sys.argv) != 6:
            print("patch mode: selfcoder <task> patch <file> <search> <replace>"); sys.exit(2)
        _, _, _, file_path, search, replace = sys.argv
        full = pathlib.Path(file_path)
        old = read_file(full)
        new = old.replace(search, replace)
        if old == new:
            print("No changes produced."); sys.exit(1)
        diff = unified_diff(old, new, str(full))
        write_patch(task_dir, diff)
        print("[OK] Patch staged at", task_dir / "PATCH.diff")
        return

    if mode == "apply":
        apply_task(name)
        print("[OK] Applied")
        return

if __name__ == "__main__":
    os.environ.setdefault("KLR_REGISTRY","/home/kloros/src/registry/capabilities.yaml")
    main()
