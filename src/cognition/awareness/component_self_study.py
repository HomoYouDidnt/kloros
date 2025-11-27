"""
Component Self-Study System - KLoROS learns about herself proactively.

Implements continuous self-exploration where KLoROS:
1. Studies her own components (modules, tools, services, configs)
2. Builds deep understanding of how/why things work
3. Identifies improvement opportunities
4. Proposes optimizations for D-REAM testing

Aligned with KLoROS-Prime doctrine: Precision, Self-Consistency, Evolution.
"""

import os
import ast
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from src.orchestration.core.umn_bus import UMNPub as ChemPub


@dataclass
class ComponentKnowledge:
    """Knowledge about a single component."""
    component_id: str
    component_type: str  # module|tool|service|config|model|pipeline
    file_path: Optional[str]
    last_studied_at: int
    study_depth: int  # 0=discovered, 1=basic, 2=detailed, 3=mastered

    purpose: str
    capabilities: List[str]
    dependencies: List[str]
    config_params: Dict[str, Any]

    usage_examples: str
    usage_count: int
    last_used_at: int

    interesting_findings: str
    potential_improvements: str
    notes: str


class ComponentSelfStudy:
    """
    Proactive component learning system.

    KLoROS systematically studies her own architecture, building
    deep understanding and identifying improvement opportunities.
    """

    def __init__(self, kloros_instance=None):
        """Initialize self-study system."""
        self.kloros = kloros_instance
        self.db_path = Path.home() / ".kloros" / "knowledge.db"
        self.base_path = Path("/home/kloros")

        # Ensure database exists
        self._init_database()

        # Initialize ChemPub for emitting learning signals
        self.chem_pub = ChemPub()

        # Study configuration
        self.enabled = int(os.getenv("KLR_ENABLE_SELF_STUDY", "1"))
        self.target_depth = int(os.getenv("KLR_STUDY_DEPTH", "2"))  # 1=basic, 2=detailed, 3=mastered
        self.study_time_budget_ms = int(os.getenv("KLR_STUDY_TIME_BUDGET_MS", "5000"))  # 5 seconds max

    def _init_database(self) -> None:
        """Initialize knowledge database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS component_knowledge (
                component_id TEXT PRIMARY KEY,
                component_type TEXT,
                file_path TEXT,
                last_studied_at INTEGER,
                study_depth INTEGER DEFAULT 0,

                purpose TEXT,
                capabilities TEXT,
                dependencies TEXT,
                config_params TEXT,

                usage_examples TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at INTEGER,

                interesting_findings TEXT,
                potential_improvements TEXT,
                notes TEXT
            )
        """)
        conn.commit()
        conn.close()

    def perform_study_cycle(self) -> Dict[str, Any]:
        """
        Execute one self-study cycle.

        Returns:
            Dict with study results and insights
        """
        if not self.enabled:
            return {"status": "disabled"}

        start_time = time.time()

        # Select component to study
        component_id = self._select_next_component()
        if not component_id:
            return {"status": "no_components", "message": "Component discovery needed"}

        print(f"[self_study] Studying component: {component_id}")

        # Perform deep dive
        knowledge = self._study_component(component_id)

        # Store knowledge
        self._store_knowledge(knowledge)

        # Analyze for improvements
        improvements = self._analyze_for_improvements(knowledge)

        # Generate insight
        insight = self._generate_study_insight(knowledge, improvements)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "status": "completed",
            "component_id": component_id,
            "component_type": knowledge.component_type,
            "study_depth": knowledge.study_depth,
            "improvements_found": len(improvements),
            "insight": insight,
            "elapsed_ms": elapsed_ms
        }

    def _select_next_component(self) -> Optional[str]:
        """
        Select next component to study using priority system.

        Priority:
        1. Never studied (study_depth=0)
        2. Least recently studied
        3. High usage but low understanding
        4. Random exploration (10% of time)

        Returns:
            Component ID to study, or None
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check for unstudied components
        cursor.execute("""
            SELECT component_id FROM component_knowledge
            WHERE study_depth = 0
            ORDER BY RANDOM()
            LIMIT 1
        """)
        result = cursor.fetchone()

        if result:
            conn.close()
            return result[0]

        # Find least recently studied that needs more depth
        cursor.execute("""
            SELECT component_id FROM component_knowledge
            WHERE study_depth < ?
            ORDER BY last_studied_at ASC
            LIMIT 1
        """, (self.target_depth,))
        result = cursor.fetchone()

        conn.close()

        if result:
            return result[0]

        # If no components in DB, discover some
        self._discover_components()

        return self._select_next_component()  # Retry after discovery

    def _discover_components(self) -> int:
        """
        Discover components in KLoROS codebase.

        Returns:
            Number of components discovered
        """
        discovered = 0
        conn = sqlite3.connect(str(self.db_path))

        # Discover Python modules
        src_path = self.base_path / "src"
        if src_path.exists():
            for py_file in src_path.rglob("*.py"):
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue

                component_id = f"module:{py_file.relative_to(src_path)}"

                # Check if already discovered
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM component_knowledge WHERE component_id = ?", (component_id,))
                if cursor.fetchone():
                    continue

                # Add to database
                conn.execute("""
                    INSERT INTO component_knowledge (
                        component_id, component_type, file_path, last_studied_at,
                        study_depth, purpose, capabilities, dependencies, config_params,
                        usage_examples, usage_count, last_used_at,
                        interesting_findings, potential_improvements, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    component_id, "module", str(py_file), 0, 0,
                    "", "[]", "[]", "{}",
                    "", 0, 0,
                    "", "", ""
                ))
                discovered += 1

                # Limit discovery per cycle
                if discovered >= 10:
                    break

        conn.commit()
        conn.close()

        print(f"[self_study] Discovered {discovered} new components")
        return discovered

    def _study_component(self, component_id: str) -> ComponentKnowledge:
        """
        Deeply study a component.

        Args:
            component_id: Component to study

        Returns:
            ComponentKnowledge with findings
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Get current knowledge
        cursor.execute("SELECT * FROM component_knowledge WHERE component_id = ?", (component_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        component_type = row[1]
        file_path = row[2]
        current_depth = row[4]

        # Determine new study depth (increment by 1, max 3)
        new_depth = min(current_depth + 1, 3)

        # Study based on type
        if component_type == "module" and file_path:
            return self._study_module(component_id, file_path, new_depth)

        # Fallback: basic study
        return ComponentKnowledge(
            component_id=component_id,
            component_type=component_type,
            file_path=file_path,
            last_studied_at=int(time.time()),
            study_depth=new_depth,
            purpose="Unknown component type",
            capabilities=[],
            dependencies=[],
            config_params={},
            usage_examples="",
            usage_count=0,
            last_used_at=0,
            interesting_findings="",
            potential_improvements="",
            notes=""
        )

    def _study_module(self, component_id: str, file_path: str, depth: int) -> ComponentKnowledge:
        """
        Study a Python module using AST analysis.

        Args:
            component_id: Module ID
            file_path: Path to module file
            depth: Study depth level

        Returns:
            ComponentKnowledge with module analysis
        """
        try:
            with open(file_path, 'r') as f:
                source = f.read()

            tree = ast.parse(source)

            # Extract module structure
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and not node.name.startswith('_')]
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            # Extract docstring (module purpose)
            purpose = ast.get_docstring(tree) or "No docstring found"
            purpose = purpose.split('\n')[0][:200]  # First line, max 200 chars

            # Build capabilities list
            capabilities = []
            if classes:
                capabilities.append(f"{len(classes)} classes: {', '.join(classes[:3])}")
            if functions:
                capabilities.append(f"{len(functions)} functions: {', '.join(functions[:5])}")

            # Identify config parameters (look for os.getenv calls)
            config_params = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        if node.func.value.id == 'os' and node.func.attr == 'getenv':
                            if node.args and isinstance(node.args[0], ast.Constant):
                                param_name = node.args[0].value
                                default_value = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else None
                                config_params[param_name] = default_value

            # Interesting findings
            findings = []
            if len(classes) > 5:
                findings.append(f"Complex module with {len(classes)} classes")
            if "TODO" in source or "FIXME" in source:
                findings.append("Contains TODO/FIXME comments - potential improvements noted")
            if config_params:
                findings.append(f"Uses {len(config_params)} configuration parameters")

            interesting_findings = "; ".join(findings) if findings else "Standard module structure"

            # Potential improvements
            improvements = []
            if not ast.get_docstring(tree):
                improvements.append("Add module docstring for clarity")
            if len(functions) > 20:
                improvements.append("Consider splitting into smaller modules")
            if "TODO" in source:
                improvements.append("Address TODO items in code")

            potential_improvements = "; ".join(improvements) if improvements else "Well-structured module"

            return ComponentKnowledge(
                component_id=component_id,
                component_type="module",
                file_path=file_path,
                last_studied_at=int(time.time()),
                study_depth=depth,
                purpose=purpose,
                capabilities=capabilities,
                dependencies=list(set(imports))[:10],  # Top 10 unique imports
                config_params=config_params,
                usage_examples="",  # TODO: Extract from docstrings/tests
                usage_count=0,
                last_used_at=0,
                interesting_findings=interesting_findings,
                potential_improvements=potential_improvements,
                notes=f"Lines: {len(source.splitlines())}, Classes: {len(classes)}, Functions: {len(functions)}"
            )

        except Exception as e:
            print(f"[self_study] Error studying module {file_path}: {e}")
            return ComponentKnowledge(
                component_id=component_id,
                component_type="module",
                file_path=file_path,
                last_studied_at=int(time.time()),
                study_depth=depth,
                purpose=f"Error analyzing: {e}",
                capabilities=[],
                dependencies=[],
                config_params={},
                usage_examples="",
                usage_count=0,
                last_used_at=0,
                interesting_findings="",
                potential_improvements="",
                notes=""
            )

    def _store_knowledge(self, knowledge: ComponentKnowledge) -> None:
        """Store component knowledge in database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE component_knowledge SET
                component_type = ?,
                file_path = ?,
                last_studied_at = ?,
                study_depth = ?,
                purpose = ?,
                capabilities = ?,
                dependencies = ?,
                config_params = ?,
                usage_examples = ?,
                usage_count = ?,
                last_used_at = ?,
                interesting_findings = ?,
                potential_improvements = ?,
                notes = ?
            WHERE component_id = ?
        """, (
            knowledge.component_type,
            knowledge.file_path,
            knowledge.last_studied_at,
            knowledge.study_depth,
            knowledge.purpose,
            json.dumps(knowledge.capabilities),
            json.dumps(knowledge.dependencies),
            json.dumps(knowledge.config_params),
            knowledge.usage_examples,
            knowledge.usage_count,
            knowledge.last_used_at,
            knowledge.interesting_findings,
            knowledge.potential_improvements,
            knowledge.notes,
            knowledge.component_id
        ))
        conn.commit()
        conn.close()

        self._emit_learning_completed(knowledge)

    def _emit_learning_completed(self, knowledge: ComponentKnowledge) -> None:
        """
        Emit LEARNING_COMPLETED signal via ChemBus.

        This enables the study-memory bridge to capture learning events
        and integrate them into episodic memory.
        """
        intensity = 1.0 + (knowledge.study_depth * 0.5)

        facts = {
            "source": "component_study",
            "component_id": knowledge.component_id,
            "study_depth": knowledge.study_depth,
            "component_type": knowledge.component_type,
            "file_path": knowledge.file_path,
            "studied_at": float(knowledge.last_studied_at),
            "purpose": knowledge.purpose,
            "capabilities": knowledge.capabilities,
            "dependencies": knowledge.dependencies,
            "config_params": knowledge.config_params,
            "usage_examples": knowledge.usage_examples,
            "usage_count": knowledge.usage_count,
            "last_used_at": knowledge.last_used_at,
            "interesting_findings": knowledge.interesting_findings,
            "potential_improvements": knowledge.potential_improvements,
            "notes": knowledge.notes
        }

        self.chem_pub.emit(
            signal="LEARNING_COMPLETED",
            ecosystem="introspection",
            intensity=intensity,
            facts=facts
        )

    def _analyze_for_improvements(self, knowledge: ComponentKnowledge) -> List[Dict[str, Any]]:
        """
        Analyze component for improvement opportunities.

        Args:
            knowledge: Component knowledge

        Returns:
            List of improvement proposals
        """
        improvements = []

        # Parse existing potential improvements
        if knowledge.potential_improvements:
            for improvement in knowledge.potential_improvements.split(';'):
                improvement = improvement.strip()
                if improvement:
                    improvements.append({
                        "type": "code_quality",
                        "description": improvement,
                        "confidence": 0.7,
                        "effort": "low",
                        "impact": "medium"
                    })

        # Config optimization opportunities
        if knowledge.config_params:
            for param, default in knowledge.config_params.items():
                # Check if parameter is documented
                if param.startswith("KLR_") and default is not None:
                    improvements.append({
                        "type": "config_optimization",
                        "description": f"Test different values for {param} (current default: {default})",
                        "confidence": 0.6,
                        "effort": "low",
                        "impact": "medium",
                        "d_ream_candidate": True,
                        "param_name": param,
                        "current_value": default
                    })

        return improvements

    def _generate_study_insight(self, knowledge: ComponentKnowledge, improvements: List[Dict]) -> Dict[str, Any]:
        """
        Generate user-facing insight from study results.

        Args:
            knowledge: Component knowledge
            improvements: Improvement opportunities

        Returns:
            Insight dict for reflection system
        """
        component_name = knowledge.component_id.split(':')[-1]

        # Build insight message
        if knowledge.study_depth == 1:
            title = f"Discovered: {component_name}"
            content = f"I've started studying {component_name}. {knowledge.purpose[:150]}"
        elif knowledge.study_depth == 2:
            title = f"Understanding: {component_name}"
            content = f"I've analyzed {component_name} in detail. "
            if knowledge.capabilities:
                content += f"It provides: {', '.join(knowledge.capabilities[:2])}. "
            if knowledge.interesting_findings:
                content += knowledge.interesting_findings
        else:  # depth 3
            title = f"Mastered: {component_name}"
            content = f"I've fully mastered {component_name}. "
            if improvements:
                content += f"I've identified {len(improvements)} potential improvements. "
                content += f"For example: {improvements[0]['description']}"
            else:
                content += "The component is well-optimized."

        # Add improvement question
        if improvements:
            d_ream_eligible = [imp for imp in improvements if imp.get('d_ream_candidate')]
            if d_ream_eligible:
                content += f" Should I test these optimizations with D-REAM?"

        return {
            "title": title,
            "content": content,
            "phase": 6,  # Self-study phase
            "type": "self_study",
            "confidence": 0.8,
            "keywords": [component_name, "self-study", "understanding"],
            "improvements": improvements
        }

    def get_study_statistics(self) -> Dict[str, Any]:
        """Get self-study statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM component_knowledge")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM component_knowledge WHERE study_depth >= 1")
        studied = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM component_knowledge WHERE study_depth >= 2")
        detailed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM component_knowledge WHERE study_depth >= 3")
        mastered = cursor.fetchone()[0]

        conn.close()

        return {
            "total_components": total,
            "studied": studied,
            "detailed_understanding": detailed,
            "mastered": mastered,
            "unstudied": total - studied,
            "progress_percent": int((studied / total * 100) if total > 0 else 0)
        }
