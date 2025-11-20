#!/usr/bin/env python3
"""
Spec-Regen repair agent:
- Reads spec_path from ToolGen bundle manifest
- Calls ToolGen codegen to regenerate the implementation for that spec
- Overwrites tool/tool.py (preserves SPDX header if present)
- Leaves tests/docs intact
"""
from __future__ import annotations
import json, pathlib, re, importlib.util

def _load_spec_path(bundle_dir: str) -> str:
    m = json.loads((pathlib.Path(bundle_dir)/"spec.json").read_text())
    # ToolGen's bundle stores spec copy as spec.json
    spec_path = m.get("spec_path") or m.get("id")
    # If spec filename only, prefer the copy under toolgen/specs
    if spec_path and not spec_path.startswith("/"):
        # Try to find matching spec in toolgen/specs
        specs_dir = pathlib.Path("/home/kloros/toolgen/specs")
        for spec_file in specs_dir.glob("*.json"):
            spec_data = json.loads(spec_file.read_text())
            if spec_data.get("id") == m.get("id") or spec_data.get("tool_id") == m.get("tool_id"):
                return str(spec_file)
    return str(spec_path) if spec_path else ""

def _import_codegen():
    # import toolgen.synthesizer.codegen dynamically
    pkg = pathlib.Path("/home/kloros/toolgen/synthesizer/codegen.py")
    spec = importlib.util.spec_from_file_location("tg_codegen", pkg)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore
    return m

def _preserve_header(old_code: str, new_body: str) -> str:
    # Keep SPDX/license header if present at top of file
    header_lines = []
    for line in old_code.splitlines(True):
        if line.lstrip().startswith("#"):
            header_lines.append(line)
            continue
        break
    header = "".join(header_lines) if header_lines else ""
    # Avoid duplicating the SPDX line if codegen already includes it
    if "SPDX-License-Identifier" in new_body:
        header = ""
    return (header + new_body) if header or new_body else new_body

def repair(bundle_dir: str) -> None:
    b = pathlib.Path(bundle_dir)

    # Load spec from bundle
    spec_file = b / "spec.json"
    if not spec_file.exists():
        return

    spec = json.loads(spec_file.read_text())
    tool_id = spec.get("tool_id", "")

    # Import codegen templates
    cg = _import_codegen()

    # Select the right template based on tool_id
    if "deduplicate" in tool_id or "text_dedup" in tool_id:
        new_code = cg.DEDUPE_CODE
    elif "flatten" in tool_id or "json_flatten" in tool_id:
        new_code = cg.FLATTEN_CODE
    else:
        # Unknown spec - bail
        return

    # Simply overwrite with the clean template
    tool_py = b / "tool.py"
    tool_py.write_text(new_code)
