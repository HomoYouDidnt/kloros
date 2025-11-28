"""Qdrant export for episodic memory summaries.

Drop-in replacement for ChromaDB exporter with better stability and lower memory usage.
"""

import os
import time
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

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
    HAS_QDRANT = False
    QdrantClient = None

from .storage import MemoryStore
from .models import EpisodeSummary
from .embeddings import get_embedding_engine

logger = logging.getLogger(__name__)


class QdrantMemoryExporter:
    """Export episodic memory summaries to Qdrant for semantic retrieval."""

    def __init__(self, memory_store: MemoryStore):
        """
        Initialize Qdrant exporter.

        Args:
            memory_store: MemoryStore instance for accessing episode summaries
        """
        self.store = memory_store
        self.client: Optional[QdrantClient] = None
        self.embedding_engine = None
        self.collections = {}

        self.qdrant_dir = os.getenv('KLOROS_QDRANT_DIR', '/home/kloros/.kloros/qdrant_data')
        self.server_url = os.getenv('KLR_QDRANT_URL', None)

        if self.server_url is None:
            try:
                import tomllib
                config_path = Path("/home/kloros/config/models.toml")
                if config_path.exists():
                    with open(config_path, "rb") as f:
                        config = tomllib.load(f)
                    self.server_url = config.get("vector_store", {}).get("server_url", None)
            except Exception as e:
                logger.debug(f"[qdrant_export] Could not read config: {e}")

        self._init_qdrant()

    def _init_qdrant(self) -> bool:
        """Initialize Qdrant client and collections."""
        if not HAS_QDRANT:
            logger.error("[qdrant_export] qdrant-client not installed")
            return False

        try:
            if self.server_url:
                logger.info(f"[qdrant_export] Using server mode: {self.server_url}")
                self.client = QdrantClient(url=self.server_url)
            else:
                os.makedirs(self.qdrant_dir, exist_ok=True)
                logger.info(f"[qdrant_export] Using file mode: {self.qdrant_dir}")
                self.client = QdrantClient(path=self.qdrant_dir)

            self.embedding_engine = get_embedding_engine()
            embedding_dim = self.embedding_engine.embedding_dim

            self._init_collections(embedding_dim)

            return True

        except Exception as e:
            logger.error(f"[qdrant_export] Qdrant initialization failed: {e}")
            return False

    def _init_collections(self, embedding_dim: int):
        """Initialize all Qdrant collections for memory system."""
        collections_config = {
            'summaries': {
                'name': 'kloros_summaries',
                'description': 'Episode summaries from episodic memory - daily/weekly rollups'
            },
            'dialogue': {
                'name': 'kloros_dialogue',
                'description': 'Individual user/agent utterances and tool replies'
            },
            'errors': {
                'name': 'kloros_errors',
                'description': 'Error traces, analyses, and remediation patterns'
            }
        }

        for key, config in collections_config.items():
            collection_name = config['name']

            if not self.client.collection_exists(collection_name):
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"[qdrant_export] Created collection '{collection_name}'")
            else:
                logger.info(f"[qdrant_export] Using existing collection '{collection_name}'")

            self.collections[key] = collection_name

        logger.info(f"[qdrant_export] Initialized {len(self.collections)} Qdrant collections")

    def _doc_id_to_uuid(self, doc_id: str) -> str:
        """Convert document ID to deterministic UUID string."""
        doc_id_hash = hashlib.sha256(doc_id.encode()).digest()
        return str(UUID(bytes=doc_id_hash[:16]))

    def export_recent_summaries(
        self,
        hours: float = 24.0,
        min_importance: float = 0.3
    ) -> Dict[str, Any]:
        """
        Export recent episode summaries to Qdrant.

        Args:
            hours: Time window for recent summaries
            min_importance: Minimum importance score to export

        Returns:
            Dictionary with export results
        """
        results = {
            "exported": 0,
            "skipped": 0,
            "errors": []
        }

        if not self.client or 'summaries' not in self.collections:
            results["errors"].append("Qdrant not initialized")
            return results

        try:
            cutoff_time = time.time() - (hours * 3600)
            summaries = self.store.get_summaries(
                limit=1000,
                min_importance=min_importance
            )

            recent_summaries = [
                s for s in summaries
                if s.created_at >= cutoff_time
            ]

            if not recent_summaries:
                return results

            collection_name = self.collections['summaries']

            existing_ids = set()
            try:
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=10000,
                    with_payload=False,
                    with_vectors=False
                )
                if scroll_result and scroll_result[0]:
                    existing_ids = {str(point.id) for point in scroll_result[0]}
            except Exception as e:
                logger.debug(f"[qdrant_export] Could not fetch existing IDs: {e}")

            points = []

            for summary in recent_summaries:
                doc_id = f"episode_{summary.episode_id}_summary_{summary.id}"
                point_id = self._doc_id_to_uuid(doc_id)

                if point_id in existing_ids:
                    results["skipped"] += 1
                    continue

                doc_text = self._format_summary_for_qdrant(summary)

                embedding = self.embedding_engine.embed(doc_text)
                embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

                payload = {
                    "episode_id": str(summary.episode_id),
                    "summary_id": str(summary.id),
                    "importance": float(summary.importance_score),
                    "created_at": float(summary.created_at),
                    "date": datetime.fromtimestamp(summary.created_at).strftime('%Y-%m-%d'),
                    "topics": json.dumps(summary.key_topics) if summary.key_topics else "[]",
                    "emotional_tone": summary.emotional_tone or "neutral",
                    "type": "episode_summary",
                    "_text": doc_text,
                    "_doc_id": doc_id
                }

                points.append(PointStruct(
                    id=point_id,
                    vector=embedding_list,
                    payload=payload
                ))

            if points:
                self.client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                results["exported"] = len(points)

        except Exception as e:
            results["errors"].append(f"Export failed: {e}")
            logger.error(f"[qdrant_export] Export failed: {e}")

        return results

    def _format_summary_for_qdrant(self, summary: EpisodeSummary) -> str:
        """
        Format episode summary for Qdrant storage.

        Args:
            summary: EpisodeSummary to format

        Returns:
            Formatted text document
        """
        parts = []

        date_str = datetime.fromtimestamp(summary.created_at).strftime('%Y-%m-%d %H:%M')
        parts.append(f"Conversation from {date_str}")

        if summary.key_topics:
            topics_str = ", ".join(summary.key_topics) if isinstance(summary.key_topics, list) else summary.key_topics
            parts.append(f"Topics: {topics_str}")

        if summary.emotional_tone:
            parts.append(f"Tone: {summary.emotional_tone}")

        parts.append(summary.summary_text)

        return " | ".join(parts)

    def create_daily_rollup(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Create daily rollup of episode summaries.

        Args:
            date: Date to rollup (default: yesterday)

        Returns:
            Dictionary with rollup results
        """
        results = {
            "rollup_created": False,
            "summaries_included": 0,
            "errors": []
        }

        if date is None:
            date = datetime.now() - timedelta(days=1)

        try:
            day_start = datetime(date.year, date.month, date.day)
            day_end = day_start + timedelta(days=1)

            summaries = self.store.get_summaries(limit=1000)
            day_summaries = [
                s for s in summaries
                if day_start.timestamp() <= s.created_at < day_end.timestamp()
            ]

            if not day_summaries:
                return results

            rollup_text = self._create_rollup_text(day_summaries, date, "daily")

            collection_name = self.collections['summaries']
            rollup_id_str = f"rollup_daily_{date.strftime('%Y_%m_%d')}"
            rollup_id = self._doc_id_to_uuid(rollup_id_str)

            embedding = self.embedding_engine.embed(rollup_text)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

            payload = {
                "type": "daily_rollup",
                "date": date.strftime('%Y-%m-%d'),
                "summaries_count": len(day_summaries),
                "created_at": time.time(),
                "importance": max(s.importance_score for s in day_summaries),
                "_text": rollup_text,
                "_doc_id": rollup_id_str
            }

            point = PointStruct(
                id=rollup_id,
                vector=embedding_list,
                payload=payload
            )

            self.client.upsert(
                collection_name=collection_name,
                points=[point]
            )

            results["rollup_created"] = True
            results["summaries_included"] = len(day_summaries)

        except Exception as e:
            results["errors"].append(f"Daily rollup failed: {e}")
            logger.error(f"[qdrant_export] Daily rollup failed: {e}")

        return results

    def create_weekly_rollup(self, week_start: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Create weekly rollup of daily rollups.

        Args:
            week_start: Start of week to rollup (default: last week)

        Returns:
            Dictionary with rollup results
        """
        results = {
            "rollup_created": False,
            "days_included": 0,
            "errors": []
        }

        if week_start is None:
            now = datetime.now()
            week_start = now - timedelta(days=now.weekday() + 7)

        try:
            week_end = week_start + timedelta(days=7)

            summaries = self.store.get_summaries(limit=10000)
            week_summaries = [
                s for s in summaries
                if week_start.timestamp() <= s.created_at < week_end.timestamp()
            ]

            if not week_summaries:
                return results

            rollup_text = self._create_rollup_text(week_summaries, week_start, "weekly")

            collection_name = self.collections['summaries']
            rollup_id_str = f"rollup_weekly_{week_start.strftime('%Y_W%U')}"
            rollup_id = self._doc_id_to_uuid(rollup_id_str)

            embedding = self.embedding_engine.embed(rollup_text)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

            payload = {
                "type": "weekly_rollup",
                "week_start": week_start.strftime('%Y-%m-%d'),
                "week_end": week_end.strftime('%Y-%m-%d'),
                "summaries_count": len(week_summaries),
                "created_at": time.time(),
                "importance": max(s.importance_score for s in week_summaries) if week_summaries else 0.0,
                "_text": rollup_text,
                "_doc_id": rollup_id_str
            }

            point = PointStruct(
                id=rollup_id,
                vector=embedding_list,
                payload=payload
            )

            self.client.upsert(
                collection_name=collection_name,
                points=[point]
            )

            results["rollup_created"] = True
            results["days_included"] = 7

        except Exception as e:
            results["errors"].append(f"Weekly rollup failed: {e}")
            logger.error(f"[qdrant_export] Weekly rollup failed: {e}")

        return results

    def _create_rollup_text(
        self,
        summaries: List[EpisodeSummary],
        date: datetime,
        rollup_type: str
    ) -> str:
        """
        Create consolidated rollup text from multiple summaries.

        Args:
            summaries: List of episode summaries to roll up
            date: Date of rollup
            rollup_type: "daily" or "weekly"

        Returns:
            Formatted rollup text
        """
        parts = []

        if rollup_type == "daily":
            parts.append(f"Daily Summary - {date.strftime('%Y-%m-%d')}")
        else:
            parts.append(f"Weekly Summary - Week of {date.strftime('%Y-%m-%d')}")

        parts.append(f"{len(summaries)} conversation episodes")

        all_topics = []
        for s in summaries:
            if s.key_topics:
                topics = s.key_topics if isinstance(s.key_topics, list) else [s.key_topics]
                all_topics.extend(topics)

        from collections import Counter
        topic_counts = Counter(all_topics)
        top_topics = topic_counts.most_common(5)

        if top_topics:
            parts.append("Primary topics: " + ", ".join(t for t, _ in top_topics))

        important = sorted(summaries, key=lambda s: s.importance_score, reverse=True)[:3]
        if important:
            parts.append("Key interactions:")
            for s in important:
                text = s.summary_text.split('.')[0] + '.'
                parts.append(f"- {text}")

        return " | ".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get Qdrant export statistics.

        Returns:
            Dictionary with statistics
        """
        stats = {
            "qdrant_initialized": self.client is not None,
            "collections": {}
        }

        if self.client:
            try:
                for key, collection_name in self.collections.items():
                    collection_info = self.client.get_collection(collection_name)
                    stats["collections"][key] = {
                        "count": collection_info.points_count or 0,
                        "name": collection_name
                    }
            except Exception as e:
                stats["error"] = str(e)

        return stats
