#!/usr/bin/env python3
"""
Experimentation Evidence Plugin - Gathers evidence through runtime testing.
"""

import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class ExperimentationPlugin(EvidencePlugin):
    """
    Gathers evidence through runtime experimentation and testing.

    Use when static analysis reaches its limits and runtime testing is needed.

    Evidence types:
    - Code execution results
    - Function call outcomes
    - Import tests (can module be imported?)
    - Simple integration tests
    """

    @property
    def name(self) -> str:
        return "experimentation"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        existing_evidence = context.get("existing_evidence", [])

        has_code_structure = any(
            ev.evidence_type in {"class_structure", "function_structure", "directory_structure"}
            for ev in existing_evidence
        )

        keywords = ["test", "run", "execute", "try", "experiment", "does it work"]

        return (
            has_code_structure and
            any(kw in question.lower() for kw in keywords)
        )

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        evidence = []

        existing_evidence = context.get("existing_evidence", [])

        for ev in existing_evidence:
            if ev.evidence_type == "directory_structure":
                module_path = ev.content.get("path")
                if module_path and ev.content.get("has_init"):
                    import_evidence = self._test_import(module_path)
                    if import_evidence:
                        evidence.append(import_evidence)

            elif ev.evidence_type == "function_structure":
                file_path = ev.metadata.get("file")
                if file_path:
                    for func_info in ev.content:
                        if func_info.get("args") is not None and len(func_info["args"]) == 0:
                            func_evidence = self._test_function_call(file_path, func_info["name"])
                            if func_evidence:
                                evidence.append(func_evidence)
                                break

        return evidence[:5]

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "time_estimate_seconds": 3.0,
            "token_cost": 0,
            "complexity": "high"
        }

    def priority(self, investigation_type: str) -> int:
        return 30

    def _test_import(self, module_path: str) -> Evidence:
        """
        Test if a module can be imported successfully.
        """
        try:
            path = Path(module_path)
            if not path.exists() or not path.is_dir():
                return None

            if "/src/" not in str(path):
                return None

            module_dotted = str(path).split("/src/")[1].replace("/", ".")

            test_script = f"""
import sys
sys.path.insert(0, '/home/kloros/src')

try:
    import {module_dotted}
    print("IMPORT_SUCCESS")
    print(f"Module location: {{getattr({module_dotted}, '__file__', 'unknown')}}")
    print(f"Module attributes: {{', '.join([a for a in dir({module_dotted}) if not a.startswith('_')])[:500]}}")
except Exception as e:
    print(f"IMPORT_FAILED: {{e}}")
"""

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(test_script)
                temp_file = f.name

            result = subprocess.run(
                ["python3", temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            Path(temp_file).unlink()

            success = "IMPORT_SUCCESS" in result.stdout

            return Evidence(
                source=self.name,
                evidence_type="import_test",
                content={
                    "module": module_dotted,
                    "success": success,
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip() if result.stderr else None
                },
                metadata={"module_path": module_path},
                timestamp="",
                confidence=1.0 if success else 0.5
            )

        except Exception as e:
            logger.warning(f"[experimentation] Import test failed for {module_path}: {e}")
            return None

    def _test_function_call(self, file_path: str, function_name: str) -> Evidence:
        """
        Test calling a zero-argument function to see what it returns.
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None

            if "/src/" not in str(path):
                return None

            module_dotted = str(path).replace(".py", "").split("/src/")[1].replace("/", ".")

            test_script = f"""
import sys
sys.path.insert(0, '/home/kloros/src')

try:
    from {module_dotted} import {function_name}
    result = {function_name}()
    print(f"CALL_SUCCESS")
    print(f"Return type: {{type(result).__name__}}")
    print(f"Return value: {{str(result)[:200]}}")
except Exception as e:
    print(f"CALL_FAILED: {{e}}")
"""

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(test_script)
                temp_file = f.name

            result = subprocess.run(
                ["python3", temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            Path(temp_file).unlink()

            success = "CALL_SUCCESS" in result.stdout

            return Evidence(
                source=self.name,
                evidence_type="function_call_test",
                content={
                    "function": function_name,
                    "success": success,
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip() if result.stderr else None
                },
                metadata={"file_path": file_path},
                timestamp="",
                confidence=0.9 if success else 0.4
            )

        except Exception as e:
            logger.warning(f"[experimentation] Function call test failed for {function_name}: {e}")
            return None
