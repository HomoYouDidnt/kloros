#!/usr/bin/env python3
"""
Code Structure Evidence Plugin - Gathers evidence from code structure analysis.
"""

import ast
import logging
from pathlib import Path
from typing import Dict, Any, List

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class CodeStructurePlugin(EvidencePlugin):
    """
    Analyzes code structure using AST parsing and file system inspection.

    Evidence types:
    - File structure (directory layout, file organization)
    - AST structure (classes, functions, imports)
    - Docstrings and comments
    - Import relationships
    """

    @property
    def name(self) -> str:
        return "code_structure"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        code_related_types = {
            "code_behavior",
            "capability_discovery",
            "integration_analysis",
            "module_structure"
        }
        return investigation_type in code_related_types or "code" in question.lower() or "module" in question.lower()

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        evidence = []

        search_paths = self._extract_search_paths(question, context)

        for search_path in search_paths:
            path = Path(search_path)

            if not path.exists():
                continue

            if path.is_file() and path.suffix == ".py":
                evidence.extend(self._analyze_python_file(path))
            elif path.is_dir():
                evidence.extend(self._analyze_directory(path))

        return evidence

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        search_paths = self._extract_search_paths(question, context)
        file_count = sum(1 for p in search_paths if Path(p).exists())

        return {
            "time_estimate_seconds": file_count * 0.1,
            "token_cost": 0,
            "complexity": "low" if file_count < 10 else "medium" if file_count < 50 else "high"
        }

    def priority(self, investigation_type: str) -> int:
        if investigation_type in {"code_behavior", "capability_discovery", "module_structure"}:
            return 90
        return 60

    def _extract_search_paths(self, question: str, context: Dict[str, Any]) -> List[str]:
        """
        Extract file/directory paths from question and context.
        """
        paths = []

        existing_evidence = context.get("existing_evidence", [])
        for ev in existing_evidence:
            if ev.evidence_type == "file_path":
                if "paths" in ev.metadata:
                    paths.extend(ev.metadata["paths"])
                elif "primary_path" in ev.metadata:
                    paths.append(ev.metadata["primary_path"])
                elif "path" in ev.metadata:
                    paths.append(ev.metadata["path"])
                elif isinstance(ev.content, list):
                    paths.extend(ev.content)
                else:
                    paths.append(ev.content)
            elif "path" in ev.metadata:
                paths.append(ev.metadata["path"])

        import re
        path_pattern = r'/[\w/\-\.]+\.py'
        found_paths = re.findall(path_pattern, question)
        paths.extend(found_paths)

        dir_pattern = r'/[\w/\-]+/src/[\w/\-]+'
        found_dirs = re.findall(dir_pattern, question)
        paths.extend(found_dirs)

        if not paths:
            intent = context.get("intent", {})
            if "module" in intent.get("investigation_type", ""):
                paths.append("/home/kloros/src")

        return list(set(paths))

    def _analyze_python_file(self, file_path: Path) -> List[Evidence]:
        """
        Analyze a single Python file using AST.
        """
        evidence = []

        try:
            content = file_path.read_text(errors='ignore')
            tree = ast.parse(content)

            module_doc = ast.get_docstring(tree)
            if module_doc:
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="module_docstring",
                    content=module_doc,
                    metadata={"file": str(file_path)},
                    timestamp="",
                    confidence=0.9
                ))

            classes = []
            functions = []
            imports = []

            method_names = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_doc = ast.get_docstring(node)
                    class_methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    method_names.update(class_methods)
                    classes.append({
                        "name": node.name,
                        "methods": class_methods,
                        "docstring": class_doc[:200] if class_doc else None
                    })

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name not in method_names:
                    func_doc = ast.get_docstring(node)
                    functions.append({
                        "name": node.name,
                        "args": [arg.arg for arg in node.args.args],
                        "docstring": func_doc[:200] if func_doc else None
                    })

            if classes:
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="class_structure",
                    content=classes,
                    metadata={"file": str(file_path), "count": len(classes)},
                    timestamp="",
                    confidence=1.0
                ))

            if functions:
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="function_structure",
                    content=functions,
                    metadata={"file": str(file_path), "count": len(functions)},
                    timestamp="",
                    confidence=1.0
                ))

            if imports:
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="imports",
                    content=list(set(imports)),
                    metadata={"file": str(file_path), "count": len(set(imports))},
                    timestamp="",
                    confidence=1.0
                ))

        except Exception as e:
            logger.warning(f"[code_structure] Failed to analyze {file_path}: {e}")

        return evidence

    def _analyze_directory(self, dir_path: Path) -> List[Evidence]:
        """
        Analyze directory structure.
        """
        evidence = []

        try:
            py_files = list(dir_path.rglob("*.py"))

            if "__pycache__" not in str(dir_path):
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="directory_structure",
                    content={
                        "path": str(dir_path),
                        "py_file_count": len(py_files),
                        "has_init": (dir_path / "__init__.py").exists(),
                        "subdirs": [d.name for d in dir_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
                    },
                    metadata={"path": str(dir_path)},
                    timestamp="",
                    confidence=1.0
                ))

                for py_file in py_files[:20]:
                    evidence.extend(self._analyze_python_file(py_file))

        except Exception as e:
            logger.warning(f"[code_structure] Failed to analyze directory {dir_path}: {e}")

        return evidence
