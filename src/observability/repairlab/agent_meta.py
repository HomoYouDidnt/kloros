#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys, time, shutil, re, hashlib, os
from dataclasses import dataclass
from pathlib import Path
import ast

LIBROOT = Path("/home/kloros/toolgen/library/patterns")
LLM_HOOK = Path("/home/kloros/bin/llm_patch.sh")

@dataclass
class RepairResult:
    ok: bool
    attempts: int
    strategy: str
    pattern_id: str|None = None
    details: dict = None

# ---------- Utilities ----------
def run_pytest(bundle_dir: Path, timeout_s: int = 45, with_cov: bool = False) -> tuple[bool,str]:
    env = dict(**dict(), PYTHONPATH=str(bundle_dir))
    pytest_bin = "/home/kloros/.venv/bin/pytest"
    cmd = [pytest_bin, "-q"]
    if with_cov:
        cmd = [pytest_bin, "--cov=tool", "--cov-branch", "-q"]
    try:
        p = subprocess.run(
            cmd, cwd=bundle_dir, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout_s
        )
        return (p.returncode == 0, p.stdout)
    except subprocess.TimeoutExpired as e:
        return (False, f"[TIMEOUT]\n{e.stdout or ''}")

def static_check(tool_py: Path) -> tuple[bool,str]:
    try:
        code = tool_py.read_text()
        ast.parse(code)  # syntax check
        # forbid dangerous names (conservative)
        forbidden = re.compile(r"\b(os\.system|subprocess\.|open\(|exec\(|eval\(|socket\.|requests\.)")
        if forbidden.search(code):
            return False, "forbidden API detected"
        return True, "ok"
    except Exception as e:
        return False, f"syntax/static err: {e}"

def bundle_hash(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()

def covered_function_name(bundle_dir: Path) -> str | None:
    """Return most-covered function in tool/tool.py from the last pytest run."""
    cov_file = bundle_dir / ".coverage"
    if not cov_file.exists():
        return None
    try:
        import coverage
        cov = coverage.Coverage(data_file=str(cov_file))
        cov.load()
        tool_py = (bundle_dir / "tool" / "tool.py").resolve()
        data = cov.get_data()
        lines = data.lines(str(tool_py)) or []
        # Map line→function
        src = ast.parse(tool_py.read_text())
        fn_spans = []
        for n in ast.walk(src):
            if isinstance(n, ast.FunctionDef):
                fn_spans.append((n.name, getattr(n, "lineno", 0), getattr(n, "end_lineno", 10**9)))
        # Score by number of covered lines inside each function
        best = None
        for name, lo, hi in fn_spans:
            score = sum(1 for L in lines if lo <= L <= hi)
            if not best or score > best[1]:
                best = (name, score)
        return best[0] if best and best[1] > 0 else None
    except Exception:
        return None

# ---------- Fault localization ----------
def failing_targets(pytest_output: str) -> list[tuple[str,int]]:
    # parse lines like: tool/tool.py:23: in <module> or in function
    locs=[]
    for line in pytest_output.splitlines():
        m = re.search(r"(tool[/\\]tool\.py):(\d+)", line)
        if m:
            locs.append((m.group(1), int(m.group(2))))
    return locs or [("tool/tool.py", None)]

def find_enclosing_function(tool_py: Path, target_line: int|None) -> str|None:
    try:
        code = tool_py.read_text()
        t = ast.parse(code)
        func_name = None
        for n in ast.walk(t):
            if isinstance(n, ast.FunctionDef):
                if target_line is None:  # best effort: first exported function
                    return n.name
                if getattr(n, "lineno", 10**9) <= target_line <= getattr(n, "end_lineno", -1):
                    func_name = n.name
        return func_name
    except Exception:
        return None

# ---------- Pattern retrieval ----------
def top_patterns_for_spec(spec_id: str, k: int = 3) -> list[tuple[Path, dict]]:
    """Return top-K patterns ranked by quality (median_ms, wins)."""
    spec_dir = LIBROOT / spec_id
    if not spec_dir.exists():
        return []
    ranked = []
    for cluster in sorted(spec_dir.iterdir()):
        mf = cluster / "manifest.json"; sn = cluster / "snippet.py"
        if not (mf.exists() and sn.exists()):
            continue
        m = json.loads(mf.read_text())
        qual = m.get("quality", {})
        key = (qual.get("median_ms", 1e9), -qual.get("wins", 0))
        ranked.append((key, cluster, m))
    ranked.sort()
    return [(c, m) for _key, c, m in ranked[:k]]

# ---------- Signature utilities ----------
def _fn_sig_map(fn: ast.FunctionDef) -> dict:
    """Return a signature dict with arg names and defaults."""
    args = [a.arg for a in fn.args.args]
    defaults = fn.args.defaults or []
    # align defaults from the right
    num_required = len(args) - len(defaults)
    def_map = {args[num_required + i]: defaults[i] for i in range(len(defaults))}
    return {"args": args, "defaults": def_map}

def _make_call_kwargs(dst_sig: dict, src_sig: dict) -> tuple[dict, list]:
    """
    Build kwargs for calling src(fn) using dst(fn)'s arg names.
    Returns (kw_assignments, missing_required_list).
    """
    kw = {}
    missing = []
    for name in dst_sig["args"]:
        if name in src_sig["args"]:
            kw[name] = ast.Name(id=name, ctx=ast.Load())
        elif name in dst_sig["defaults"]:
            # destination arg has default — omit to use default
            continue
        else:
            missing.append(name)
    return kw, missing

def _wrap_with_adapter(dst_mod: ast.Module, dst_fn: ast.FunctionDef, src_fn_name: str, src_sig: dict, dst_sig: dict) -> ast.Module:
    """
    Keep src implementation under a private symbol, and create a wrapper with the original name.
    """
    wrapper_name = dst_fn.name
    impl_name = f"_{wrapper_name}_impl"
    # Build call kwargs from dst args
    kw_map, _missing = _make_call_kwargs(dst_sig, src_sig)
    call = ast.Call(func=ast.Name(id=impl_name, ctx=ast.Load()),
                    args=[], keywords=[ast.keyword(arg=k, value=v) for k, v in kw_map.items()])
    new_wrapper = ast.FunctionDef(
        name=wrapper_name,
        args=dst_fn.args, body=[ast.Return(value=call)],
        decorator_list=[], returns=dst_fn.returns, type_comment=None
    )
    # Replace the old dst_fn node with wrapper
    new_body = []
    for n in dst_mod.body:
        if n is dst_fn:
            new_body.append(new_wrapper)
        else:
            new_body.append(n)
    dst_mod.body = new_body
    return dst_mod

# ---------- AST transplant ----------
def transplant_function(src_snippet: Path, dst_tool: Path, fn_name_hint: str|None) -> bool:
    src_mod = ast.parse(src_snippet.read_text())
    dst_code = dst_tool.read_text()
    dst_mod = ast.parse(dst_code)

    src_fn = next((n for n in src_mod.body if isinstance(n, ast.FunctionDef)), None)
    if not src_fn:
        return False

    # find target by hint or first function
    dst_fn = None
    if fn_name_hint:
        for n in dst_mod.body:
            if isinstance(n, ast.FunctionDef) and n.name == fn_name_hint:
                dst_fn = n; break
    if not dst_fn:
        dst_fn = next((n for n in dst_mod.body if isinstance(n, ast.FunctionDef)), None)
        fn_name_hint = getattr(dst_fn, "name", None)
    if not dst_fn:
        return False

    # derive signatures
    src_sig = _fn_sig_map(src_fn)
    dst_sig = _fn_sig_map(dst_fn)

    # Strategy: insert source implementation as _<name>_impl, create wrapper with adapter
    impl_fn = ast.FunctionDef(
        name=f"_{dst_fn.name}_impl",
        args=src_fn.args, body=src_fn.body,
        decorator_list=src_fn.decorator_list, returns=src_fn.returns, type_comment=src_fn.type_comment
    )

    # insert impl function into module
    new_body=[]
    replaced=False
    for n in dst_mod.body:
        if isinstance(n, ast.FunctionDef) and n is dst_fn:
            new_body.append(impl_fn)
            replaced=True
        else:
            new_body.append(n)
    if not replaced:
        return False
    dst_mod.body = new_body

    # create wrapper with original signature that calls _impl
    dst_mod = _wrap_with_adapter(dst_mod, dst_fn, impl_fn.name, src_sig, dst_sig)

    fixed = ast.unparse(dst_mod) if hasattr(ast, "unparse") else _py38_unparse(dst_mod)
    dst_tool.write_text(fixed)
    return True

def _py38_unparse(tree: ast.AST) -> str:
    # fallback minimal unparse (Python <3.9 not expected in your env)
    import astor  # if ever needed
    return astor.to_source(tree)

# ---------- Micro-fix heuristics ----------
def heuristic_microfix(tool_py: Path) -> bool:
    code = tool_py.read_text()
    orig = code
    # Example early-return remover: if function returns "" immediately, comment it out
    code = re.sub(r"return\s+[\"']{0,2}\"\s*#?\s*INTENTIONAL\s*BUG[^\n]*", "# removed bug return", code, count=1)
    # Example wrong operator swap (>= vs >) – very conservative (only if tests keep failing, this may help)
    # (leave disabled by default for safety)
    if code != orig:
        tool_py.write_text(code)
        return True
    return False


def llm_guided_patch(bundle_dir: Path) -> tuple[bool, str]:
    """
    Call a local LLM patch hook (shell script). The hook should:
    - read bundle_dir
    - write an updated tool/tool.py (in-place) if it proposes a patch
    - print JSON {"ok": true/false, "note": "..."} and exit 0 even on failure
    """
    if not LLM_HOOK.exists() or os.environ.get("ENABLE_LLM_PATCH") != "1":
        return (False, "LLM disabled")
    try:
        p = subprocess.run([str(LLM_HOOK), str(bundle_dir)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        obj = json.loads(p.stdout.strip() or "{}")
        return (bool(obj.get("ok")), obj.get("note",""))
    except Exception as e:
        return (False, f"LLM hook error: {e}")

# ---------- Main agent ----------
def repair(bundle_dir: str, spec_id: str|None=None) -> RepairResult:
    b = Path(bundle_dir)
    tool_py = b / "tool" / "tool.py"
    ok, out = run_pytest(b, with_cov=True)
    if ok:
        return RepairResult(True, 0, "noop", None, {"note":"already passing"})

    # 1) Coverage-guided localization
    cov_fn = covered_function_name(b)
    target_fn = cov_fn or find_enclosing_function(tool_py, failing_targets(out)[0][1])

    # 2) Pattern transplant (if spec known & pattern exists)
    attempts = 0
    if spec_id:
        for pdir, pman in top_patterns_for_spec(spec_id, k=3):
            attempts += 1
            backup = tool_py.read_text()
            if transplant_function(pdir/"snippet.py", tool_py, target_fn):
                ok_s, _ = static_check(tool_py)
                if ok_s:
                    ok2, out2 = run_pytest(b)
                    if ok2:
                        return RepairResult(True, attempts, "pattern_transplant",
                                            f'{pman.get("spec_id", spec_id)}:{pman.get("cluster_id","unknown")}',
                                            {"static":"ok","pytest":out2})
            tool_py.write_text(backup)

    # 3) Heuristic micro-fix
    attempts += 1
    backup = tool_py.read_text()
    if heuristic_microfix(tool_py):
        ok_s, msg_s = static_check(tool_py)
        if ok_s:
            ok3, out3 = run_pytest(b)
            if ok3:
                return RepairResult(True, attempts, "heuristic_microfix", None,
                                    {"static":"ok","pytest":out3})
        tool_py.write_text(backup)


    # 4) LLM guided (opt-in)
    attempts += 1
    backup = tool_py.read_text()
    ok_llm, note = llm_guided_patch(b)
    if ok_llm:
        ok_s, _ = static_check(tool_py)
        if ok_s:
            ok4, out4 = run_pytest(b)
            if ok4:
                return RepairResult(True, attempts, "llm_patch", None,
                                    {"static":"ok","pytest":out4,"note":note})
    tool_py.write_text(backup)

    return RepairResult(False, attempts, "exhausted", None, {"pytest":out})

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", required=True, help="Path to ToolGen→RepairLab handoff JSON")
    args = ap.parse_args()
    meta = json.loads(Path(args.handoff).read_text())
    bdir = Path(meta["bundle_dir"])
    spec_path = meta.get("spec_path")
    spec_id = Path(spec_path).stem if spec_path else None

    res = repair(str(bdir), spec_id=spec_id)
    out = {
        "ok": res.ok,
        "attempts": res.attempts,
        "strategy": res.strategy,
        "pattern_id": res.pattern_id,
        "details": res.details,
        "bundle_sha256": bundle_hash(bdir)
    }
    print(json.dumps(out, indent=2))
    # exit code -> watcher marks .ok or .fail
    sys.exit(0 if res.ok else 1)

if __name__ == "__main__":
    main()
