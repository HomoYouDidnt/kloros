"""
KOSMOS - Kosmos Obey Structured Memory of Operational Systems

KLoROS autonomous knowledge discovery and semantic memory system.

Reads files, generates LLM summaries, and indexes to Qdrant for semantic search.
Supports staleness detection and automatic re-indexing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
    )
    HAS_QDRANT = True
except ImportError:
    QdrantClient = None
    HAS_QDRANT = False

from .embeddings import get_embedding_engine
from .knowledge_lineage import get_lineage_log, LineageEvent
from reasoning.llm_router import get_router, LLMMode

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 60
LLM_RETRY_TIMEOUT_SECONDS = 120
MAX_LINES_BEFORE_TRUNCATE = 10000
TRUNCATE_HEAD_LINES = 5000
TRUNCATE_TAIL_LINES = 1000
SCROLL_BATCH_SIZE = 100
MAX_FILE_SIZE_MB = 100


class KOSMOS:
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
        collection_name: str = "kloros_knowledge"
    ):
        """
        Initialize KOSMOS - Kosmos Obey Structured Memory of Operational Systems.

        Args:
            qdrant_client: QdrantClient instance
            collection_name: Qdrant collection name
        """
        if not HAS_QDRANT:
            raise ImportError(
                "qdrant-client is not installed. "
                "Install it with: pip install qdrant-client"
            )

        self.client = qdrant_client
        self.collection_name = collection_name
        self.router = get_router()
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
            logger.info(f"[kosmos] Created collection '{self.collection_name}' with {embedding_dim}-dim vectors")
        else:
            logger.info(f"[kosmos] Using existing collection '{self.collection_name}'")

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

    def _read_file_content(self, file_path: Path, max_lines: int = MAX_LINES_BEFORE_TRUNCATE) -> tuple[str, bool]:
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
            ValueError: If file size exceeds MAX_FILE_SIZE_MB
        """
        file_size_bytes = file_path.stat().st_size
        max_file_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

        if file_size_bytes > max_file_size_bytes:
            raise ValueError(
                f"File size ({file_size_bytes / 1024 / 1024:.2f}MB) exceeds "
                f"maximum allowed size ({MAX_FILE_SIZE_MB}MB)"
            )

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            truncated = False
            if len(lines) > max_lines:
                content = ''.join(lines[:TRUNCATE_HEAD_LINES] + ['...\n[TRUNCATED]\n...'] + lines[-TRUNCATE_TAIL_LINES:])
                truncated = True
            else:
                content = ''.join(lines)

            return content, truncated

        except UnicodeDecodeError:
            logger.warning(f"[kosmos] Binary or unsupported encoding: {file_path}")
            raise
        except IOError as e:
            logger.error(f"[kosmos] Cannot read file {file_path}: {e}")
            raise

    def _generate_summary(self, file_path: Path, content: str, file_type: str) -> str:
        """
        Generate LLM summary of file content using LLMRouter with fallback.

        Args:
            file_path: Path to file
            content: File content
            file_type: Detected file type

        Returns:
            Summary string
        """
        prompt = self._build_summary_prompt(file_path, content, file_type)

        try:
            success, response, source = self.router.query(
                prompt=prompt,
                mode=LLMMode.LIVE,
                prefer_remote=False,
                stream=False
            )

            if success:
                summary = response.strip()
                if summary:
                    logger.info(f"[kosmos] Generated summary from {source} for {file_path}")
                    return summary
                else:
                    logger.warning(f"[kosmos] Empty summary from LLM for {file_path}")
                    return self._fallback_summary(content)
            else:
                logger.warning(f"[kosmos] LLM query failed: {response}, using fallback")
                return self._fallback_summary(content)

        except Exception as e:
            logger.error(f"[kosmos] LLM error for {file_path}: {e}, using fallback")
            return self._fallback_summary(content)

    def _fallback_summary(self, content: str, max_chars: int = 500) -> str:
        """
        Generate fallback summary from text extraction when LLM is unavailable.

        Args:
            content: File content
            max_chars: Maximum characters to extract

        Returns:
            Fallback summary string
        """
        summary = content[:max_chars].strip()
        if len(content) > max_chars:
            summary += "..."
        return summary

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
{content}"""

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

    def _extract_dates(self, content: str) -> Dict[str, Any]:
        """
        Extract temporal metadata from document content.

        Looks for common patterns:
        - **Date:** 2025-11-17
        - **Last Updated:** 2025-11-07 18:00 EST
        - **First Autonomous Spawn:** 2025-11-07 18:00:17 EST
        - created 2025-11-07
        - (modified: 2025-11-17)

        Args:
            content: Document text content

        Returns:
            Dictionary with keys:
                - document_date: str (primary date, ISO format or None)
                - last_updated: str (last update date, ISO format or None)
                - all_dates: List[str] (all dates found in YYYY-MM-DD format)
                - has_timeline: bool (whether doc contains timeline sections)
        """
        dates = {
            "document_date": None,
            "last_updated": None,
            "all_dates": [],
            "has_timeline": False
        }

        date_pattern = r'\*\*Date[*:\s]+(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, content[:2000])
        if match:
            dates["document_date"] = match.group(1)

        updated_pattern = r'\*\*Last Updated[*:\s]+(\d{4}-\d{2}-\d{2})'
        match = re.search(updated_pattern, content[:2000])
        if match:
            dates["last_updated"] = match.group(1)

        all_dates_pattern = r'\b(\d{4}-\d{2}-\d{2})\b'
        all_matches = re.findall(all_dates_pattern, content[:5000])
        dates["all_dates"] = sorted(list(set(all_matches)))

        if re.search(r'##\s+.*[Tt]imeline', content, re.IGNORECASE):
            dates["has_timeline"] = True

        return dates

    def _get_git_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get git information for a file.

        Returns:
            Dict with keys: tracked, repo_root, commit, branch, message
        """
        result = {
            'tracked': False,
            'repo_root': None,
            'commit': None,
            'branch': None,
            'message': None,
        }

        try:
            repo_root = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=2
            )

            if repo_root.returncode != 0:
                return result

            result['repo_root'] = repo_root.stdout.strip()
            result['tracked'] = True

            commit = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=2
            )

            if commit.returncode == 0:
                result['commit'] = commit.stdout.strip()[:12]

            branch = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=2
            )

            if branch.returncode == 0:
                result['branch'] = branch.stdout.strip()

            message = subprocess.run(
                ['git', 'log', '-1', '--pretty=%s', '--', str(file_path)],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=2
            )

            if message.returncode == 0 and message.stdout.strip():
                result['message'] = message.stdout.strip()

        except Exception as e:
            logger.debug(f"[kosmos] Git info error for {file_path}: {e}")

        return result

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_previous_version_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get information about previous version from Qdrant.

        Returns:
            Dict with keys: exists, version, content_hash, summary
        """
        try:
            doc_id = self._create_doc_id(file_path)
            results = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[doc_id]
            )

            if results:
                payload = results[0].payload
                return {
                    'exists': True,
                    'version': payload.get('version', 0),
                    'content_hash': payload.get('content_hash', ''),
                    'summary': payload.get('summary', ''),
                }
        except Exception:
            pass

        return {'exists': False, 'version': 0}

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
            logger.warning(f"[kosmos] File not found: {file_path}")
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

            temporal_metadata = self._extract_dates(content)

            summary = self._generate_summary(file_path, content, file_type)

            embedding = self.embedder.embed(summary)
            embedding_list = embedding.tolist()

            indexed_at = datetime.now().isoformat()
            doc_id = self._create_doc_id(file_path)

            # Get previous version info for change detection
            prev_info = self._get_previous_version_info(file_path)

            # Compute content and summary hashes
            content_hash = self._compute_content_hash(content)
            summary_hash = self._compute_content_hash(summary)

            # Get git information
            git_info = self._get_git_info(file_path)

            # Determine version number and change type
            if prev_info['exists']:
                version = prev_info['version'] + 1
                content_changed = (content_hash != prev_info['content_hash'])
                change_type = 'updated' if content_changed else 'reindexed'
            else:
                version = 1
                content_changed = True
                change_type = 'new'

            # Log lineage event
            try:
                lineage_log = get_lineage_log()
                lineage_event = LineageEvent(
                    timestamp=indexed_at,
                    event_type='indexed',
                    file_path=str(file_path),
                    version=version,
                    change_type=change_type,
                    content_hash=content_hash,
                    summary_hash=summary_hash,
                    git_commit=git_info.get('commit'),
                    git_message=git_info.get('message'),
                    indexed_by='auto',
                    summary_preview=summary[:100]
                )
                lineage_log.log_event(lineage_event)
                logger.debug(f"[kosmos] Logged lineage: {file_path} v{version} ({change_type})")
            except Exception as e:
                logger.warning(f"[kosmos] Failed to log lineage event: {e}")

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
                "document_date": temporal_metadata["document_date"],
                "last_updated": temporal_metadata["last_updated"],
                "all_dates": temporal_metadata["all_dates"],
                "has_timeline": temporal_metadata["has_timeline"],
                # Versioning metadata
                "version": version,
                "content_hash": content_hash,
                "summary_hash": summary_hash,
                "git_commit": git_info.get('commit'),
                "git_repo": git_info.get('repo_root'),
                "git_branch": git_info.get('branch'),
                "git_message": git_info.get('message'),
                # Lineage metadata
                "indexed_by": "auto",
                "change_type": change_type,
                "previous_version": prev_info['version'],
                "content_changed": content_changed,
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

            logger.info(f"[kosmos] Indexed: {file_path} ({file_type}, {file_size} bytes)")

            return {
                "success": True,
                "summary": summary,
                "file_path": str(file_path),
                "indexed_at": indexed_at,
            }

        except UnicodeDecodeError:
            logger.warning(f"[kosmos] Skipping binary/unsupported file: {file_path}")
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": "Binary or unsupported encoding"
            }

        except IOError as e:
            logger.error(f"[kosmos] Permission denied or IO error: {file_path}: {e}")
            return {
                "success": False,
                "summary": "",
                "file_path": str(file_path),
                "indexed_at": "",
                "error": f"IO error: {e}"
            }

        except Exception as e:
            logger.error(f"[kosmos] Unexpected error indexing {file_path}: {e}", exc_info=True)
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
                    limit=SCROLL_BATCH_SIZE,
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

            logger.info(f"[kosmos] Retrieved {len(all_paths)} indexed files")
            return all_paths

        except Exception as e:
            logger.error(f"[kosmos] Error retrieving indexed files: {e}")
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
            logger.error(f"[kosmos] Error checking if indexed {file_path}: {e}")
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
                logger.info(f"[kosmos] Stale file detected: {file_path} "
                           f"(indexed: {indexed_mtime}, current: {current_mtime})")

            return is_stale

        except Exception as e:
            logger.error(f"[kosmos] Error checking staleness for {file_path}: {e}")
            return False

    def search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        doc_type_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort_by_date: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Semantic search in knowledge base with optional temporal filtering.

        Args:
            query: Search query text
            top_k: Number of results to return
            doc_type_filter: Optional filter by file_type (e.g., "markdown_doc", "python_file")
            date_from: Optional start date filter (YYYY-MM-DD format)
            date_to: Optional end date filter (YYYY-MM-DD format)
            sort_by_date: If True, sort by document_date instead of similarity (newest first)

        Returns:
            List of result dictionaries with keys:
                - file_path: str
                - summary: str
                - file_type: str
                - similarity: float
                - metadata: dict (all payload fields including temporal data)
        """
        try:
            query_embedding = self.embedder.embed(query)
            query_embedding_list = query_embedding.tolist()

            filter_conditions = []

            if doc_type_filter:
                filter_conditions.append(
                    FieldCondition(
                        key="file_type",
                        match=MatchValue(value=doc_type_filter)
                    )
                )

            if date_from:
                filter_conditions.append(
                    FieldCondition(
                        key="document_date",
                        range={
                            "gte": date_from
                        }
                    )
                )

            if date_to:
                filter_conditions.append(
                    FieldCondition(
                        key="document_date",
                        range={
                            "lte": date_to
                        }
                    )
                )

            query_filter = None
            if filter_conditions:
                query_filter = Filter(must=filter_conditions)

            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding_list,
                limit=top_k * 2 if sort_by_date else top_k,
                query_filter=query_filter,
                with_payload=True
            ).points

            formatted_results = []
            for hit in results:
                payload = hit.payload.copy()

                formatted_results.append({
                    'file_path': payload.get('file_path', ''),
                    'summary': payload.get('summary', ''),
                    'file_type': payload.get('file_type', 'unknown'),
                    'similarity': hit.score,
                    'document_date': payload.get('document_date'),
                    'last_updated': payload.get('last_updated'),
                    'all_dates': payload.get('all_dates', []),
                    'has_timeline': payload.get('has_timeline', False),
                    'metadata': payload,
                })

            if sort_by_date:
                formatted_results.sort(
                    key=lambda x: x.get('document_date') or x.get('last_updated') or '0000-00-00',
                    reverse=True
                )
                formatted_results = formatted_results[:top_k]

            logger.info(f"[kosmos] Search query='{query}' date_range={date_from or 'any'} to {date_to or 'any'} returned {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"[kosmos] Search error for query '{query}': {e}")
            return []

    def build_timeline(
        self,
        query: str = "",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        doc_type: Optional[str] = "markdown_doc",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Build chronological timeline of documents.

        Args:
            query: Optional semantic query to filter relevant docs (empty = all docs)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            doc_type: Filter by document type (default: markdown_doc)
            limit: Maximum number of documents to return

        Returns:
            List of documents sorted chronologically (newest first), each with:
                - file_path, summary, document_date, last_updated, all_dates, etc.
        """
        try:
            if query:
                results = self.search_knowledge(
                    query=query,
                    top_k=limit,
                    doc_type_filter=doc_type,
                    date_from=date_from,
                    date_to=date_to,
                    sort_by_date=True
                )
            else:
                scroll_results, _ = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )

                results = []
                for point in scroll_results:
                    payload = point.payload

                    if doc_type and payload.get('file_type') != doc_type:
                        continue

                    doc_date = payload.get('document_date')

                    if date_from and doc_date and doc_date < date_from:
                        continue
                    if date_to and doc_date and doc_date > date_to:
                        continue

                    results.append({
                        'file_path': payload.get('file_path', ''),
                        'summary': payload.get('summary', ''),
                        'file_type': payload.get('file_type', 'unknown'),
                        'document_date': doc_date,
                        'last_updated': payload.get('last_updated'),
                        'all_dates': payload.get('all_dates', []),
                        'has_timeline': payload.get('has_timeline', False),
                        'metadata': payload,
                    })

                results.sort(
                    key=lambda x: x.get('document_date') or x.get('last_updated') or '0000-00-00',
                    reverse=True
                )

            logger.info(f"[kosmos] Built timeline with {len(results)} documents")
            return results

        except Exception as e:
            logger.error(f"[kosmos] Timeline build error: {e}")
            return []


def get_kosmos(
    collection_name: str = "kloros_knowledge"
) -> Optional[KnowledgeIndexer]:
    """
    Get or create KnowledgeIndexer instance.

    Uses LLMRouter for all LLM operations with fallback to text extraction.

    Args:
        collection_name: Qdrant collection name

    Returns:
        KnowledgeIndexer instance or None if dependencies unavailable
    """
    if not HAS_QDRANT:
        logger.warning("[kosmos] qdrant-client not installed, indexer disabled")
        return None

    try:
        from .vector_store_qdrant import get_qdrant_vector_store

        vector_store = get_qdrant_vector_store(collection_name=collection_name)
        if vector_store is None:
            logger.error("[kosmos] Failed to get Qdrant vector store")
            return None

        indexer = KOSMOS(
            qdrant_client=vector_store.client,
            collection_name=collection_name
        )

        return indexer

    except Exception as e:
        logger.error(f"[kosmos] Failed to create indexer: {e}")
        return None
