#!/usr/bin/env python3
"""
Integration Flow Monitor - Detects broken data flows and architectural gaps.

Purpose:
    Analyze system architecture to detect integration issues that metrics/tests can't catch:
    - Orphaned queues (producers but no consumers)
    - Duplicate responsibilities (multiple components doing the same thing)
    - Missing wiring (calls to non-existent components)
    - Dead code (registered but never invoked)

Governance:
    - Tool-Integrity: Static analysis + runtime trace analysis
    - D-REAM-Allowed-Stack: Uses AST parsing, no external deps
    - Autonomy Level 2: Identifies issues, proposes fixes

Integration with Curiosity Core:
    Generates CuriosityQuestion objects for architectural anomalies
"""

import ast
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

try:
    from .curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus
    from .systemd_helpers import is_service_intentionally_disabled
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from curiosity_core import CuriosityQuestion, ActionClass, QuestionStatus
    from systemd_helpers import is_service_intentionally_disabled

logger = logging.getLogger(__name__)


@dataclass
class DataFlow:
    """Represents a data flow between components."""
    producer: str  # Component that creates/writes data
    consumer: str  # Component that reads/processes data
    channel: str   # Queue, file, method call, etc.
    channel_type: str  # 'queue', 'file', 'method', 'attribute'
    producer_file: str
    consumer_file: Optional[str]
    line_number: int


@dataclass
class ComponentResponsibility:
    """Represents what a component is responsible for."""
    component: str  # Class or module name
    responsibility: str  # What it does (e.g., "conversation state management")
    file_path: str
    evidence: List[str] = field(default_factory=list)  # Method names, attributes, etc.


class IntegrationFlowMonitor:
    """
    Detects architectural integration issues through static analysis.

    Analyzes:
        1. Orphaned queues - Data structures that fill but never drain
        2. Duplicate responsibilities - Multiple components doing same thing
        3. Data flow gaps - Producers without consumers, broken call chains
        4. Initialization gaps - Components used but never initialized
    """

    def __init__(self, src_root: Path = Path("/home/kloros/src")):
        """
        Initialize integration monitor.

        Parameters:
            src_root: Root directory of source code to analyze
        """
        self.src_root = src_root
        self.data_flows: List[DataFlow] = []
        self.responsibilities: List[ComponentResponsibility] = []

    def _infer_service_from_queue_name(self, queue_name: str) -> Optional[str]:
        """
        Map queue/attribute name to owning systemd service.

        D-REAM evolution queues are owned by kloros-dream.service.
        This mapping prevents false-positive investigations when D-REAM is disabled.

        Args:
            queue_name: Name of the queue/attribute (e.g., "episodes", "fitness_history")

        Returns:
            Service name (e.g., "kloros-dream.service") or None if no mapping

        Examples:
            >>> _infer_service_from_queue_name("episodes")
            "kloros-dream.service"

            >>> _infer_service_from_queue_name("fitness_history")
            "kloros-dream.service"

            >>> _infer_service_from_queue_name("unknown_queue")
            None
        """
        DREAM_QUEUES = {
            "episodes",
            "fitness_history",
            "phenotype_history",
            "mutation_history",
            "generations",
            "macro_traces",
            "mutations",
            "attempt_history",
            "episode_buffer",
            "genomes",
            "population",
            "parent_versions",
            "offspring",
            "elite_genomes",
            "fitness_scores",
            "evolution_stats",
            "convergence_history",
            "diversity_metrics",
            "evolution_history",
            "bracket_history",
            "buffer",
            "regimes",
            "safety_violations",
            "violations",
            "created_bridges",
            "data_flows",
            "playbook_deltas",
            "petri_reports",
            "responsibilities",
            "_streaming_audio_chunks",
            "tokenized_corpus",
            "worker_threads"
        }

        if queue_name in DREAM_QUEUES:
            return "kloros-dream.service"

        return None

    def generate_integration_questions(self) -> List[CuriosityQuestion]:
        """
        Generate curiosity questions from integration analysis.

        Returns:
            List of CuriosityQuestion objects for architectural issues
        """
        questions = []

        # Analyze data flows
        self._scan_data_flows()

        # Detect orphaned queues
        orphan_questions = self._detect_orphaned_queues()
        questions.extend(orphan_questions)

        # Detect duplicate responsibilities
        duplicate_questions = self._detect_duplicate_responsibilities()
        questions.extend(duplicate_questions)

        # Detect missing wiring
        wiring_questions = self._detect_missing_wiring()
        questions.extend(wiring_questions)

        # Detect initialization gaps
        init_questions = self._detect_initialization_gaps()
        questions.extend(init_questions)

        logger.info(f"[integration_monitor] Generated {len(questions)} integration questions")

        return questions

    def _scan_data_flows(self):
        """Scan source code for data flows between components."""
        self.data_flows = []
        self.responsibilities = []

        # Scan all Python files
        for py_file in self.src_root.rglob("*.py"):
            if "test_" in py_file.name or "__pycache__" in str(py_file):
                continue

            try:
                self._analyze_file(py_file)
            except Exception as e:
                logger.debug(f"[integration_monitor] Failed to analyze {py_file}: {e}")

    def _analyze_file(self, file_path: Path):
        """Analyze a single Python file for data flows and responsibilities."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.debug(f"[integration_monitor] Cannot read {file_path}: {e}")
            return

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            logger.debug(f"[integration_monitor] Syntax error in {file_path}")
            return

        # Analyze AST for patterns
        analyzer = FlowAnalyzer(file_path, source)
        analyzer.visit(tree)
        analyzer.finalize_flows()  # Finalize flows after traversal

        self.data_flows.extend(analyzer.flows)
        self.responsibilities.extend(analyzer.responsibilities)

    def _detect_orphaned_queues(self) -> List[CuriosityQuestion]:
        """
        Detect queues/lists that are populated but never consumed.

        Returns:
            List of questions about orphaned data structures
        """
        questions = []

        # Group flows by channel
        channels = defaultdict(lambda: {"producers": set(), "consumers": set()})

        for flow in self.data_flows:
            channels[flow.channel]["producers"].add((flow.producer, flow.producer_file))
            if flow.consumer:
                channels[flow.channel]["consumers"].add((flow.consumer, flow.consumer_file))

        # Find channels with producers but no consumers
        for channel, info in channels.items():
            if info["producers"] and not info["consumers"]:
                # Orphaned queue detected
                producers = ", ".join([p[0] for p in info["producers"]])
                producer_files = [p[1] for p in info["producers"]]

                # Check if owning service is intentionally disabled
                metadata = {}
                owning_service = self._infer_service_from_queue_name(channel)
                if owning_service and is_service_intentionally_disabled(owning_service):
                    metadata = {
                        "intentionally_disabled": True,
                        "reason": f"{owning_service} is disabled"
                    }
                    logger.info(
                        f"[integration_monitor] Skipping orphaned queue '{channel}' - "
                        f"owning service {owning_service} is intentionally disabled"
                    )

                q = CuriosityQuestion(
                    id=f"orphaned_queue_{channel}",
                    hypothesis=f"ORPHANED_QUEUE_{channel.upper()}",
                    question=(
                        f"Data structure '{channel}' is populated by {producers} "
                        f"but never consumed. Is this a broken integration? "
                        f"Should I find where it should be read?"
                    ),
                    evidence=[
                        f"Produced in: {', '.join(producer_files)}",
                        f"No consumers found in codebase",
                        f"Channel type: queue/list"
                    ],
                    action_class=ActionClass.PROPOSE_FIX,
                    autonomy=3,  # Level 3: Execute with approval
                    value_estimate=0.95,  # CRITICAL - architectural debt compounds
                    cost=0.2,  # LOW - automated code patching
                    status=QuestionStatus.READY,
                    capability_key=f"integration.{channel}",
                    metadata=metadata
                )
                questions.append(q)

        return questions

    def _detect_duplicate_responsibilities(self) -> List[CuriosityQuestion]:
        """
        Detect multiple components with overlapping responsibilities.

        Returns:
            List of questions about duplicate responsibilities
        """
        questions = []

        # Group responsibilities by semantic similarity
        responsibility_map = defaultdict(list)

        for resp in self.responsibilities:
            # Normalize responsibility description
            normalized = self._normalize_responsibility(resp.responsibility)
            responsibility_map[normalized].append(resp)

        # Find duplicates
        for responsibility, components in responsibility_map.items():
            if len(components) >= 2:
                # Duplicate responsibility detected
                component_names = [c.component for c in components]
                file_paths = [c.file_path for c in components]

                q = CuriosityQuestion(
                    id=f"duplicate_responsibility_{responsibility}",
                    hypothesis=f"DUPLICATE_{responsibility.upper().replace(' ', '_')}",
                    question=(
                        f"Multiple components handle '{responsibility}': "
                        f"{', '.join(component_names)}. "
                        f"Are they synchronized? Should I consolidate them?"
                    ),
                    evidence=[
                        f"Components: {', '.join(component_names)}",
                        f"Files: {', '.join(file_paths)}",
                        "Potential for state divergence"
                    ],
                    action_class=ActionClass.INVESTIGATE,
                    autonomy=2,  # Level 2: Just document, too risky to auto-consolidate
                    value_estimate=0.85,  # HIGH - duplication causes bugs
                    cost=0.4,  # Medium cost - requires review
                    status=QuestionStatus.READY,
                    capability_key=f"architecture.duplication.{responsibility}"
                )
                questions.append(q)

        return questions

    def _detect_missing_wiring(self) -> List[CuriosityQuestion]:
        """
        Detect method calls or attribute accesses to non-existent components.

        Returns:
            List of questions about missing wiring
        """
        questions = []

        # Pattern: self.component.method() but self.component is None or never initialized
        missing_wiring = self._find_uninitialized_attributes()

        for attr_name, usage_info in missing_wiring.items():
            q = CuriosityQuestion(
                id=f"missing_wiring_{attr_name}",
                hypothesis=f"UNINITIALIZED_COMPONENT_{attr_name.upper()}",
                question=(
                    f"Component '{attr_name}' is used in {usage_info['file']} "
                    f"but may not be initialized. "
                    f"Usage: {usage_info['usage']}. "
                    f"Should I add initialization in __init__?"
                ),
                evidence=[
                    f"Used at line {usage_info['line']}",
                    f"No initialization found",
                    f"May cause AttributeError at runtime"
                ],
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=3,  # Level 3: Add null check (low risk)
                value_estimate=0.92,  # CRITICAL - prevents crashes
                cost=0.15,  # VERY LOW - simple null check
                status=QuestionStatus.READY,
                capability_key=f"initialization.{attr_name}"
            )
            questions.append(q)

        return questions

    def _detect_initialization_gaps(self) -> List[CuriosityQuestion]:
        """
        Detect components that are conditionally initialized but unconditionally used.

        Pattern:
            if ALERT_SYSTEM_AVAILABLE:
                self.alert_manager = DreamAlertManager()

            # Later, without checking:
            self.alert_manager.notify_improvement_ready()

        Returns:
            List of questions about initialization gaps
        """
        questions = []

        # Scan for pattern: conditional init + unconditional usage
        init_gaps = self._find_conditional_initialization_gaps()

        for component, gap_info in init_gaps.items():
            q = CuriosityQuestion(
                id=f"init_gap_{component}",
                hypothesis=f"CONDITIONAL_INIT_GAP_{component.upper()}",
                question=(
                    f"Component '{component}' is conditionally initialized "
                    f"(if {gap_info['condition']}) but used unconditionally. "
                    f"Should I add null checks before usage?"
                ),
                evidence=[
                    f"Initialized in: {gap_info['init_file']} (conditional)",
                    f"Used in: {gap_info['usage_file']} (unconditional)",
                    "May cause AttributeError if condition is False"
                ],
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=2,
                value_estimate=0.85,
                cost=0.2,
                status=QuestionStatus.READY,
                capability_key=f"safety.{component}"
            )
            questions.append(q)

        return questions

    def _normalize_responsibility(self, responsibility: str) -> str:
        """Normalize responsibility description for comparison."""
        # Remove common words and normalize
        normalized = responsibility.lower()
        normalized = re.sub(r'\b(the|a|an|is|are|for|to|of|in)\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _find_uninitialized_attributes(self) -> Dict[str, Dict[str, Any]]:
        """
        Find attributes used but not initialized AND not safely guarded.

        Returns:
            Dict mapping attribute name to usage info
        """
        uninitialized = {}

        # This is a simplified heuristic - real implementation would use AST
        # For now, scan for known patterns in kloros_voice.py and other main files

        main_files = [
            self.src_root / "kloros_voice.py",
            self.src_root / "evolutionary_optimization.py",
            self.src_root / "kloros_idle_reflection.py"
        ]

        for file_path in main_files:
            if not file_path.exists():
                continue

            try:
                with open(file_path, 'r') as f:
                    source = f.read()
                    lines = source.split('\n')

                # Find attribute usage patterns
                for i, line in enumerate(lines, 1):
                    # Pattern: self.something.method() or self.something.attribute
                    match = re.search(r'self\.(\w+)\.(\w+)', line)
                    if match:
                        attr_name = match.group(1)
                        usage = match.group(2)

                        # Check if this attribute is initialized
                        # Handle both direct assignment and type-annotated assignment:
                        # self.attr = ...
                        # self.attr: Type = ...
                        init_pattern = rf'self\.{attr_name}\s*(?::\s*[^=]+)?\s*='
                        if not re.search(init_pattern, source):
                            # Not initialized - check if it's safely guarded
                            if self._is_safely_guarded(attr_name, i, lines):
                                # Has hasattr() guard - safe to use without initialization
                                continue

                            # Not initialized AND not guarded
                            if attr_name not in uninitialized:
                                uninitialized[attr_name] = {
                                    "file": str(file_path),
                                    "line": i,
                                    "usage": f"self.{attr_name}.{usage}()"
                                }
            except Exception as e:
                logger.debug(f"[integration_monitor] Error scanning {file_path}: {e}")

        return uninitialized

    def _is_safely_guarded(self, attr_name: str, line_num: int, lines: List[str]) -> bool:
        """
        Check if attribute usage is safely guarded with hasattr() checks.

        Args:
            attr_name: Name of the attribute to check
            line_num: 1-indexed line number where attribute is used
            lines: All lines of source code (0-indexed)

        Returns:
            True if usage is guarded, False otherwise
        """
        # Check current line for hasattr() guard
        current_line = lines[line_num - 1] if line_num - 1 < len(lines) else ""
        if f"hasattr(self, '{attr_name}')" in current_line:
            return True

        # Check previous 3 lines for hasattr() guard wrapping this usage
        for offset in range(1, 4):
            if line_num - offset < 1:
                break
            prev_line = lines[line_num - 1 - offset]
            if f"hasattr(self, '{attr_name}')" in prev_line:
                return True

        return False

    def _find_conditional_initialization_gaps(self) -> Dict[str, Dict[str, Any]]:
        """
        Find components with conditional initialization but unconditional usage.

        Returns:
            Dict mapping component name to gap info
        """
        gaps = {}

        # Scan main files for pattern
        main_files = [
            self.src_root / "kloros_voice.py",
            self.src_root / "evolutionary_optimization.py"
        ]

        for file_path in main_files:
            if not file_path.exists():
                continue

            try:
                with open(file_path, 'r') as f:
                    source = f.read()

                # Find conditional initialization pattern
                # Pattern: if CONDITION:\n    self.component = ...
                cond_init_pattern = r'if\s+(\w+):\s*\n\s+self\.(\w+)\s*='

                for match in re.finditer(cond_init_pattern, source):
                    condition = match.group(1)
                    component = match.group(2)

                    # Now check if this component is used without null checks
                    usage_pattern = rf'(?<!if\s+)(?<!if\s+not\s+)self\.{component}\.'
                    if re.search(usage_pattern, source):
                        gaps[component] = {
                            "condition": condition,
                            "init_file": str(file_path),
                            "usage_file": str(file_path)
                        }
            except Exception as e:
                logger.debug(f"[integration_monitor] Error scanning {file_path}: {e}")

        return gaps


class FlowAnalyzer(ast.NodeVisitor):
    """AST visitor that extracts data flows and component responsibilities."""

    def __init__(self, file_path: Path, source: str):
        self.file_path = file_path
        self.source = source
        self.flows: List[DataFlow] = []
        self.responsibilities: List[ComponentResponsibility] = []
        self.current_class = None
        self.mutated_attributes: Set[str] = set()
        self.pending_flows: List[tuple] = []

    def visit_ClassDef(self, node):
        """Visit class definition to identify responsibilities."""
        self.current_class = node.name

        # Extract docstring for responsibility
        docstring = ast.get_docstring(node)
        if docstring:
            # First line is usually the responsibility
            responsibility = docstring.split('\n')[0].strip()

            # Extract evidence from methods
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]

            self.responsibilities.append(ComponentResponsibility(
                component=node.name,
                responsibility=responsibility,
                file_path=str(self.file_path),
                evidence=methods[:5]  # First 5 methods as evidence
            ))

        self.generic_visit(node)
        self.current_class = None

    def visit_Assign(self, node):
        """Visit assignment to detect queue/list creation and population."""
        # Pattern: self.queue = []
        # Pattern: self.queue.append(item)

        if isinstance(node.targets[0], ast.Attribute):
            attr = node.targets[0]
            if isinstance(attr.value, ast.Name) and attr.value.id == 'self':
                # This is self.something = ...
                attr_name = attr.attr

                # Check if it's a list/queue
                if isinstance(node.value, ast.List):
                    # Defer DataFlow creation until after full traversal
                    # This allows us to check for mutations before deciding if config
                    self.pending_flows.append((attr_name, node))

        self.generic_visit(node)

    def visit_Subscript(self, node):
        """Visit subscript operations to detect array/queue access (internal consumption)."""
        # Pattern: self.queue[index], self.queue[-1], self.approach_history[-2]

        if isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == 'self':
                # This is self.something[index] - internal consumption
                channel_name = node.value.attr

                # Mark this channel as internally consumed
                self.flows.append(DataFlow(
                    producer=self.current_class or "unknown",
                    consumer=self.current_class or "internal",  # Same class consumes it
                    channel=channel_name,
                    channel_type="queue",
                    producer_file=str(self.file_path),
                    consumer_file=str(self.file_path),  # Same file
                    line_number=node.lineno
                ))

        self.generic_visit(node)

    def visit_Call(self, node):
        """Visit function calls to detect queue operations and method calls."""
        # Pattern: self.queue.append(item) - producer
        # Pattern: self.queue.pop() - consumer
        # Pattern: len(self.queue) - consumer
        # Pattern: self.alert_manager.notify_improvement_ready() - data flow

        # Check for len(self.something) - indicates internal consumption
        if isinstance(node.func, ast.Name) and node.func.id == 'len':
            if len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Attribute):
                    if isinstance(arg.value, ast.Name) and arg.value.id == 'self':
                        # len(self.queue) - internal consumption
                        channel_name = arg.attr
                        self.flows.append(DataFlow(
                            producer=self.current_class or "unknown",
                            consumer=self.current_class or "internal",
                            channel=channel_name,
                            channel_type="queue",
                            producer_file=str(self.file_path),
                            consumer_file=str(self.file_path),
                            line_number=node.lineno
                        ))

        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Attribute):
                # self.something.method()
                if isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == 'self':
                        component = node.func.value.attr
                        method = node.func.attr

                        # Track queue mutation operations
                        QUEUE_MUTATION_METHODS = {
                            'append', 'pop', 'extend', 'clear',
                            'insert', 'remove', 'popleft'
                        }
                        if method in QUEUE_MUTATION_METHODS:
                            self.mutated_attributes.add(component)

                        # Check for known data flow methods
                        if method in ['notify_improvement_ready', 'share_observation',
                                     'queue_reflection_insights', 'add_alert']:
                            self.flows.append(DataFlow(
                                producer=self.current_class or "unknown",
                                consumer=component,
                                channel=method,
                                channel_type="method",
                                producer_file=str(self.file_path),
                                consumer_file=None,  # Would need cross-file analysis
                                line_number=node.lineno
                            ))
            elif isinstance(node.func.value, ast.Name):
                if node.func.value.id == 'self':
                    # self.method() or self.queue.append()
                    method = node.func.attr

                    if method in ['append', 'put', 'add', 'enqueue']:
                        # Producer operation
                        pass  # Already captured in Assign
                    elif method in ['pop', 'get', 'poll', 'dequeue']:
                        # Consumer operation - mark existing flow
                        pass

        self.generic_visit(node)

    def _has_literal_values(self, node: ast.expr) -> bool:
        """
        Check if list/dict contains only literal values (not variables/calls).

        Returns True if all elements are constants/literals.
        """
        if isinstance(node, ast.List):
            # Check all elements are literals
            for elt in node.elts:
                if not isinstance(elt, (ast.Constant, ast.Str, ast.Num)):
                    return False
            return True

        elif isinstance(node, ast.Dict):
            # Check all keys and values are literals
            for k, v in zip(node.keys, node.values):
                if not isinstance(k, (ast.Constant, ast.Str, ast.Num)):
                    return False
                if not isinstance(v, (ast.Constant, ast.Str, ast.Num)):
                    return False
            return True

        return False

    def _is_configuration_data(self, attr_name: str, node: ast.Assign) -> bool:
        """
        Check if assignment is configuration data vs operational queue.

        Configuration = initialized with literals AND never mutated
        Operational queue = empty init OR has mutations

        Args:
            attr_name: Attribute name being assigned
            node: Assignment AST node

        Returns:
            True if this is configuration data (should skip)
        """
        if isinstance(node.value, (ast.List, ast.Dict)):
            has_literals = self._has_literal_values(node.value)
            is_mutated = attr_name in self.mutated_attributes

            # Config = literals AND not mutated
            return has_literals and not is_mutated

        return False

    def finalize_flows(self):
        """
        Create DataFlows after full traversal, filtering configuration data.

        Called after visit() completes to check mutations before creating flows.
        """
        config_filtered = 0

        for attr_name, node in self.pending_flows:
            if self._is_configuration_data(attr_name, node):
                config_filtered += 1
                logger.debug(f"[integration_monitor] Skipped config attribute: {attr_name}")
                continue

            # This is an operational queue, create DataFlow
            self.flows.append(DataFlow(
                producer=self.current_class or "unknown",
                consumer=None,
                channel=attr_name,
                channel_type="queue",
                producer_file=str(self.file_path),
                consumer_file=None,
                line_number=node.lineno
            ))

        if config_filtered > 0:
            logger.info(f"[integration_monitor] Filtered {config_filtered} configuration attributes in {self.file_path.name}")


def main():
    """Test integration flow monitor."""
    import sys

    logging.basicConfig(level=logging.INFO)

    monitor = IntegrationFlowMonitor()
    questions = monitor.generate_integration_questions()

    print(f"\n[IntegrationFlowMonitor] Generated {len(questions)} questions:\n")

    for i, q in enumerate(questions, 1):
        print(f"{i}. {q.question}")
        print(f"   Hypothesis: {q.hypothesis}")
        print(f"   Evidence: {q.evidence}")
        print(f"   Action: {q.action_class.value}")
        print(f"   Value: {q.value_estimate:.2f}, Cost: {q.cost:.2f}")
        print()

    # Write to JSON for inspection
    output_path = Path("/home/kloros/.kloros/integration_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "questions": [q.to_dict() for q in questions],
            "total": len(questions),
            "generated_at": "now"
        }, f, indent=2)

    print(f"[IntegrationFlowMonitor] Wrote analysis to {output_path}")

    return 0 if questions else 1


if __name__ == "__main__":
    sys.exit(main())
