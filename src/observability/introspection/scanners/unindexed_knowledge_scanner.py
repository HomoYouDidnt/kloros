#!/usr/bin/env python3
"""
Unindexed Knowledge Scanner

Periodically scans filesystem for unindexed or stale files and generates
curiosity questions to populate the knowledge base.

Purpose:
Enables autonomous knowledge discovery by detecting documentation, configuration,
source code, and service definitions that haven't been indexed yet. Generates
curiosity questions to trigger indexing via the DocumentationPlugin.

Example:
Scans /home/kloros/docs and finds ASTRAEA_SYSTEM_THESIS.md is not in Qdrant.
Generates question: "What knowledge does /home/kloros/docs/ASTRAEA_SYSTEM_THESIS.md contain?"
Investigation handler processes question, DocumentationPlugin indexes file.
"""

import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

SCAN_PATHS = [
    "/home/kloros/docs",
    "/home/kloros/config",
    "/home/kloros/src",
    "/etc/systemd/system",
]

FILE_PATTERNS = {
    "documentation": ["*.md", "*.txt"],
    "configuration": ["*.yaml", "*.yml", "*.json"],
    "source_code": ["*.py"],
    "services": ["*.service"],
}

SKIP_PATTERNS = [
    "__pycache__",
    ".venv",
    "*.pyc",
    ".git",
    "*.backup*",
    "*.bak",
    ".pytest_cache",
    "*.egg-info",
    "node_modules",
    ".cache",
]

SCAN_INTERVAL_SECONDS = 600
MAX_QUESTIONS_PER_SCAN = 10

PRIORITY_ORDER = {
    "documentation": 3,
    "configuration": 2,
    "source_code": 1,
    "services": 2,
}


@dataclass
class UnindexedFile:
    """Represents a file that needs indexing."""
    file_path: str
    file_type: str
    file_size: int
    mtime: float
    priority: int


class UnindexedKnowledgeScanner:
    """
    Scanner that discovers unindexed files and generates curiosity questions.

    Features:
    - Recursive filesystem scanning with pattern matching
    - Qdrant integration to check indexed files
    - Staleness detection (mtime vs indexed_mtime)
    - Priority ordering (Docs > Configs > Source code)
    - Rate limiting to avoid flooding curiosity feed
    """

    def __init__(self):
        self.available = True
        self.indexer = None

        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.knowledge_indexer import get_knowledge_indexer

            self.indexer = get_knowledge_indexer()

            if self.indexer is None:
                logger.warning("[unindexed_scanner] KnowledgeIndexer not available")
                self.available = False
            else:
                logger.info("[unindexed_scanner] KnowledgeIndexer initialized")

        except Exception as e:
            logger.warning(f"[unindexed_scanner] Failed to initialize: {e}")
            self.available = False

    def _should_skip(self, path: Path) -> bool:
        """
        Check if path should be skipped based on SKIP_PATTERNS.

        Args:
            path: Path to check

        Returns:
            True if path should be skipped
        """
        path_str = str(path)

        for pattern in SKIP_PATTERNS:
            if pattern.startswith("*."):
                suffix = pattern[1:]
                if path_str.endswith(suffix):
                    return True
            elif pattern in path_str:
                return True

        return False

    def _collect_files_by_type(self) -> Dict[str, List[Path]]:
        """
        Walk SCAN_PATHS and collect files by type.

        Returns:
            Dict mapping file_type to list of file paths
        """
        files_by_type = {
            "documentation": [],
            "configuration": [],
            "source_code": [],
            "services": [],
        }

        for scan_path_str in SCAN_PATHS:
            scan_path = Path(scan_path_str)

            if not scan_path.exists():
                logger.debug(f"[unindexed_scanner] Scan path does not exist: {scan_path}")
                continue

            for file_type, patterns in FILE_PATTERNS.items():
                for pattern in patterns:
                    if scan_path.is_dir():
                        matches = scan_path.rglob(pattern)
                    else:
                        if scan_path.match(pattern):
                            matches = [scan_path]
                        else:
                            matches = []

                    for file_path in matches:
                        if not file_path.is_file():
                            continue

                        if self._should_skip(file_path):
                            continue

                        files_by_type[file_type].append(file_path)

        for file_type, files in files_by_type.items():
            logger.debug(f"[unindexed_scanner] Found {len(files)} {file_type} files")

        return files_by_type

    def _get_indexed_files(self) -> Set[str]:
        """
        Get set of all indexed file paths from Qdrant.

        Returns:
            Set of absolute file path strings
        """
        if not self.available or self.indexer is None:
            return set()

        try:
            indexed_paths = self.indexer.get_indexed_files()
            return set(indexed_paths)

        except Exception as e:
            logger.error(f"[unindexed_scanner] Failed to get indexed files: {e}")
            return set()

    def _detect_unindexed_files(self) -> List[UnindexedFile]:
        """
        Compare filesystem files with indexed files and detect unindexed ones.

        Returns:
            List of UnindexedFile objects sorted by priority
        """
        files_by_type = self._collect_files_by_type()
        indexed_files = self._get_indexed_files()

        unindexed = []

        for file_type, file_paths in files_by_type.items():
            for file_path in file_paths:
                file_path_str = str(file_path.absolute())

                if file_path_str not in indexed_files:
                    try:
                        stat = file_path.stat()
                        unindexed.append(UnindexedFile(
                            file_path=file_path_str,
                            file_type=file_type,
                            file_size=stat.st_size,
                            mtime=stat.st_mtime,
                            priority=PRIORITY_ORDER.get(file_type, 0)
                        ))
                    except Exception as e:
                        logger.warning(f"[unindexed_scanner] Cannot stat {file_path}: {e}")
                        continue

        unindexed.sort(key=lambda f: f.priority, reverse=True)

        logger.info(f"[unindexed_scanner] Detected {len(unindexed)} unindexed files")

        return unindexed

    def _detect_stale_files(self) -> List[UnindexedFile]:
        """
        Detect files where filesystem mtime > indexed_mtime.

        Returns:
            List of UnindexedFile objects for stale files
        """
        if not self.available or self.indexer is None:
            return []

        stale_files = []
        files_by_type = self._collect_files_by_type()

        for file_type, file_paths in files_by_type.items():
            for file_path in file_paths:
                try:
                    if self.indexer.is_stale(file_path):
                        stat = file_path.stat()
                        stale_files.append(UnindexedFile(
                            file_path=str(file_path.absolute()),
                            file_type=file_type,
                            file_size=stat.st_size,
                            mtime=stat.st_mtime,
                            priority=PRIORITY_ORDER.get(file_type, 0)
                        ))
                except Exception as e:
                    logger.warning(f"[unindexed_scanner] Error checking staleness for {file_path}: {e}")
                    continue

        logger.info(f"[unindexed_scanner] Detected {len(stale_files)} stale files")

        return stale_files

    def _sanitize_filename(self, file_path: str) -> str:
        """
        Sanitize file path for use in hypothesis ID.

        Args:
            file_path: Absolute file path

        Returns:
            Sanitized filename suitable for hypothesis ID
        """
        path = Path(file_path)
        name = path.name.replace(".", "_").replace("-", "_").upper()
        return name

    def _generate_question_for_file(self, file: UnindexedFile, is_stale: bool = False) -> Dict[str, Any]:
        """
        Generate curiosity question for unindexed or stale file.

        Args:
            file: UnindexedFile object
            is_stale: True if file is stale, False if unindexed

        Returns:
            Question dictionary ready for emission
        """
        sanitized_name = self._sanitize_filename(file.file_path)

        if is_stale:
            question = f"Should I re-index stale file {file.file_path}?"
            hypothesis = f"STALE_KNOWLEDGE_{sanitized_name}"
            priority = "low"
        else:
            question = f"What knowledge does {file.file_path} contain?"
            hypothesis = f"UNINDEXED_KNOWLEDGE_{sanitized_name}"
            priority = "medium"

        evidence = [
            f"file_path: {file.file_path}",
            f"file_type: {file.file_type}",
            f"size: {file.file_size}",
            f"mtime: {file.mtime}"
        ]

        evidence_str = "|".join(sorted(evidence))
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

        question_dict = {
            "id": hypothesis.lower(),
            "hypothesis": hypothesis,
            "question": question,
            "evidence": evidence,
            "evidence_hash": evidence_hash,
            "action_class": "investigate",
            "autonomy": 3,
            "value_estimate": 0.6 if not is_stale else 0.3,
            "cost_estimate": 0.2,
            "status": "ready",
            "timestamp": datetime.now().isoformat(),
            "priority": priority,
        }

        return question_dict

    def scan_for_unindexed_knowledge(self) -> List[Dict[str, Any]]:
        """
        Main entry point: Scan for unindexed and stale files, generate questions.

        Returns:
            List of question dictionaries, limited to MAX_QUESTIONS_PER_SCAN
        """
        if not self.available:
            logger.warning("[unindexed_scanner] Scanner not available")
            return []

        logger.info("[unindexed_scanner] Starting knowledge scan...")

        unindexed_files = self._detect_unindexed_files()
        stale_files = self._detect_stale_files()

        questions = []

        for file in unindexed_files[:MAX_QUESTIONS_PER_SCAN]:
            question = self._generate_question_for_file(file, is_stale=False)
            questions.append(question)

        remaining_slots = MAX_QUESTIONS_PER_SCAN - len(questions)

        if remaining_slots > 0:
            for file in stale_files[:remaining_slots]:
                question = self._generate_question_for_file(file, is_stale=True)
                questions.append(question)

        logger.info(f"[unindexed_scanner] Generated {len(questions)} questions "
                   f"({len([q for q in questions if 'UNINDEXED' in q['hypothesis']])} unindexed, "
                   f"{len([q for q in questions if 'STALE' in q['hypothesis']])} stale)")

        return questions

    def format_findings(self, questions: List[Dict[str, Any]]) -> str:
        """
        Format questions as human-readable report.

        Args:
            questions: List of question dictionaries

        Returns:
            Formatted report string
        """
        if not questions:
            return "No unindexed or stale files detected"

        report = []
        report.append(f"Knowledge Discovery Scan Results ({len(questions)} questions)")
        report.append("=" * 60)

        unindexed = [q for q in questions if "UNINDEXED" in q["hypothesis"]]
        stale = [q for q in questions if "STALE" in q["hypothesis"]]

        if unindexed:
            report.append(f"\nUnindexed Files ({len(unindexed)}):")
            for q in unindexed[:5]:
                file_path = [e for e in q["evidence"] if e.startswith("file_path:")][0].split(": ", 1)[1]
                file_type = [e for e in q["evidence"] if e.startswith("file_type:")][0].split(": ", 1)[1]
                report.append(f"  - {Path(file_path).name} ({file_type})")

        if stale:
            report.append(f"\nStale Files ({len(stale)}):")
            for q in stale[:5]:
                file_path = [e for e in q["evidence"] if e.startswith("file_path:")][0].split(": ", 1)[1]
                report.append(f"  - {Path(file_path).name}")

        if len(questions) > 5:
            report.append(f"\n... and {len(questions) - 5} more files")

        return "\n".join(report)


def scan_for_unindexed_knowledge() -> tuple[List[Dict[str, Any]], str]:
    """
    Main entry point: Scan for unindexed knowledge and return questions.

    Returns:
        Tuple of (questions, formatted_report)
    """
    scanner = UnindexedKnowledgeScanner()
    questions = scanner.scan_for_unindexed_knowledge()
    report = scanner.format_findings(questions)

    return questions, report


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    questions, report = scan_for_unindexed_knowledge()

    print(report)
    print(f"\nGenerated {len(questions)} questions")

    if questions:
        print("\nSample Question:")
        sample = questions[0]
        print(f"  ID: {sample['id']}")
        print(f"  Question: {sample['question']}")
        print(f"  Hypothesis: {sample['hypothesis']}")
        print(f"  Evidence: {sample['evidence']}")
        print(f"  Priority: {sample['priority']}")
