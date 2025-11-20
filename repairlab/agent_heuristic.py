#!/usr/bin/env python3
from __future__ import annotations
import ast, pathlib, re
from typing import Tuple

def _read(p: pathlib.Path) -> str: return p.read_text(encoding="utf-8")
def _write(p: pathlib.Path, s: str): p.write_text(s, encoding="utf-8")

def _fix_return_empty_string(code: str) -> Tuple[str,bool]:
    # Find `return ""` or `return ''` in target function bodies and remove if unconditional
    pat = re.compile(r"return\s+[\"\']{2}\s*$", re.M)
    new = pat.sub("# patched: removed empty-string return", code)
    return new, (new != code)

def _fix_early_return_none(code: str) -> Tuple[str,bool]:
    pat = re.compile(r"return\s+None\s*$", re.M)
    new = pat.sub("# patched: removed early return None", code)
    return new, (new != code)

def _fix_off_by_one_range(code: str) -> Tuple[str,bool]:
    # naive: range(len(x)) → ok; range(n-1) → suspicious, try range(n)
    new = re.sub(r"range\((\w+)\s*-\s*1\)", r"range(\1)", code)
    return new, (new != code)

def _fix_wrong_operator(code: str) -> Tuple[str,bool]:
    # swap "== True" → "is True", "!= True" → "is not True" (style + clarity)
    new = re.sub(r"==\s*True\b", "is True", code)
    new = re.sub(r"!=\s*True\b", "is not True", new)
    return new, (new != code)

def repair(bundle_dir: str) -> None:
    tool = pathlib.Path(bundle_dir)/"tool.py"
    if not tool.exists(): return
    code = _read(tool)

    changed = False
    for fixer in (_fix_return_empty_string, _fix_early_return_none, _fix_off_by_one_range, _fix_wrong_operator):
        code, did = fixer(code); changed = changed or did

    if changed:
        _write(tool, code)
        return

    # Fallback: delegate to spec-regen agent
    import importlib.util
    regen_p = pathlib.Path("/home/kloros/repairlab/agent_regen.py")
    if regen_p.exists():
        spec = importlib.util.spec_from_file_location("agent_regen", regen_p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)  # type: ignore
        m.repair(bundle_dir)
