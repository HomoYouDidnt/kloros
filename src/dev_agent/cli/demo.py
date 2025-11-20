#!/usr/bin/env python3
"""Demo script for Dev Agent functionality."""
import os, sys, json
sys.path.insert(0, '/home/kloros')

from src.dev_agent.controller.dev_loop import run_task

PATCH = """--- a/src/app/__init__.py
+++ b/src/app/__init__.py
@@ -1,1 +1,6 @@
-def add(a:int,b:int)->int:
-    return a+b
+def add(a:int,b:int)->int:
+    return a+b
+
+def mul(a:int,b:int)->int:
+    \"\"\"Multiply two integers.\"\"\"
+    return a*b
"""

SPEC = {
  "path": "./_scratch/work/app",
  "template": "python",
  "tasks": [
    {"name":"impl mul", "patch": PATCH, "test_cmd":"python -m pytest -q", "manifest":"pip"}
  ],
  "git": {"branch":"feat-mul","title":"feat: add mul","body":"Implements mul() with a smoke test","target":"main"}
}

if __name__ == "__main__":
    os.makedirs("./_scratch/work", exist_ok=True)
    res = run_task(SPEC)
    print(json.dumps(res, indent=2))
