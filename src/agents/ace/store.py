"""ChromaDB-based storage for ACE bullets."""
from typing import Dict, Any, List, Optional
import time
import hashlib


class BulletStore:
    """Stores and retrieves ACE bullets using ChromaDB."""

    def __init__(self, chroma_client, embedder):
        """Initialize bullet store.

        Args:
            chroma_client: ChromaDB client
            embedder: Embedding function
        """
        self.client = chroma_client
        self.embedder = embedder

        # Create or get bullets collection
        self.bullets = self.client.get_or_create_collection(
            name="ace_bullets",
            embedding_function=embedder,
            metadata={"description": "ACE context hints"}
        )

        print("[ace] Bullet store initialized")

    def add_bullet(self, bullet: Any) -> str:
        """Add a bullet to the store.

        Args:
            bullet: Bullet object

        Returns:
            Bullet ID
        """
        self.bullets.upsert(
            ids=[bullet.id],
            documents=[bullet.text],
            metadatas=[{
                "domain": bullet.domain,
                "tags": ",".join(bullet.tags),
                "uses": bullet.stats["uses"],
                "wins": bullet.stats["wins"],
                "win_rate": bullet.win_rate,
                "created_at": bullet.stats["created_at"]
            }]
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
        where_filter = {}
        if domain:
            where_filter["domain"] = domain

        results = self.bullets.query(
            query_texts=[query],
            n_results=k,
            where=where_filter if where_filter else None
        )

        bullets = []
        if results and results['ids']:
            for i in range(len(results['ids'][0])):
                bullets.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': results['distances'][0][i] if 'distances' in results else None
                })

        # Sort by win_rate and recency
        bullets.sort(key=lambda b: (
            -b['metadata'].get('win_rate', 0.0),
            -b['metadata'].get('created_at', 0)
        ))

        return bullets[:k]

    def update_stats(self, bullet_id: str, success: bool):
        """Update bullet statistics after use.

        Args:
            bullet_id: Bullet ID
            success: Whether the bullet helped achieve success
        """
        try:
            # Get current bullet
            result = self.bullets.get(ids=[bullet_id])
            if not result or not result['ids']:
                return

            metadata = result['metadatas'][0]
            uses = metadata.get('uses', 0) + 1
            wins = metadata.get('wins', 0) + (1 if success else 0)
            win_rate = wins / uses if uses > 0 else 0.0

            # Update metadata
            self.bullets.update(
                ids=[bullet_id],
                metadatas=[{
                    **metadata,
                    "uses": uses,
                    "wins": wins,
                    "win_rate": win_rate,
                    "last_used": time.time()
                }]
            )

        except Exception as e:
            print(f"[ace] Failed to update stats for {bullet_id}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get overall bullet statistics.

        Returns:
            Statistics dict
        """
        try:
            all_bullets = self.bullets.get()
            total_bullets = len(all_bullets['ids']) if all_bullets['ids'] else 0

            # Calculate aggregate stats
            total_uses = 0
            total_wins = 0
            domains = set()

            if all_bullets and all_bullets['metadatas']:
                for meta in all_bullets['metadatas']:
                    total_uses += meta.get('uses', 0)
                    total_wins += meta.get('wins', 0)
                    domains.add(meta.get('domain', 'unknown'))

            return {
                "total_bullets": total_bullets,
                "total_uses": total_uses,
                "total_wins": total_wins,
                "domains": list(domains),
                "overall_win_rate": total_wins / total_uses if total_uses > 0 else 0.0
            }

        except Exception as e:
            print(f"[ace] Failed to get stats: {e}")
            return {"error": str(e)}
