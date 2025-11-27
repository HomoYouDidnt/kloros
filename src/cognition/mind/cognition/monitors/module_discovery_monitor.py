"""
Module Discovery Monitor - Capability registry gap detection.

Proactively scans /home/kloros/src for modules and compares against capability registry.
"""

import logging
import time
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
)

logger = logging.getLogger(__name__)


class ModuleDiscoveryMonitor:
    """
    Proactively scans /home/kloros/src for modules and compares against capability registry.

    Generates questions about:
    - Modules that exist but aren't in the registry
    - Modules with __init__.py suggesting they're complete
    - Modules with recent activity (mtime)
    - Knowledge base documents describing capabilities
    """

    def __init__(
        self,
        src_path: Path = Path("/home/kloros/src"),
        knowledge_base_path: Path = Path("/home/kloros/knowledge_base"),
        capability_yaml: Path = Path("/home/kloros/src/registry/capabilities.yaml"),
        semantic_store=None,
        prioritizer=None
    ):
        self.src_path = src_path
        self.knowledge_base_path = knowledge_base_path
        self.capability_yaml = capability_yaml
        self.semantic_store = semantic_store
        self.prioritizer = prioritizer
        self.known_capabilities = self._load_known_capabilities()

    def _load_known_capabilities(self) -> set:
        """Extract known capability keys from YAML."""
        known = set()
        try:
            with open(self.capability_yaml) as f:
                capabilities = yaml.safe_load(f)
                if capabilities:
                    for key in capabilities.keys():
                        known.add(key)
                        cap = capabilities[key]
                        if isinstance(cap, dict) and 'module' in cap:
                            module_name = cap['module'].split('.')[-1]
                            known.add(module_name)
        except Exception as e:
            logger.warning(f"[module_discovery] Failed to load capability registry: {e}")
        return known

    def scan_undiscovered_modules(self) -> List[Dict[str, Any]]:
        """Scan /home/kloros/src for modules not in capability registry."""
        undiscovered = []

        if not self.src_path.exists():
            return undiscovered

        for module_dir in self.src_path.iterdir():
            if not module_dir.is_dir():
                continue

            if module_dir.name.startswith('.') or module_dir.name in ['__pycache__', 'tests']:
                continue

            module_name = module_dir.name

            potential_keys = [
                module_name,
                f"module.{module_name}",
                f"tools.{module_name}",
                f"agent.{module_name}",
                f"reasoning.{module_name}",
                f"service.{module_name}"
            ]

            if not any(key in self.known_capabilities for key in potential_keys):
                init_file = module_dir / "__init__.py"
                has_init = init_file.exists()

                try:
                    mtime = module_dir.stat().st_mtime
                except:
                    mtime = 0

                py_files = list(module_dir.glob("*.py"))
                py_count = len(py_files)

                has_docs = (module_dir / "README.md").exists()

                if has_init or py_count >= 2 or has_docs:
                    undiscovered.append({
                        "module_name": module_name,
                        "path": str(module_dir),
                        "has_init": has_init,
                        "py_file_count": py_count,
                        "has_docs": has_docs,
                        "mtime": mtime
                    })

        return undiscovered

    def scan_knowledge_base_gaps(self) -> List[Dict[str, Any]]:
        """Scan knowledge base for documentation about capabilities not in registry."""
        gaps = []

        if not self.knowledge_base_path.exists():
            return gaps

        for md_file in self.knowledge_base_path.rglob("*.md"):
            try:
                content = md_file.read_text()
                if "capability" in content.lower() or "module" in content.lower():
                    gaps.append({
                        "doc_file": str(md_file.relative_to(self.knowledge_base_path)),
                        "path": str(md_file),
                        "mtime": md_file.stat().st_mtime
                    })
            except Exception as e:
                logger.debug(f"[module_discovery] Failed to read {md_file}: {e}")

        return gaps

    def generate_discovery_questions(self) -> List[CuriosityQuestion]:
        """Generate curiosity questions about undiscovered modules."""
        undiscovered = self.scan_undiscovered_modules()

        logger.info(f"[module_discovery] Found {len(undiscovered)} undiscovered modules in /src")

        candidate_questions = []

        for module_info in undiscovered:
            module_name = module_info["module_name"]

            value = 0.5

            if module_info["has_init"]:
                value += 0.1
            if module_info["has_docs"]:
                value += 0.1
            if module_info["py_file_count"] >= 3:
                value += 0.1

            age_days = (time.time() - module_info["mtime"]) / 86400
            if age_days < 30:
                value += 0.15

            if value < 0.6:
                continue

            hypothesis = f"UNDISCOVERED_MODULE_{module_name.upper()}"

            question = (
                f"I found an undiscovered module '{module_name}' in /src with "
                f"{module_info['py_file_count']} Python files. "
                f"What does it do, and should it be added to my capability registry?"
            )

            static_evidence = [
                f"path:{module_info['path']}",
                f"has_init:{module_info['has_init']}",
                f"py_files:{module_info['py_file_count']}",
                f"has_docs:{module_info['has_docs']}",
                f"age_days:{int(age_days)}"
            ]

            semantic_evidence = []
            if self.semantic_store:
                semantic_evidence = self.semantic_store.to_evidence_list(module_name)

            evidence = static_evidence + semantic_evidence

            q = CuriosityQuestion(
                id=f"discover.module.{module_name}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.INVESTIGATE,
                autonomy=3,
                value_estimate=min(value, 0.95),
                cost=0.15,
                status=QuestionStatus.READY,
                capability_key=f"undiscovered.{module_name}"
            )

            candidate_questions.append(q)

        candidate_questions.sort(key=lambda q: q.value_estimate, reverse=True)
        top_questions = candidate_questions[:5]

        emitted_count = 0
        if self.prioritizer is not None:
            for q in top_questions:
                self.prioritizer.prioritize_and_emit(q)
                emitted_count += 1

        logger.info(f"[module_discovery] Emitted {emitted_count} discovery questions via prioritizer")

        return top_questions if self.prioritizer is None else []
