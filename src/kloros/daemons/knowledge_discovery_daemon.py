#!/usr/bin/env python3

import ast
import hashlib
import logging
import pickle
import time
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional
import inotify.adapters
import inotify.constants

from kloros.daemons.base_streaming_daemon import BaseStreamingDaemon

try:
    from kloros.orchestration.chem_bus_v2 import ChemPub
except ImportError:
    ChemPub = None

logger = logging.getLogger(__name__)


class KnowledgeDiscoveryScannerDaemon(BaseStreamingDaemon):

    def __init__(
        self,
        watch_path: Path = Path("/home/kloros"),
        state_file: Path = Path("/home/kloros/.kloros/knowledge_discovery_state.pkl"),
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

        # TODO: Integrate with actual knowledge indexing system (e.g., vector database, search index)
        # Currently always empty, so all docs are flagged as "unindexed"
        # Future enhancement: Populate this dict when documents are indexed
        self.knowledge_index: Dict[str, bool] = {}

        self.chem_pub = None

        self.load_state()

    def _watch_files(self):
        watcher = inotify.adapters.InotifyTree(
            str(self.watch_path),
            mask=inotify.constants.IN_MODIFY |
                 inotify.constants.IN_CREATE |
                 inotify.constants.IN_DELETE
        )

        for event in watcher.event_gen(yield_nones=False):
            if self.shutdown_event.is_set():
                break

            (_, type_names, path, filename) = event

            knowledge_extensions = {'.md', '.rst', '.txt', '.py'}
            if not any(filename.endswith(ext) for ext in knowledge_extensions):
                continue

            if 'test_' in filename or '__pycache__' in path:
                continue

            file_path = Path(path) / filename
            event_type = 'modify' if 'IN_MODIFY' in type_names else \
                        'create' if 'IN_CREATE' in type_names else 'delete'

            try:
                self.event_queue.put((event_type, file_path), timeout=1.0)
            except queue.Full:
                logging.warning(f"[knowledge_discovery] Event queue full, dropping event for {file_path}")

    def process_file_event(self, event_type: str, file_path: Path):
        file_path_str = str(file_path)

        if event_type == 'delete':
            if file_path_str in self.file_hashes:
                del self.file_hashes[file_path_str]
            logger.debug(f"[knowledge_discovery] File deleted: {file_path}")
            return

        if not file_path.exists():
            return

        if not self._is_knowledge_file(file_path):
            logger.debug(f"[knowledge_discovery] Not a knowledge file: {file_path}")
            return

        file_changed = self._has_file_changed(file_path)

        if not file_changed:
            logger.debug(f"[knowledge_discovery] File unchanged, skipping: {file_path}")
            return

        logger.info(f"[knowledge_discovery] Analyzing file: {file_path}")

        all_gaps = []

        unindexed_gaps = self._detect_unindexed_documentation(file_path)
        all_gaps.extend(unindexed_gaps)

        if file_path.suffix == '.py':
            docstring_gaps = self._detect_missing_docstrings(file_path)
            all_gaps.extend(docstring_gaps)

        if file_path.suffix in ['.md', '.rst']:
            stale_gaps = self._detect_stale_documentation(file_path)
            all_gaps.extend(stale_gaps)

        if all_gaps:
            logger.info(f"[knowledge_discovery] Detected {len(all_gaps)} knowledge gaps")
            self._emit_questions_to_chembus(all_gaps)
        else:
            logger.debug(f"[knowledge_discovery] No gaps found in {file_path}")

        self._evict_cache_if_needed()
        self._evict_file_hash_cache_if_needed()
        self._evict_knowledge_index_if_needed()

    def _is_knowledge_file(self, file_path: Path) -> bool:
        knowledge_extensions = {'.md', '.rst', '.txt', '.py'}
        return file_path.suffix in knowledge_extensions

    def _compute_file_hash(self, file_path: Path) -> str:
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.debug(f"[knowledge_discovery] Cannot hash {file_path}: {e}")
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

    def _is_indexed(self, file_path: Path) -> bool:
        try:
            relative_path = str(file_path.relative_to(self.watch_path))
            return relative_path in self.knowledge_index
        except ValueError:
            return False

    def _detect_unindexed_documentation(self, file_path: Path) -> List[Dict[str, Any]]:
        gaps = []

        if file_path.suffix in ['.md', '.rst', '.txt']:
            if not self._is_indexed(file_path):
                gaps.append({
                    'type': 'unindexed_documentation',
                    'severity': 'medium',
                    'evidence': [f'New documentation file: {file_path.name}'],
                    'suggestion': f'Index {file_path.name} for knowledge retrieval',
                    'file': file_path.name
                })

        return gaps

    def _detect_missing_docstrings(self, file_path: Path) -> List[Dict[str, Any]]:
        if file_path.suffix != '.py':
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.debug(f"[knowledge_discovery] Cannot read {file_path}: {e}")
            return []

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            logger.debug(f"[knowledge_discovery] Syntax error in {file_path}: {e}")
            return []

        missing_docs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                if not ast.get_docstring(node):
                    missing_docs.append(node.name)

        if len(missing_docs) > 3:
            return [{
                'type': 'missing_docstrings',
                'severity': 'low',
                'evidence': [f'{len(missing_docs)} items without docstrings in {file_path.name}'],
                'suggestion': f'Add docstrings to improve code documentation',
                'file': file_path.name
            }]

        return []

    def _detect_stale_documentation(self, file_path: Path) -> List[Dict[str, Any]]:
        if file_path.suffix not in ['.md', '.rst']:
            return []

        try:
            mod_time = file_path.stat().st_mtime
            days_old = (time.time() - mod_time) / 86400

            if days_old > 90:
                return [{
                    'type': 'stale_documentation',
                    'severity': 'low',
                    'evidence': [f'{file_path.name} not modified in {int(days_old)} days'],
                    'suggestion': f'Review and update {file_path.name}',
                    'file': file_path.name
                }]
        except Exception as e:
            logger.debug(f"[knowledge_discovery] Failed to check staleness for {file_path}: {e}")

        return []

    def _emit_questions_to_chembus(self, gaps: List[Dict[str, Any]]):
        if not ChemPub:
            logger.warning("[knowledge_discovery] ChemBus not available, skipping emission")
            return

        if not self.chem_pub:
            try:
                self.chem_pub = ChemPub()
            except Exception as e:
                logger.error(f"[knowledge_discovery] Failed to create ChemPub: {e}")
                return

        for gap in gaps:
            try:
                timestamp = int(time.time())
                question_id = f'knowledge_{gap["type"]}_{timestamp}'

                self.chem_pub.emit(
                    signal="curiosity.knowledge_question",
                    ecosystem="curiosity",
                    intensity=0.85,
                    facts={
                        'question_id': question_id,
                        'hypothesis': f'Knowledge gap: {gap["type"]}',
                        'question': f'Should we {gap["suggestion"]}?',
                        'evidence': gap['evidence'],
                        'severity': gap['severity'],
                        'category': 'knowledge_discovery',
                        'source': 'knowledge_discovery_daemon',
                        'timestamp': timestamp
                    }
                )
                logger.info(f"[knowledge_discovery] Emitted question: {question_id}")

            except Exception as e:
                logger.error(f"[knowledge_discovery] Failed to emit question for {gap['type']}: {e}")

    def _evict_file_hash_cache_if_needed(self):
        """Evict oldest file hashes if cache exceeds max_cache_size."""
        if len(self.file_hashes) > self.max_cache_size:
            to_remove = len(self.file_hashes) - self.max_cache_size
            for key in list(self.file_hashes.keys())[:to_remove]:
                del self.file_hashes[key]
            logger.debug(
                f"[knowledge_discovery] Evicted {to_remove} file hashes "
                f"(cache size: {len(self.file_hashes)})"
            )

    def _evict_knowledge_index_if_needed(self):
        """Evict oldest knowledge index entries if cache exceeds max_cache_size."""
        if len(self.knowledge_index) > self.max_cache_size:
            to_remove = len(self.knowledge_index) - self.max_cache_size
            for key in list(self.knowledge_index.keys())[:to_remove]:
                del self.knowledge_index[key]
            logger.debug(
                f"[knowledge_discovery] Evicted {to_remove} knowledge index entries "
                f"(cache size: {len(self.knowledge_index)})"
            )

    def save_state(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            state = {
                'file_hashes': self.file_hashes,
                'knowledge_index': self.knowledge_index,
                'timestamp': time.time()
            }

            with open(self.state_file, 'wb') as f:
                pickle.dump(state, f)

            logger.info(f"[knowledge_discovery] Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"[knowledge_discovery] Failed to save state: {e}")

    def load_state(self):
        if not self.state_file.exists():
            logger.info("[knowledge_discovery] No previous state found, starting fresh")
            return

        try:
            with open(self.state_file, 'rb') as f:
                state = pickle.load(f)

            self.file_hashes = state.get('file_hashes', {})
            self.knowledge_index = state.get('knowledge_index', {})

            logger.info(
                f"[knowledge_discovery] Loaded state: "
                f"{len(self.file_hashes)} files, {len(self.knowledge_index)} indexed"
            )

        except (pickle.UnpicklingError, EOFError, ValueError) as e:
            logger.error(
                f"[knowledge_discovery] Corrupted state file, starting fresh: {e}"
            )
            # Backup corrupted file for investigation
            try:
                corrupted_path = self.state_file.with_suffix('.pkl.corrupted')
                self.state_file.rename(corrupted_path)
                logger.info(f"[knowledge_discovery] Backed up corrupted state to {corrupted_path}")
            except Exception as backup_error:
                logger.warning(f"[knowledge_discovery] Could not backup corrupted state: {backup_error}")

        except Exception as e:
            logger.error(f"[knowledge_discovery] Failed to load state: {e}", exc_info=True)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    # Watch only docs directory to avoid permission issues with tmp/logs/etc
    daemon = KnowledgeDiscoveryScannerDaemon(
        watch_path=Path("/home/kloros/docs")
    )

    logger.info("[knowledge_discovery] Starting daemon...")
    daemon.start()


if __name__ == "__main__":
    main()
