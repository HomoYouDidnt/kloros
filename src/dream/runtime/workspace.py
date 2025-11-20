# src/dream/runtime/workspace.py
import os, shutil, time, json, difflib, pathlib, hashlib

ROOT = pathlib.Path(os.getenv("DREAM_WORKSPACE", ".")).resolve()
STORE = ROOT / ".dreamp"
SNAP  = STORE / "snapshots"
ARTS  = STORE / "artifacts"
ALLOW = [ROOT / "src", ROOT / "tests"]

# Create directories, but don't fail if we don't have permissions
# (e.g., during testing when ROOT is not writable)
try:
    for p in (SNAP, ARTS): p.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError):
    pass  # Will be created on first use if needed

def _ts(): return time.strftime("%Y%m%d-%H%M%S", time.localtime())
def _walk(p): return [x for x in p.rglob("*") if x.is_file()]
def _rel(p):  return str(p.relative_to(ROOT))
def _hash(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for ch in iter(lambda: f.read(1<<16), b""): h.update(ch)
    return h.hexdigest()

def snapshot_create(label=""):
    sid = f"{_ts()}_{label}" if label else _ts()
    dst = SNAP / sid; dst.mkdir(parents=True, exist_ok=True)
    for base in ("src","tests"):
        s = ROOT / base
        if s.exists(): shutil.copytree(s, dst / base, dirs_exist_ok=True)
    meta = {"id": sid, "created_at": time.time(),
            "files": {_rel(p): _hash(p) for base in ("src","tests")
                      if (ROOT/base).exists() for p in _walk(ROOT/base)}}
    (dst / "snapshot.json").write_text(json.dumps(meta, indent=2))
    return sid

def snapshot_restore(sid: str):
    src = SNAP / sid
    assert src.exists(), f"snapshot {sid} missing"
    for base in ("src","tests"):
        tgt = ROOT / base
        if tgt.exists(): shutil.rmtree(tgt)
        if (src / base).exists(): shutil.copytree(src / base, tgt)

def _read_text(p):
    if not p: return []
    try: return p.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    except: return ["<binary>\n"]

def diff_report(prev_sid: str):
    prev = SNAP / prev_sid
    # CRITICAL: Only compare src/ and tests/ in workspace ROOT, not in snapshot dir
    before = {_rel(p): p for base in ("src","tests") if (prev/base).exists()
              for p in _walk(prev / base)}
    now = {_rel(p): p for base in ("src","tests") if (ROOT/base).exists()
           for p in _walk(ROOT / base)}

    # Filter out any snapshot directory pollution
    before = {k: v for k, v in before.items() if not k.startswith('.dreamp/')}
    now = {k: v for k, v in now.items() if not k.startswith('.dreamp/')}

    keys = sorted(set(before) | set(now))
    changes = []
    for k in keys:
        a, b = before.get(k), now.get(k)
        if a and b and _hash(a) == _hash(b): continue
        status = "modified"
        if a and not b: status = "deleted"
        elif b and not a: status = "added"
        diff = difflib.unified_diff(_read_text(a), _read_text(b),
                                    fromfile=f"a/{k}", tofile=f"b/{k}")
        changes.append({"file": k, "status": status, "diff": "".join(diff)})
    rep = {"base_snapshot": prev_sid, "changes": changes,
           "summary": {"added": sum(c["status"]=="added" for c in changes),
                       "deleted": sum(c["status"]=="deleted" for c in changes),
                       "modified": sum(c["status"]=="modified" for c in changes),
                       "total": len(changes)}}
    out = ARTS / f"diff_{_ts()}.json"
    out.write_text(json.dumps(rep, indent=2))
    return rep

def enforce_allowlist(rel_paths):
    """Check that all file paths are within allowlist (src/, tests/ only)."""
    for rel in rel_paths:
        abs_p = (ROOT / rel).resolve()
        if not any(str(abs_p).startswith(str(a.resolve())) for a in ALLOW):
            return False
    return True

# Safety rails: forbidden patterns in diffs
FORBIDDEN_PATTERNS = [
    "curl ",
    "wget ",
    "ssh ",
    "rm -rf",
    "eval(",
    "exec(",
    "subprocess.call",
    "__import__",
    "open('"
]

def check_forbidden_patterns(diff_text: str) -> tuple[bool, list[str]]:
    """
    Check diff for forbidden patterns.

    Returns:
        (safe, violations) - True if safe, False with list of violations
    """
    violations = []
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in diff_text:
            violations.append(pattern)
    return (len(violations) == 0, violations)
