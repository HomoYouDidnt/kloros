#!/usr/bin/env python3
"""Check that all public tool functions are decorated with @track_tool."""
import os, ast, sys, pathlib

ROOT = pathlib.Path("/home/kloros/src/tools")
missing = []

for py in ROOT.rglob("*.py"):
    if py.name == "tracker.py" or py.name == "__init__.py":
        continue
    
    try:
        t = ast.parse(py.read_text(encoding="utf-8"), str(py))
    except:
        continue
    
    for node in t.body:
        if isinstance(node, ast.FunctionDef):
            # Skip private functions
            if node.name.startswith("_"):
                continue
            
            # Check decorators
            decos = []
            for d in node.decorator_list:
                if isinstance(d, ast.Name):
                    decos.append(d.id)
                elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name):
                    decos.append(d.func.id)
                elif isinstance(d, ast.Attribute):
                    decos.append(d.attr)
            
            if "track_tool" not in decos:
                missing.append(f"{py.relative_to(ROOT.parent)}:{node.name}")

if missing:
    print("❌ Untracked tools:")
    for m in missing:
        print(f"  {m}")
    sys.exit(1)

print("✅ All tools decorated with @track_tool")
