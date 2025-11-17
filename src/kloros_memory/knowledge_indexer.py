"""
Knowledge indexer for KLoROS autonomous knowledge discovery system.

Reads files, generates LLM summaries, and indexes to Qdrant for semantic search.
Supports staleness detection and automatic re-indexing.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import requests

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        ScrollRequest,
    )
    HAS_QDRANT = True
except ImportError:
    QdrantClient = None
    HAS_QDRANT = False

from .embeddings import get_embedding_engine

logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    """
    Shared library for reading files, generating LLM summaries, and indexing to Qdrant.

    Features:
    - LLM-powered summarization via Ollama
    - Qdrant indexing with metadata filtering
    - Staleness detection (filesystem mtime vs indexed_mtime)
    - File type detection and appropriate summarization
    - Error handling for binary files, encoding issues, LLM failures
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str = "kloros_knowledge",
        llm_model: str = "qwen2.5-coder:14b",
        llm_url: str = "http://100.67.244.66:11434"
    ):
        """
        Initialize knowledge indexer.

        Args:
            qdrant_client: QdrantClient instance
            collection_name: Qdrant collection name
            llm_model: Ollama model for summaries
            llm_url: Ollama server URL
        """
        if not HAS_QDRANT:
            raise ImportError(
                "qdrant-client is not installed. "
                "Install it with: pip install qdrant-client"
            )

        self.client = qdrant_client
        self.collection_name = collection_name
        self.llm_model = llm_model
        self.llm_url = llm_url.rstrip("/")
        self.embedder = get_embedding_engine()

        if self.embedder is None:
            raise RuntimeError("Embedding engine is not available")

        self._ensure_collection_exists()

    def _ensure_collection_exists(self) -> None:
        """Create collection if it doesn't exist."""
        if not self.client.collection_exists(self.collection_name):
            embedding_dim = self.embedder.embedding_dim
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"[knowledge_indexer] Created collection '{self.collection_name}' with {embedding_dim}-dim vectors")
        else:
            logger.info(f"[knowledge_indexer] Using existing collection '{self.collection_name}'")

    def _detect_file_type(self, file_path: Path) -> str:
        """
        Detect file type from extension.

        Returns:
            File type string (e.g., "markdown_doc", "python_file", "yaml_config", "service_file")
        """
        suffix = file_path.suffix.lower()

        type_map = {
            '.md': 'markdown_doc',
            '.txt': 'text_doc',
            '.py': 'python_file',
            '.yaml': 'yaml_config',
            '.yml': 'yaml_config',
            '.json': 'json_config',
            '.service': 'service_file',
            '.toml': 'toml_config',
        }

        return type_map.get(suffix, 'unknown')

    def _read_file_content(self, file_path: Path, max_lines: int = 10000) -> tuple[str, bool]:
        """
        Read file content with error handling.

        Args:
            file_path: Path to file
            max_lines: Maximum lines to read (truncate large files)

        Returns:
            Tuple of (content, truncated)

        Raises:
            IOError: If file cannot be read
            UnicodeDecodeError: If file encoding is unsupported
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            truncated = False
            if len(lines) > max_lines:
                content = ''.join(lines[:5000] + ['...\n[TRUNCATED]\n...'] + lines[-1000:])
                truncated = True
            else:
                content = ''.join(lines)

            return content, truncated

        except UnicodeDecodeError:
            logger.warning(f"[knowledge_indexer] Binary or unsupported encoding: {file_path}")
            raise
        except IOError as e:
            logger.error(f"[knowledge_indexer] Cannot read file {file_path}: {e}")
            raise

    def _generate_summary(self, file_path: Path, content: str, file_type: str) -> str:
        """
        Generate LLM summary of file content.

        Args:
            file_path: Path to file
            content: File content
            file_type: Detected file type

        Returns:
            Summary string
        """
        prompt = self._build_summary_prompt(file_path, content, file_type)

        try:
            response = requests.post(
                f"{self.llm_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 500,
                        "num_gpu": 999,
                        "main_gpu": 0,
                    },
                    "stream": False,
                },
                timeout=60,
            )
            response.raise_for_status()
            summary = response.json().get("response", "").strip()

            if not summary:
                logger.warning(f"[knowledge_indexer] Empty summary from LLM for {file_path}")
                return "[Summary generation failed: empty response]"

            return summary

        except requests.Timeout:
            logger.error(f"[knowledge_indexer] LLM timeout for {file_path}, retrying once...")
            try:
                response = requests.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.llm_model,
                        "prompt": prompt,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 500,
                        },
                        "stream": False,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                return response.json().get("response", "[Summary generation failed: timeout]").strip()
            except Exception as e:
                logger.error(f"[knowledge_indexer] LLM retry failed for {file_path}: {e}")
                return "[Summary generation failed: timeout]"

        except Exception as e:
            logger.error(f"[knowledge_indexer] LLM error for {file_path}: {e}")
            return f"[Summary generation failed: {type(e).__name__}]"

    def _build_summary_prompt(self, file_path: Path, content: str, file_type: str) -> str:
        """
        Build LLM prompt for summarization with file-type-specific hints.

        Args:
            file_path: Path to file
            content: File content
            file_type: Detected file type

        Returns:
            Prompt string
        """
        type_hints = {
            'python_file': 'List main classes and functions. Describe the module purpose.',
            'markdown_doc': 'List the main sections/headers. Describe the document purpose.',
            'yaml_config': 'List top-level configuration keys. Describe what is configured.',
            'json_config': 'List top-level keys. Describe what is configured.',
            'service_file': 'Describe the service: what it runs, dependencies, restart policy.',
            'toml_config': 'List sections and keys. Describe what is configured.',
        }

        hint = type_hints.get(file_type, 'Describe the file purpose and key content.')

        return f"""Summarize this {file_type} file concisely. Include: purpose, key topics, main components.
Be specific and factual. 3-6 sentences. {hint}

File: {file_path}
Content:
{content[:4000]}"""

    def _create_doc_id(self, file_path: Path) -> str:
        """
        Create deterministic document ID from file path.

        Args:
            file_path: Path to file

        Returns:
            UUID string
        """
        file_path_str = str(file_path.absolute())
        doc_id_hash = hashlib.sha256(file_path_str.encode()).digest()
        return str(UUID(bytes=doc_id_hash[:16]))

    def summarize_and_index(self, file_path: Path) -> Dict[str, Any]:
        """
        Read file, generate summary, index to Qdrant.

        Args:
            file_path: Path to file to index

        Returns:
            Dictionary with keys:
                - success: bool
                - summary: str (summary text or error message)
                - file_path: str
                - indexed_at: str (ISO timestamp)
                - error: Optional[str] (error message if failed)
        """
        file_path = Path(file_path).absolute()

        if not file_path.exists():
            logger.warning(f"[knowledge_indexer] File not found: {file_path}")
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": "File not found"
            }

        try:
            file_type = self._detect_file_type(file_path)
            file_size = file_path.stat().st_size
            mtime = file_path.stat().st_mtime

            content, truncated = self._read_file_content(file_path)

            summary = self._generate_summary(file_path, content, file_type)

            embedding = self.embedder.embed(summary)
            embedding_list = embedding.tolist()

            indexed_at = datetime.now().isoformat()
            doc_id = self._create_doc_id(file_path)

            payload = {
                "file_path": str(file_path),
                "file_type": file_type,
                "file_size": file_size,
                "indexed_mtime": mtime,
                "indexed_at": indexed_at,
                "summary": summary,
                "doc_id": doc_id,
                "truncated": truncated,
                "summary_failed": summary.startswith("[Summary generation failed"),
                "_text": summary,
            }

            point = PointStruct(
                id=doc_id,
                vector=embedding_list,
                payload=payload
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            logger.info(f"[knowledge_indexer] Indexed: {file_path} ({file_type}, {file_size} bytes)")

            return {
                "success": True,
                "summary": summary,
                "file_path": str(file_path),
                "indexed_at": indexed_at,
            }

        except UnicodeDecodeError:
            logger.warning(f"[knowledge_indexer] Skipping binary/unsupported file: {file_path}")
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": "Binary or unsupported encoding"
            }

        except IOError as e:
            logger.error(f"[knowledge_indexer] Permission denied or IO error: {file_path}: {e}")
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": f"IO error: {e}"
            }

        except Exception as e:
            logger.error(f"[knowledge_indexer] Unexpected error indexing {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": f"Unexpected error: {type(e).__name__}"
            }

    def get_indexed_files(self) -> List[str]:
        """
        Get list of all indexed file paths from Qdrant.

        Returns:
            List of absolute file path strings
        """
        try:
            all_paths = []
            offset = None

            while True:
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                points, next_offset = scroll_result

                for point in points:
                    file_path = point.payload.get("file_path")
                    if file_path:
                        all_paths.append(file_path)

                if next_offset is None:
                    break

                offset = next_offset

            logger.info(f"[knowledge_indexer] Retrieved {len(all_paths)} indexed files")
            return all_paths

        except Exception as e:
            logger.error(f"[knowledge_indexer] Error retrieving indexed files: {e}")
            return []

    def is_indexed(self, file_path: Path) -> bool:
        """
        Check if file exists in index.

        Args:
            file_path: Path to file

        Returns:
            True if indexed, False otherwise
        """
        doc_id = self._create_doc_id(Path(file_path).absolute())

        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[doc_id],
                with_payload=False,
                with_vectors=False
            )
            return len(points) > 0

        except Exception as e:
            logger.error(f"[knowledge_indexer] Error checking if indexed {file_path}: {e}")
            return False

    def is_stale(self, file_path: Path) -> bool:
        """
        Check if indexed version is older than filesystem.

        Args:
            file_path: Path to file

        Returns:
            True if indexed version is stale, False if up-to-date or not indexed
        """
        file_path = Path(file_path).absolute()

        if not file_path.exists():
            return False

        doc_id = self._create_doc_id(file_path)

        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[doc_id],
                with_payload=True,
                with_vectors=False
            )

            if not points:
                return False

            indexed_mtime = points[0].payload.get("indexed_mtime")
            if indexed_mtime is None:
                return True

            current_mtime = file_path.stat().st_mtime

            is_stale = current_mtime > indexed_mtime

            if is_stale:
                logger.info(f"[knowledge_indexer] Stale file detected: {file_path} "
                           f"(indexed: {indexed_mtime}, current: {current_mtime})")

            return is_stale

        except Exception as e:
            logger.error(f"[knowledge_indexer] Error checking staleness for {file_path}: {e}")
            return False

    def search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        doc_type_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search in knowledge base.

        Args:
            query: Search query text
            top_k: Number of results to return
            doc_type_filter: Optional filter by file_type (e.g., "markdown_doc", "python_file")

        Returns:
            List of result dictionaries with keys:
                - file_path: str
                - summary: str
                - file_type: str
                - similarity: float
                - metadata: dict (all payload fields)
        """
        try:
            query_embedding = self.embedder.embed(query)
            query_embedding_list = query_embedding.tolist()

            query_filter = None
            if doc_type_filter:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="file_type",
                            match=MatchValue(value=doc_type_filter)
                        )
                    ]
                )

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding_list,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True
            )

            formatted_results = []
            for hit in results:
                payload = hit.payload.copy()

                formatted_results.append({
                    'file_path': payload.get('file_path', ''),
                    'summary': payload.get('summary', ''),
                    'file_type': payload.get('file_type', 'unknown'),
                    'similarity': hit.score,
                    'metadata': payload,
                })

            logger.info(f"[knowledge_indexer] Search query='{query}' returned {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"[knowledge_indexer] Search error for query '{query}': {e}")
            return []


def get_knowledge_indexer(
    collection_name: str = "kloros_knowledge",
    llm_model: Optional[str] = None,
    llm_url: Optional[str] = None
) -> Optional[KnowledgeIndexer]:
    """
    Get or create KnowledgeIndexer instance.

    Args:
        collection_name: Qdrant collection name
        llm_model: Ollama model for summaries (default from env or qwen2.5-coder:14b)
        llm_url: Ollama server URL (default from env or http://100.67.244.66:11434)

    Returns:
        KnowledgeIndexer instance or None if dependencies unavailable
    """
    if not HAS_QDRANT:
        logger.warning("[knowledge_indexer] qdrant-client not installed, indexer disabled")
        return None

    try:
        from .vector_store_qdrant import get_qdrant_vector_store

        vector_store = get_qdrant_vector_store(collection_name=collection_name)
        if vector_store is None:
            logger.error("[knowledge_indexer] Failed to get Qdrant vector store")
            return None

        llm_model = llm_model or os.getenv("KLR_KNOWLEDGE_LLM_MODEL", "qwen2.5-coder:14b")
        llm_url = llm_url or os.getenv("KLR_KNOWLEDGE_LLM_URL", "http://100.67.244.66:11434")

        indexer = KnowledgeIndexer(
            qdrant_client=vector_store.client,
            collection_name=collection_name,
            llm_model=llm_model,
            llm_url=llm_url
        )

        return indexer

    except Exception as e:
        logger.error(f"[knowledge_indexer] Failed to create indexer: {e}")
        return None
