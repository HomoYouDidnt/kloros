#!/usr/bin/env python3
"""
Integration Evidence Plugin - Analyzes how modules connect and integrate.
"""

import ast
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Set

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class IntegrationPlugin(EvidencePlugin):
    """
    Analyzes integration points between modules.

    Evidence types:
    - Import relationships (who imports what)
    - Signal emissions/subscriptions (ZMQ chemical bus)
    - API calls between modules
    - Shared data structures
    """

    @property
    def name(self) -> str:
        return "integration"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        integration_related = {
            "integration_analysis",
            "capability_discovery",
            "system_architecture"
        }

        keywords = ["connect", "integrate", "communicate", "signal", "import", "depend", "call"]

        return (
            investigation_type in integration_related or
            any(kw in question.lower() for kw in keywords)
        )

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        evidence = []

        module_paths = self._extract_module_paths(question, context)

        for module_path in module_paths:
            path = Path(module_path)

            if not path.exists():
                continue

            import_evidence = self._analyze_imports(path)
            if import_evidence:
                evidence.extend(import_evidence)

            signal_evidence = self._analyze_signals(path)
            if signal_evidence:
                evidence.extend(signal_evidence)

        return evidence

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        module_count = len(self._extract_module_paths(question, context))

        return {
            "time_estimate_seconds": module_count * 0.5,
            "token_cost": 0,
            "complexity": "medium"
        }

    def priority(self, investigation_type: str) -> int:
        if investigation_type == "integration_analysis":
            return 90
        return 60

    def _extract_module_paths(self, question: str, context: Dict[str, Any]) -> List[str]:
        """
        Extract module paths from question and context.
        """
        paths = set()

        existing_evidence = context.get("existing_evidence", [])
        for ev in existing_evidence:
            if ev.evidence_type in {"directory_structure", "module_docstring"}:
                path = ev.metadata.get("path") or ev.metadata.get("file")
                if path:
                    paths.add(str(Path(path).parent))

        import re
        module_pattern = r'/home/kloros/src/[\w/\-]+'
        found_paths = re.findall(module_pattern, question)
        paths.update(found_paths)

        if not paths:
            paths.add("/home/kloros/src")

        return list(paths)

    def _analyze_imports(self, module_path: Path) -> List[Evidence]:
        """
        Analyze import relationships for a module.
        """
        evidence = []

        if not module_path.is_dir():
            module_path = module_path.parent

        try:
            py_files = list(module_path.rglob("*.py"))

            all_imports = set()
            internal_imports = set()
            external_imports = set()

            for py_file in py_files[:50]:
                try:
                    content = py_file.read_text(errors='ignore')
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                all_imports.add(alias.name)
                                if alias.name.startswith("kloros") or alias.name.startswith("src"):
                                    internal_imports.add(alias.name)
                                else:
                                    external_imports.add(alias.name)

                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                all_imports.add(node.module)
                                if node.module.startswith("kloros") or node.module.startswith("src"):
                                    internal_imports.add(node.module)
                                else:
                                    external_imports.add(node.module)

                except Exception as e:
                    logger.debug(f"[integration] Failed to parse {py_file}: {e}")

            if all_imports:
                evidence.append(Evidence(
                    source=self.name,
                    evidence_type="import_relationships",
                    content={
                        "all_imports": sorted(list(all_imports))[:50],
                        "internal_imports": sorted(list(internal_imports))[:30],
                        "external_imports": sorted(list(external_imports))[:30],
                        "total_count": len(all_imports),
                        "internal_count": len(internal_imports),
                        "external_count": len(external_imports)
                    },
                    metadata={"module_path": str(module_path)},
                    timestamp="",
                    confidence=0.95
                ))

        except Exception as e:
            logger.warning(f"[integration] Failed to analyze imports for {module_path}: {e}")

        return evidence

    def _analyze_signals(self, module_path: Path) -> List[Evidence]:
        """
        Analyze signal emissions and subscriptions (ZMQ chemical bus).
        """
        evidence = []

        if not module_path.is_dir():
            module_path = module_path.parent

        try:
            result = subprocess.run(
                ["grep", "-r", "-E", "(publish|subscribe|ChemicalSignal|emit_signal)", str(module_path)],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                signal_lines = result.stdout.strip().splitlines()[:50]

                publishes = [l for l in signal_lines if "publish" in l.lower() or "emit" in l.lower()]
                subscribes = [l for l in signal_lines if "subscribe" in l.lower()]

                if publishes or subscribes:
                    evidence.append(Evidence(
                        source=self.name,
                        evidence_type="signal_integration",
                        content={
                            "publishes": publishes[:20],
                            "subscribes": subscribes[:20],
                            "publish_count": len(publishes),
                            "subscribe_count": len(subscribes)
                        },
                        metadata={"module_path": str(module_path)},
                        timestamp="",
                        confidence=0.8
                    ))

        except subprocess.TimeoutExpired:
            logger.warning(f"[integration] Signal analysis timed out for {module_path}")
        except Exception as e:
            logger.warning(f"[integration] Failed to analyze signals for {module_path}: {e}")

        return evidence
