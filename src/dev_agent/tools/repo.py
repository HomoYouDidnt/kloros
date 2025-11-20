import os, shutil, pathlib
from typing import Literal
from ..utils.diff_apply import apply_unified_diff
from src.tools.tracker import track_tool

@track_tool()
def repo_init(path: str, template: Literal['python','node','blank']='python'):
    p = pathlib.Path(path).resolve()
    if p.exists() and any(p.iterdir()):
        raise RuntimeError(f"Directory not empty: {p}")
    os.makedirs(p, exist_ok=True)
    base = pathlib.Path(__file__).resolve().parents[1]
    tdir = base / 'templates' / template
    if tdir.exists():
        shutil.copytree(tdir, p, dirs_exist_ok=True)
    else:
        (p / 'README.md').write_text("# New Project\n", encoding='utf-8')
    return {"ok": True}

@track_tool()
def apply_patch(path: str, patch_unified: str):
    res = apply_unified_diff(path, patch_unified)
    return {"ok": True, **res}
