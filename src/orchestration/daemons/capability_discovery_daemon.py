#!/usr/bin/env python3

import ast
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import OrderedDict

from src.orchestration.daemons.base_streaming_daemon import BaseStreamingDaemon
from src.cognition.mind.cognition.semantic_analysis import ArchitecturalReasoner

try:
    from src.orchestration.core.umn_bus import UMNPub
except ImportError:
    UMNPub = None

logger = logging.getLogger(__name__)


# Module-level constants (shared by daemon and visitor)
CAPABILITY_SUFFIXES = {
    'analyzer', 'optimizer', 'processor', 'handler', 'manager',
    'builder', 'factory', 'controller', 'service', 'engine',
    'detector', 'scanner', 'monitor', 'validator', 'transformer'
}

CAPABILITY_DECORATORS = {
    'tool', 'skill', 'capability', 'tool_capability',
    'skill_capability', 'pattern', 'agent'
}


class CapabilityDiscoveryMonitorDaemon(BaseStreamingDaemon):

    def __init__(
        self,
        watch_path: Path = Path("/home/kloros/src"),
        state_file: Path = Path("/home/kloros/.kloros/capability_discovery_state.json"),
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
        self.discovered_capabilities: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.semantic_reasoner = ArchitecturalReasoner()
        self.chem_pub = None
        self.files_processed_since_save = 0

        self.load_state()

    def process_file_event(self, event_type: str, file_path: Path):
        file_path_str = str(file_path)

        if event_type == 'delete':
            if file_path_str in self.file_hashes:
                del self.file_hashes[file_path_str]
            logger.debug(f"[capability_discovery] File deleted: {file_path}")
            return

        if not file_path.exists():
            return

        file_changed = self._has_file_changed(file_path)

        if not file_changed:
            logger.debug(f"[capability_discovery] File unchanged, skipping: {file_path}")
            return

        logger.info(f"[capability_discovery] Analyzing file: {file_path}")

        indicators = self._extract_capability_indicators(file_path)

        if not indicators:
            logger.debug(f"[capability_discovery] No indicators found in {file_path}")
            return

        validated = self._validate_capabilities_with_semantic_analysis(indicators)

        # Log phantom filtering
        phantom_count = len(indicators) - len(validated)
        if phantom_count > 0:
            logger.info(
                f"[capability_discovery] Filtered {phantom_count} phantoms from {file_path.name}"
            )

        for cap in validated:
            term = cap['term']
            if term not in self.discovered_capabilities:
                self.discovered_capabilities[term] = {
                    'term': term,
                    'type': cap['type'],
                    'evidence': cap['evidence'],
                    'is_real_gap': cap.get('is_real_gap', True),
                    'confidence': cap.get('confidence', 0.5),
                    'first_seen': time.time()
                }

        if validated:
            logger.info(f"[capability_discovery] Validated {len(validated)} capabilities")
            self._emit_questions_to_umn(validated)

        self._evict_capability_cache_if_needed()
        self._evict_file_hash_cache_if_needed()

        # Periodic state save every 100 files
        self.files_processed_since_save += 1
        if self.files_processed_since_save >= 100:
            logger.info("[capability_discovery] Periodic state save")
            self.save_state()
            self.files_processed_since_save = 0
        self._evict_cache_if_needed()

    def _compute_file_hash(self, file_path: Path) -> str:
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.debug(f"[capability_discovery] Cannot hash {file_path}: {e}")
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

    def _extract_capability_indicators(self, file_path: Path) -> List[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.debug(f"[capability_discovery] Cannot read {file_path}: {e}")
            return []

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            logger.debug(f"[capability_discovery] Syntax error in {file_path}: {e}")
            return []

        visitor = CapabilityIndicatorVisitor(file_path)
        visitor.visit(tree)

        return visitor.indicators

    def _validate_capabilities_with_semantic_analysis(
        self,
        indicators: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        validated = []

        for indicator in indicators:
            term = indicator['term']

            try:
                analysis = self.semantic_reasoner.analyze_gap_hypothesis(
                    term=term,
                    max_files=100
                )

                if analysis.is_real_gap:
                    validated.append({
                        'term': term,
                        'type': indicator['type'],
                        'evidence': indicator['evidence'],
                        'is_real_gap': True,
                        'confidence': analysis.confidence,
                        'pattern': analysis.pattern,
                        'explanation': analysis.explanation
                    })
                    logger.info(
                        f"[capability_discovery] Real gap: {term} "
                        f"(confidence: {analysis.confidence:.2f})"
                    )
                else:
                    logger.debug(
                        f"[capability_discovery] Filtered phantom: {term} "
                        f"({analysis.explanation})"
                    )

            except Exception as e:
                logger.error(
                    f"[capability_discovery] Semantic validation failed for {term}: {e}",
                    exc_info=True
                )
                # Skip this indicator - don't emit unvalidated capabilities

        return validated

    def _evict_capability_cache_if_needed(self):
        if len(self.discovered_capabilities) > self.max_cache_size:
            to_remove = len(self.discovered_capabilities) - self.max_cache_size
            for _ in range(to_remove):
                self.discovered_capabilities.popitem(last=False)

    def _evict_file_hash_cache_if_needed(self):
        if len(self.file_hashes) > self.max_cache_size:
            to_remove = len(self.file_hashes) - self.max_cache_size
            for key in list(self.file_hashes.keys())[:to_remove]:
                del self.file_hashes[key]

    def _emit_questions_to_umn(self, capabilities: List[Dict[str, Any]]):
        if not UMNPub:
            logger.warning("[capability_discovery] UMN not available, skipping emission")
            return

        if not self.chem_pub:
            try:
                self.chem_pub = UMNPub()
            except Exception as e:
                logger.error(f"[capability_discovery] Failed to create UMNPub: {e}")
                return

        for cap in capabilities:
            try:
                term = cap['term']
                timestamp = int(time.time())
                question_id = f"capability_{term}_{timestamp}"

                confidence = cap.get('confidence', 0.5)
                severity = 'high' if confidence >= 0.75 else 'medium'

                self.chem_pub.emit(
                    signal="curiosity.capability_question",
                    ecosystem="curiosity",
                    intensity=0.90,
                    facts={
                        'question_id': question_id,
                        'hypothesis': f"Missing capability: {term}",
                        'question': f"Should we implement {term}?",
                        'evidence': cap['evidence'],
                        'severity': severity,
                        'category': 'capability_discovery',
                        'source': 'capability_discovery_daemon',
                        'confidence': confidence,
                        'timestamp': time.time()
                    }
                )
                logger.info(f"[capability_discovery] Emitted question: {question_id}")

            except Exception as e:
                logger.error(
                    f"[capability_discovery] Failed to emit question for {cap['term']}: {e}"
                )

    def save_state(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                'file_hashes': self.file_hashes,
                'discovered_capabilities': dict(self.discovered_capabilities),
                'timestamp': time.time()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f)

            logger.info(f"[capability_discovery] Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"[capability_discovery] Failed to save state: {e}")

        finally:
            # Cleanup UMN connection if exists
            if self.chem_pub is not None:
                try:
                    # Note: UMNPub may not have explicit close() method
                    # Setting to None allows garbage collection
                    logger.info("[capability_discovery] Cleaning up UMN connection")
                    self.chem_pub = None
                except Exception as e:
                    logger.warning(f"[capability_discovery] UMN cleanup error: {e}")

    def load_state(self):
        if not self.state_file.exists():
            logger.info("[capability_discovery] No previous state found, starting fresh")
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.file_hashes = state.get('file_hashes', {})
            self.discovered_capabilities = OrderedDict(
                state.get('discovered_capabilities', {})
            )

            logger.info(
                f"[capability_discovery] Loaded state: "
                f"{len(self.file_hashes)} files, "
                f"{len(self.discovered_capabilities)} capabilities"
            )

        except Exception as e:
            logger.error(f"[capability_discovery] Failed to load state: {e}")


class CapabilityIndicatorVisitor(ast.NodeVisitor):

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.indicators: List[Dict[str, Any]] = []
        self.seen_terms: Set[str] = set()

    def visit_ClassDef(self, node):
        class_name = node.name
        class_name_lower = class_name.lower()

        for suffix in CAPABILITY_SUFFIXES:
            if class_name_lower.endswith(suffix):
                term = suffix
                if term not in self.seen_terms:
                    self.indicators.append({
                        'term': term,
                        'type': 'class',
                        'evidence': [f"{class_name} class in {self.file_path.name}"],
                        'line': node.lineno
                    })
                    self.seen_terms.add(term)
                break

        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if not node.module:
            self.generic_visit(node)
            return

        module_parts = node.module.split('.')

        if 'tools' in module_parts or 'skills' in module_parts:
            for alias in node.names:
                term = alias.name.lower()
                if term not in self.seen_terms:
                    self.indicators.append({
                        'term': term,
                        'type': 'import',
                        'evidence': [f"from {node.module} import {alias.name}"],
                        'line': node.lineno
                    })
                    self.seen_terms.add(term)

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            decorator_name = None

            if isinstance(decorator, ast.Name):
                decorator_name = decorator.id
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    decorator_name = decorator.func.id

            if decorator_name and decorator_name in CAPABILITY_DECORATORS:
                term = f"{decorator_name}_pattern"
                if term not in self.seen_terms:
                    self.indicators.append({
                        'term': term,
                        'type': 'decorator',
                        'evidence': [
                            f"@{decorator_name} on {node.name} in {self.file_path.name}"
                        ],
                        'line': node.lineno
                    })
                    self.seen_terms.add(term)

        self.generic_visit(node)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    daemon = CapabilityDiscoveryMonitorDaemon()

    logger.info("[capability_discovery] Starting daemon...")
    daemon.start()


if __name__ == "__main__":
    main()
