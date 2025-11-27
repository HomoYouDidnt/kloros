#!/usr/bin/env python3

import ast
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from src.orchestration.daemons.base_streaming_daemon import BaseStreamingDaemon

try:
    from src.orchestration.core.umn_bus import UMNPub
except ImportError:
    UMNPub = None

logger = logging.getLogger(__name__)


class IntegrationMonitorDaemon(BaseStreamingDaemon):

    def __init__(
        self,
        watch_path: Path = Path("/home/kloros/src"),
        state_file: Path = Path("/home/kloros/.kloros/integration_monitor_state.json"),
        max_queue_size: int = 1000,
        max_workers: int = 2,
        max_cache_size: int = 500
    ):
        super().__init__(
            watch_path=watch_path,
            max_queue_size=max_queue_size,
            max_workers=max_workers,
            max_cache_size=max_cache_size
        )

        self.state_file = state_file
        self.file_hashes: Dict[str, str] = {}
        self.data_flows: Dict[str, Dict[str, List]] = defaultdict(
            lambda: {"producers": [], "consumers": []}
        )
        self.chem_pub = None

        self.load_state()

    def process_file_event(self, event_type: str, file_path: Path):
        file_path_str = str(file_path)

        if event_type == 'delete':
            if file_path_str in self.file_hashes:
                del self.file_hashes[file_path_str]
            logger.debug(f"[integration_monitor] File deleted: {file_path}")
            return

        if not file_path.exists():
            return

        file_changed = self._has_file_changed(file_path)

        if not file_changed:
            logger.debug(f"[integration_monitor] File unchanged, skipping: {file_path}")
            return

        logger.info(f"[integration_monitor] Analyzing file: {file_path}")

        flows = self._extract_data_flows(file_path)

        for flow in flows:
            channel = flow['channel']
            producer_info = (flow['producer'], flow['producer_file'])

            if producer_info not in self.data_flows[channel]['producers']:
                self.data_flows[channel]['producers'].append(producer_info)

            if flow.get('consumer'):
                consumer_info = (flow['consumer'], flow.get('consumer_file', ''))
                if consumer_info not in self.data_flows[channel]['consumers']:
                    self.data_flows[channel]['consumers'].append(consumer_info)

        orphaned = self._detect_orphaned_queues()
        missing_wiring = self._detect_missing_wiring()

        all_questions = orphaned + missing_wiring

        if all_questions:
            logger.info(f"[integration_monitor] Detected {len(all_questions)} integration issues")
            self._emit_questions_to_umn(all_questions)
        else:
            logger.debug(f"[integration_monitor] No issues found in {file_path}")

        self._evict_cache_if_needed()

    def _compute_file_hash(self, file_path: Path) -> str:
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.debug(f"[integration_monitor] Cannot hash {file_path}: {e}")
            return ""

    def _has_file_changed(self, file_path: Path) -> bool:
        file_path_str = str(file_path)
        current_hash = self._compute_file_hash(file_path)

        if not current_hash:
            return False

        previous_hash = self.file_hashes.get(file_path_str)

        if previous_hash == current_hash:
            return False

        self.file_hashes[file_path_str] = current_hash
        return True

    def _extract_data_flows(self, file_path: Path) -> List[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.debug(f"[integration_monitor] Cannot read {file_path}: {e}")
            return []

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            logger.debug(f"[integration_monitor] Syntax error in {file_path}: {e}")
            return []

        analyzer = FlowAnalyzer(file_path, source)
        analyzer.visit(tree)
        analyzer.finalize_flows()

        return analyzer.flows

    def _detect_orphaned_queues(self) -> List[Dict[str, Any]]:
        orphaned = []

        for channel, info in self.data_flows.items():
            if info['producers'] and not info['consumers']:
                producers_str = ", ".join([p[0] for p in info['producers']])
                producer_files = [p[1] for p in info['producers']]

                orphaned.append({
                    'id': f'orphaned_queue_{channel}',
                    'channel': channel,
                    'producers': producers_str,
                    'question': (
                        f"Data structure '{channel}' is populated by {producers_str} "
                        f"but never consumed. Is this a broken integration?"
                    ),
                    'evidence': [
                        f"Produced in: {', '.join(producer_files)}",
                        "No consumers found in codebase",
                        "Channel type: queue/list"
                    ]
                })

        return orphaned

    def _detect_missing_wiring(self) -> List[Dict[str, Any]]:
        missing = []

        for file_path_str, file_hash in list(self.file_hashes.items()):
            file_path = Path(file_path_str)

            if not file_path.exists():
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                    tree = ast.parse(source, filename=str(file_path))
            except Exception:
                continue

            visitor = MissingWiringVisitor(file_path)
            visitor.visit(tree)

            for attr_name, usage_info in visitor.uninitialized.items():
                missing.append({
                    'id': f'missing_wiring_{attr_name}_{file_path.stem}',
                    'attribute': attr_name,
                    'file': str(file_path),
                    'question': (
                        f"Component '{attr_name}' is used in {file_path.name} "
                        f"but may not be initialized. "
                        f"Usage: {usage_info['usage']}. "
                        f"Should initialization be added?"
                    ),
                    'evidence': [
                        f"Used at line {usage_info['line']}",
                        "No initialization found",
                        "May cause AttributeError at runtime"
                    ]
                })

        return missing

    def _emit_questions_to_umn(self, questions: List[Dict[str, Any]]):
        if not UMNPub:
            logger.warning("[integration_monitor] UMN not available, skipping emission")
            return

        if not self.chem_pub:
            try:
                self.chem_pub = UMNPub()
            except Exception as e:
                logger.error(f"[integration_monitor] Failed to create UMNPub: {e}")
                return

        for q in questions:
            try:
                self.chem_pub.emit(
                    signal="curiosity.integration_question",
                    ecosystem="curiosity",
                    intensity=0.95,
                    facts={
                        'question_id': q['id'],
                        'question': q['question'],
                        'evidence': q['evidence'],
                        'timestamp': time.time()
                    }
                )
                logger.info(f"[integration_monitor] Emitted question: {q['id']}")

            except Exception as e:
                logger.error(f"[integration_monitor] Failed to emit question {q['id']}: {e}")

    def save_state(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                'file_hashes': self.file_hashes,
                'data_flows': dict(self.data_flows),
                'timestamp': time.time()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f)

            logger.info(f"[integration_monitor] Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"[integration_monitor] Failed to save state: {e}")

    def load_state(self):
        if not self.state_file.exists():
            logger.info("[integration_monitor] No previous state found, starting fresh")
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.file_hashes = state.get('file_hashes', {})
            self.data_flows = defaultdict(
                lambda: {"producers": [], "consumers": []},
                state.get('data_flows', {})
            )

            logger.info(
                f"[integration_monitor] Loaded state: "
                f"{len(self.file_hashes)} files, {len(self.data_flows)} flows"
            )

        except Exception as e:
            logger.error(f"[integration_monitor] Failed to load state: {e}")


class FlowAnalyzer(ast.NodeVisitor):

    def __init__(self, file_path: Path, source: str):
        self.file_path = file_path
        self.source = source
        self.flows: List[Dict[str, Any]] = []
        self.current_class = None
        self.mutated_attributes: Set[str] = set()
        self.pending_flows: List[tuple] = []

    def visit_ClassDef(self, node):
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_Assign(self, node):
        if isinstance(node.targets[0], ast.Attribute):
            attr = node.targets[0]
            if isinstance(attr.value, ast.Name) and attr.value.id == 'self':
                attr_name = attr.attr

                if isinstance(node.value, ast.List):
                    self.pending_flows.append((attr_name, node, self.current_class))

        self.generic_visit(node)

    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == 'self':
                channel_name = node.value.attr

                self.flows.append({
                    'producer': self.current_class or "unknown",
                    'consumer': self.current_class or "internal",
                    'channel': channel_name,
                    'channel_type': "queue",
                    'producer_file': str(self.file_path),
                    'consumer_file': str(self.file_path),
                    'line_number': node.lineno
                })

        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'len':
            if len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Attribute):
                    if isinstance(arg.value, ast.Name) and arg.value.id == 'self':
                        channel_name = arg.attr
                        self.flows.append({
                            'producer': self.current_class or "unknown",
                            'consumer': self.current_class or "internal",
                            'channel': channel_name,
                            'channel_type': "queue",
                            'producer_file': str(self.file_path),
                            'consumer_file': str(self.file_path),
                            'line_number': node.lineno
                        })

        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Attribute):
                if isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == 'self':
                        component = node.func.value.attr
                        method = node.func.attr

                        QUEUE_MUTATION_METHODS = {
                            'append', 'pop', 'extend', 'clear',
                            'insert', 'remove', 'popleft'
                        }
                        if method in QUEUE_MUTATION_METHODS:
                            self.mutated_attributes.add(component)

        self.generic_visit(node)

    def _has_literal_values(self, node: ast.expr) -> bool:
        if isinstance(node, ast.List):
            for elt in node.elts:
                if not isinstance(elt, (ast.Constant, ast.Str, ast.Num)):
                    return False
            return True

        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if not isinstance(k, (ast.Constant, ast.Str, ast.Num)):
                    return False
                if not isinstance(v, (ast.Constant, ast.Str, ast.Num)):
                    return False
            return True

        return False

    def _is_configuration_data(self, attr_name: str, node: ast.Assign) -> bool:
        if isinstance(node.value, (ast.List, ast.Dict)):
            has_literals = self._has_literal_values(node.value)
            is_mutated = attr_name in self.mutated_attributes

            return has_literals and not is_mutated

        return False

    def finalize_flows(self):
        config_filtered = 0

        for attr_name, node, class_name in self.pending_flows:
            if self._is_configuration_data(attr_name, node):
                config_filtered += 1
                logger.debug(f"[integration_monitor] Skipped config attribute: {attr_name}")
                continue

            self.flows.append({
                'producer': class_name or "unknown",
                'consumer': None,
                'channel': attr_name,
                'channel_type': "queue",
                'producer_file': str(self.file_path),
                'consumer_file': None,
                'line_number': node.lineno
            })

        if config_filtered > 0:
            logger.info(
                f"[integration_monitor] Filtered {config_filtered} "
                f"configuration attributes in {self.file_path.name}"
            )


class MissingWiringVisitor(ast.NodeVisitor):

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.current_class = None
        self.initialized_attributes: Set[str] = set()
        self.used_attributes: Dict[str, Dict[str, Any]] = {}
        self.uninitialized: Dict[str, Dict[str, Any]] = {}

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.initialized_attributes.clear()
        self.used_attributes.clear()

        self.generic_visit(node)

        for attr_name, usage_info in self.used_attributes.items():
            if attr_name not in self.initialized_attributes:
                self.uninitialized[attr_name] = usage_info

        self.current_class = None

    def visit_Assign(self, node):
        if isinstance(node.targets[0], ast.Attribute):
            attr = node.targets[0]
            if isinstance(attr.value, ast.Name) and attr.value.id == 'self':
                self.initialized_attributes.add(attr.attr)

        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Attribute):
                if isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == 'self':
                        attr_name = node.func.value.attr
                        method_name = node.func.attr

                        if attr_name not in self.used_attributes:
                            self.used_attributes[attr_name] = {
                                'file': str(self.file_path),
                                'line': node.lineno,
                                'usage': f'self.{attr_name}.{method_name}()'
                            }

        self.generic_visit(node)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    daemon = IntegrationMonitorDaemon()

    logger.info("[integration_monitor] Starting daemon...")
    daemon.start()


if __name__ == "__main__":
    main()
