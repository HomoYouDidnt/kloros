"""Qdrant-based storage for ACE bullets.

Drop-in replacement for ChromaDB BulletStore with better stability.
"""
from typing import Dict, Any, List, Optional
import time
import hashlib
import logging
from uuid import UUID

try:
    from src.orchestration.core.umn_bus import UMNPub as ChemPub
    HAS_CHEMBUS = True
except ImportError:
    ChemPub = None
    HAS_CHEMBUS = False

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

from kloros_memory.embeddings import get_embedding_engine

logger = logging.getLogger(__name__)


class QdrantBulletStore:
    """Stores and retrieves ACE bullets using Qdrant."""

    def __init__(self, qdrant_client: QdrantClient, collection_name: str = "ace_bullets"):
        """Initialize bullet store.

        Args:
            qdrant_client: Qdrant client instance
            collection_name: Name of the collection (default: ace_bullets)
        """
        if not HAS_QDRANT:
            raise ImportError("qdrant-client is required for QdrantBulletStore")

        self.client = qdrant_client
        self.collection_name = collection_name
        self.embedding_engine = get_embedding_engine()

        embedding_dim = self.embedding_engine.embedding_dim

        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"[ace] Created Qdrant collection '{collection_name}'")
        else:
            logger.debug(f"[ace] Using existing collection '{collection_name}'")

        # Initialize ChemBus publisher for operation signals
        self.chem_pub = ChemPub() if HAS_CHEMBUS else None
        if self.chem_pub:
            logger.debug("[ace] ChemBus signal emission enabled")

        print("[ace] Bullet store initialized (Qdrant)")

    def _doc_id_to_uuid(self, doc_id: str) -> str:
        """Convert document ID to deterministic UUID string."""
        doc_id_hash = hashlib.sha256(doc_id.encode()).digest()
        return str(UUID(bytes=doc_id_hash[:16]))

    def add_bullet(self, bullet: Any) -> str:
        """Add a bullet to the store.

        Args:
            bullet: Bullet object

        Returns:
            Bullet ID
        """
        start_time = time.time()

        embedding = self.embedding_engine.embed(bullet.text)
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

        point_id = self._doc_id_to_uuid(bullet.id)

        payload = {
            "domain": bullet.domain,
            "tags": ",".join(bullet.tags),
            "uses": bullet.stats["uses"],
            "wins": bullet.stats["wins"],
            "win_rate": bullet.win_rate,
            "created_at": bullet.stats["created_at"],
            "_text": bullet.text,
            "_doc_id": bullet.id
        }

        point = PointStruct(
            id=point_id,
            vector=embedding_list,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

        # Emit ChemBus signal
        latency_ms = (time.time() - start_time) * 1000
        if self.chem_pub:
            self.chem_pub.emit(
                signal="Q_ACE_STORE_BULLET",
                ecosystem="ace",
                facts={
                    "bullet_id": bullet.id,
                    "domain": bullet.domain,
                    "tags": list(bullet.tags),
                    "win_rate": bullet.win_rate,
                    "latency_ms": round(latency_ms, 2)
                }
            )

        return bullet.id

    def retrieve_bullets(self, query: str, domain: Optional[str] = None,
                        k: int = 8) -> List[Dict[str, Any]]:
        """Retrieve relevant bullets for a query.

        Args:
            query: Query to match against
            domain: Optional domain filter
            k: Number of bullets to retrieve

        Returns:
            List of bullet dicts with metadata
        """
        start_time = time.time()

        query_filter = None

        if domain:
            query_filter = Filter(
                must=[FieldCondition(
                    key="domain",
                    match=MatchValue(value=domain)
                )]
            )

        query_embedding = self.embedding_engine.embed(query)
        query_embedding_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)

        collection_info = self.client.get_collection(self.collection_name)
        collection_count = collection_info.points_count or 0

        if collection_count == 0:
            return []

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding_list,
            limit=min(k, collection_count),
            query_filter=query_filter,
            with_payload=True
        )

        bullets = []
        for hit in results:
            payload = hit.payload.copy()
            text = payload.pop("_text", "")
            doc_id = payload.pop("_doc_id", str(hit.id))

            bullets.append({
                'id': doc_id,
                'text': text,
                'metadata': payload,
                'distance': 1.0 - hit.score  # Qdrant returns cosine similarity, convert to distance
            })

        bullets.sort(key=lambda b: (
            -b['metadata'].get('win_rate', 0.0),
            -b['metadata'].get('created_at', 0)
        ))

        final_bullets = bullets[:k]

        # Emit ChemBus signal
        latency_ms = (time.time() - start_time) * 1000
        if self.chem_pub:
            avg_win_rate = sum(b['metadata'].get('win_rate', 0.0) for b in final_bullets) / len(final_bullets) if final_bullets else 0.0
            self.chem_pub.emit(
                signal="Q_ACE_RETRIEVE",
                ecosystem="ace",
                facts={
                    "query": query[:100],  # Truncate query
                    "domain": domain,
                    "k_requested": k,
                    "k_returned": len(final_bullets),
                    "avg_win_rate": round(avg_win_rate, 3),
                    "latency_ms": round(latency_ms, 2)
                }
            )

        return final_bullets

    def update_stats(self, bullet_id: str, success: bool):
        """Update bullet statistics after use.

        Args:
            bullet_id: Bullet ID
            success: Whether the bullet helped achieve success
        """
        start_time = time.time()
        try:
            point_id = self._doc_id_to_uuid(bullet_id)

            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False
            )

            if not points:
                return

            point = points[0]
            metadata = point.payload.copy()

            uses = metadata.get('uses', 0) + 1
            wins = metadata.get('wins', 0) + (1 if success else 0)
            win_rate = wins / uses if uses > 0 else 0.0

            metadata.update({
                "uses": uses,
                "wins": wins,
                "win_rate": win_rate,
                "last_used": time.time()
            })

            self.client.set_payload(
                collection_name=self.collection_name,
                payload=metadata,
                points=[point_id]
            )

            # Emit ChemBus signal
            latency_ms = (time.time() - start_time) * 1000
            if self.chem_pub:
                self.chem_pub.emit(
                    signal="Q_ACE_UPDATE_STATS",
                    ecosystem="ace",
                    facts={
                        "bullet_id": bullet_id,
                        "success": success,
                        "new_win_rate": round(win_rate, 3),
                        "uses": uses,
                        "wins": wins,
                        "latency_ms": round(latency_ms, 2)
                    }
                )

        except Exception as e:
            logger.error(f"[ace] Failed to update stats for {bullet_id}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get overall bullet statistics.

        Returns:
            Statistics dict
        """
        try:
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )

            if not scroll_result or not scroll_result[0]:
                return {
                    "total_bullets": 0,
                    "total_uses": 0,
                    "total_wins": 0,
                    "domains": [],
                    "overall_win_rate": 0.0
                }

            points = scroll_result[0]
            total_bullets = len(points)

            total_uses = 0
            total_wins = 0
            domains = set()

            for point in points:
                metadata = point.payload
                total_uses += metadata.get('uses', 0)
                total_wins += metadata.get('wins', 0)
                domains.add(metadata.get('domain', 'unknown'))

            return {
                "total_bullets": total_bullets,
                "total_uses": total_uses,
                "total_wins": total_wins,
                "domains": list(domains),
                "overall_win_rate": total_wins / total_uses if total_uses > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"[ace] Failed to get stats: {e}")
            return {"error": str(e)}
