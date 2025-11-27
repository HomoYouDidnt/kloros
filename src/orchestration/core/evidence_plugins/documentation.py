#!/usr/bin/env python3
"""
Documentation Evidence Plugin - Dual-mode knowledge indexing and retrieval.

Mode 1: Index unindexed files when investigating "What knowledge does X contain?"
Mode 2: Retrieve indexed knowledge as evidence for investigations
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, List

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class DocumentationPlugin(EvidencePlugin):
    """
    Dual-purpose documentation plugin:
    1. Indexes files to knowledge base when investigating unindexed files
    2. Retrieves relevant knowledge from index for investigations

    Uses KnowledgeIndexer for LLM summarization and Qdrant storage.
    Validates freshness and re-indexes stale files automatically.
    """

    def __init__(self):
        """Initialize documentation plugin with knowledge indexer."""
        self._indexer = None

    @property
    def indexer(self):
        """Lazy-load knowledge indexer to avoid circular imports."""
        if self._indexer is None:
            try:
                from src.cognition.mind.memory.knowledge_indexer import get_knowledge_indexer
                self._indexer = get_knowledge_indexer()
                if self._indexer is None:
                    logger.warning("[documentation] Knowledge indexer not available")
            except Exception as e:
                logger.error(f"[documentation] Failed to initialize knowledge indexer: {e}")
        return self._indexer

    @property
    def name(self) -> str:
        return "documentation"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        """
        Determine if this plugin can contribute.

        Mode 1 (Indexing): Activate for "What knowledge does X contain?" questions
        Mode 2 (Retrieval): Activate for any investigation to provide context
        """
        if self.indexer is None:
            logger.debug("[documentation] Cannot gather: indexer unavailable")
            return False

        hypothesis = context.get("hypothesis", "")

        if "What knowledge does" in question or "UNINDEXED_KNOWLEDGE" in hypothesis:
            logger.debug("[documentation] Mode 1 (Indexing): Activating for knowledge indexing question")
            return True

        logger.debug("[documentation] Mode 2 (Retrieval): Activating for context retrieval")
        return True

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        """
        Gather evidence based on mode.

        Mode 1: Index file and return summary
        Mode 2: Search knowledge base and return relevant summaries
        """
        if self.indexer is None:
            logger.warning("[documentation] Cannot gather evidence: indexer unavailable")
            return []

        hypothesis = context.get("hypothesis", "")

        if "What knowledge does" in question or "UNINDEXED_KNOWLEDGE" in hypothesis:
            return self._mode_indexing(question, context)
        else:
            return self._mode_retrieval(question, context)

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate cost of gathering evidence.

        Indexing: LLM call + embedding, ~30s
        Retrieval: Embedding + vector search, ~1s
        """
        hypothesis = context.get("hypothesis", "")

        if "What knowledge does" in question or "UNINDEXED_KNOWLEDGE" in hypothesis:
            return {
                "time_estimate_seconds": 30.0,
                "token_cost": 500,
                "complexity": "high"
            }
        else:
            return {
                "time_estimate_seconds": 1.0,
                "token_cost": 0,
                "complexity": "low"
            }

    def priority(self, investigation_type: str) -> int:
        """
        Priority for evidence gathering order.

        Indexing mode: Very high (95) to index before other analysis
        Retrieval mode: Medium (70) to provide context after structural analysis
        """
        if investigation_type == "knowledge_indexing":
            return 95
        return 70

    def _mode_indexing(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        """
        Mode 1: Index unindexed file.

        Extract file_path from evidence, read file, generate summary, index to Qdrant.
        """
        evidence_list = []

        file_path = self._extract_file_path_from_context(question, context)

        if not file_path:
            logger.warning("[documentation] Mode 1: Could not extract file path from context")
            return evidence_list

        logger.info(f"[documentation] Mode 1 (Indexing): Processing {file_path}")

        result = self.indexer.summarize_and_index(file_path)

        if result["success"]:
            evidence_list.append(Evidence(
                source=self.name,
                evidence_type="knowledge_indexed",
                content=result["summary"],
                metadata={
                    "file_path": result["file_path"],
                    "indexed_at": result["indexed_at"],
                    "mode": "indexing"
                },
                timestamp="",
                confidence=0.9
            ))
            logger.info(f"[documentation] Successfully indexed: {file_path}")
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"[documentation] Failed to index {file_path}: {error_msg}")
            evidence_list.append(Evidence(
                source=self.name,
                evidence_type="indexing_failed",
                content=f"Failed to index file: {error_msg}",
                metadata={
                    "file_path": result["file_path"],
                    "error": error_msg,
                    "mode": "indexing"
                },
                timestamp="",
                confidence=0.5
            ))

        return evidence_list

    def _mode_retrieval(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        """
        Mode 2: Retrieve relevant knowledge from index.

        Search Qdrant for semantic matches, check freshness, re-index stale files.
        """
        evidence_list = []

        query_terms = self._extract_query_terms(question)

        if not query_terms:
            logger.debug("[documentation] Mode 2: No clear query terms, skipping retrieval")
            return evidence_list

        logger.info(f"[documentation] Mode 2 (Retrieval): Searching for '{query_terms}'")

        results = self.indexer.search_knowledge(query=query_terms, top_k=5)

        if not results:
            logger.debug(f"[documentation] No knowledge base results for query: '{query_terms}'")
            return evidence_list

        summaries = []
        file_paths = []
        stale_count = 0

        for result in results:
            file_path = Path(result["file_path"])
            summary = result["summary"]
            similarity = result["similarity"]

            if self.indexer.is_stale(file_path):
                logger.info(f"[documentation] Stale file detected, re-indexing: {file_path}")
                reindex_result = self.indexer.summarize_and_index(file_path)
                if reindex_result["success"]:
                    summary = reindex_result["summary"]
                    stale_count += 1

            summaries.append({
                "file_path": str(file_path),
                "summary": summary,
                "similarity": similarity
            })
            file_paths.append(str(file_path))

        evidence_list.append(Evidence(
            source=self.name,
            evidence_type="indexed_knowledge",
            content={
                "summaries": summaries,
                "file_paths": file_paths
            },
            metadata={
                "query": query_terms,
                "result_count": len(results),
                "stale_reindexed": stale_count,
                "mode": "retrieval"
            },
            timestamp="",
            confidence=0.8
        ))

        logger.info(f"[documentation] Retrieved {len(results)} knowledge base entries "
                   f"(re-indexed {stale_count} stale files)")

        return evidence_list

    def _extract_file_path_from_context(self, question: str, context: Dict[str, Any]) -> Path | None:
        """
        Extract file path from question or evidence context.

        Looks for:
        1. Evidence strings like "file_path: /home/kloros/..."
        2. Paths in the question text
        3. Paths in existing evidence metadata
        """
        existing_evidence = context.get("existing_evidence", [])

        for ev in existing_evidence:
            if isinstance(ev.content, str) and ev.content.startswith("file_path:"):
                path_str = ev.content.replace("file_path:", "").strip()
                return Path(path_str)

            if "file_path" in ev.metadata:
                return Path(ev.metadata["file_path"])

            if ev.evidence_type == "file_path" and isinstance(ev.content, str):
                return Path(ev.content)

        path_pattern = r'/[\w/\-\.]+\.\w+'
        matches = re.findall(path_pattern, question)
        if matches:
            return Path(matches[0])

        logger.warning("[documentation] Could not extract file path from question or context")
        return None

    def _extract_query_terms(self, question: str) -> str:
        """
        Extract key terms from question for semantic search.

        Removes stop words and focuses on meaningful terms.
        """
        stop_words = {
            "what", "is", "are", "the", "a", "an", "how", "does", "do",
            "why", "when", "where", "which", "my", "i", "have", "has"
        }

        words = re.findall(r'\b\w+\b', question.lower())
        meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]

        if len(meaningful_words) < 2:
            return question

        query = " ".join(meaningful_words[:8])

        logger.debug(f"[documentation] Extracted query terms: '{query}' from '{question}'")
        return query
