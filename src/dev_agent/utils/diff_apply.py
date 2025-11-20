from __future__ import annotations
import os, re, pathlib
from typing import List, Tuple

class PatchError(Exception): pass

HUNK_RE = re.compile(r'^@@ -(?P<lstart>\d+)(,(?P<llines>\d+))? \+(?P<rstart>\d+)(,(?P<rlines>\d+))? @@')

def apply_unified_diff(root: str, patch_text: str) -> dict:
    rootp = pathlib.Path(root).resolve()
    created, deleted, modified = [], [], []
    lines = patch_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith('--- '):
            src = lines[i][4:].strip(); i += 1
            assert i < len(lines) and lines[i].startswith('+++ '), "Malformed diff: missing +++"
            dst = lines[i][4:].strip()
            def norm(p):
                p = p.strip()
                if p.startswith("a/") or p.startswith("b/"): p = p[2:]
                return str(rootp / p)
            srcp, dstp = norm(src), norm(dst)
            i += 1
            hunks = []
            while i < len(lines) and lines[i].startswith('@@ '):
                m = HUNK_RE.match(lines[i])
                if not m: raise PatchError("Bad hunk header: " + lines[i])
                i += 1
                hunk_lines = []
                while i < len(lines) and not lines[i].startswith('@@ ') and not lines[i].startswith('--- '):
                    hunk_lines.append(lines[i]); i += 1
                hunks.append((m, hunk_lines))
            exists = os.path.exists(dstp)
            original = []
            if exists:
                with open(dstp, 'r', encoding='utf-8', errors='ignore') as f:
                    original = f.read().splitlines()
            new = []
            src_cursor = 0
            for m, hunk_lines in hunks:
                lstart = int(m.group('lstart')) - 1
                while src_cursor < lstart and src_cursor < len(original):
                    new.append(original[src_cursor]); src_cursor += 1
                for hl in hunk_lines:
                    if not hl: continue
                    tag = hl[0]
                    if tag == ' ':
                        new.append(original[src_cursor]); src_cursor += 1
                    elif tag == '-':
                        src_cursor += 1
                    elif tag == '+':
                        new.append(hl[1:])
                    elif tag == '\\':
                        pass
                    else:
                        raise PatchError("Unknown hunk tag: " + tag)
            while src_cursor < len(original):
                new.append(original[src_cursor]); src_cursor += 1
            if not exists and new:
                os.makedirs(os.path.dirname(dstp), exist_ok=True)
                with open(dstp, 'w', encoding='utf-8') as f: f.write('\n'.join(new) + '\n')
                created.append(dstp)
            elif exists and not new:
                os.remove(dstp); deleted.append(dstp)
            else:
                if '\n'.join(original) != '\n'.join(new):
                    os.makedirs(os.path.dirname(dstp), exist_ok=True)
                    with open(dstp, 'w', encoding='utf-8') as f: f.write('\n'.join(new) + '\n')
                    if exists: modified.append(dstp)
        else:
            i += 1
    return {"files_changed": len(created)+len(deleted)+len(modified),
            "created": created, "deleted": deleted, "modified": modified}
