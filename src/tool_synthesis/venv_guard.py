"""
Virtual Environment Isolation Guardrails for Tool Synthesis.

Ensures all synthesized tool execution stays within the venv boundary.
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Set


class VenvGuard:
    """Enforces virtual environment isolation for tool synthesis."""

    def __init__(self, venv_path: str = "/home/kloros/.venv"):
        self.venv_path = Path(venv_path)
        self.allowed_paths = self._get_allowed_paths()

    def _get_allowed_paths(self) -> Set[str]:
        """Get all paths that should be allowed for imports."""
        allowed = set()

        # Venv paths
        allowed.add(str(self.venv_path))
        venv_site = self.venv_path / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        if venv_site.exists():
            allowed.add(str(venv_site))

        # Project paths
        allowed.add("/home/kloros")
        allowed.add("/home/kloros/src")

        # Standard library only (not system site-packages)
        for path in sys.path:
            if "site-packages" not in path and (path.startswith("/usr/lib/python") or path.startswith("/usr/local/lib/python")):
                allowed.add(path)

        return allowed

    def create_isolated_namespace(self) -> Dict:
        """Create a namespace that enforces venv isolation."""

        original_import = __builtins__["__import__"]

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            """Import function that blocks system packages outside venv."""
            try:
                module = original_import(name, globals, locals, fromlist, level)

                # Check module path if available
                if hasattr(module, "__file__") and module.__file__:
                    module_path = str(Path(module.__file__).resolve())

                    # Allow if within venv or project paths
                    is_allowed = any(module_path.startswith(allowed) for allowed in self.allowed_paths)

                    if not is_allowed:
                        raise ImportError(
                            f"VENV_GUARD: Module '{name}' from {module_path} is outside venv. "
                            f"Install with: pip install {name}"
                        )

                return module

            except ImportError as e:
                if "VENV_GUARD:" in str(e):
                    raise e
                else:
                    raise ImportError(f"Module '{name}' not found. Install with: pip install {name}") from e

        # Create guarded namespace
        namespace = dict(__builtins__)
        namespace.update({
            "__name__": "__main__",
            "__file__": "<synthesized_tool>",
            "__path__": ["/home/kloros"],
            "__import__": guarded_import
        })

        return {"__builtins__": namespace}

    def validate_tool_safety(self, tool_code: str) -> tuple[bool, str]:
        """Validate that tool code respects venv boundaries."""
        import ast

        try:
            tree = ast.parse(tool_code)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split(".")[0])

            # Test imports with venv guard
            test_namespace = self.create_isolated_namespace()

            for module_name in set(imports):
                if not module_name:
                    continue

                try:
                    exec(f"import {module_name}", test_namespace)
                except ImportError as e:
                    if "VENV_GUARD:" in str(e):
                        return False, str(e)
                    else:
                        return False, f"Missing dependency: {e}"

            return True, "All imports are venv-safe"

        except Exception as e:
            return False, f"Validation error: {e}"


def create_venv_isolated_namespace() -> Dict:
    """Create venv-isolated namespace for tool execution."""
    guard = VenvGuard()
    return guard.create_isolated_namespace()


def validate_tool_venv_safety(tool_code: str) -> tuple[bool, str]:
    """Validate tool respects venv boundaries."""
    guard = VenvGuard()
    return guard.validate_tool_safety(tool_code)
