"""
Embedding engine for KLoROS semantic memory.

Provides vector embeddings for events, summaries, and queries using
sentence-transformers for local, fast, and accurate semantic representation.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None
    HAS_SENTENCE_TRANSFORMERS = False

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    """
    Semantic embedding engine for KLoROS memory.

    Features:
    - Local sentence-transformers model (no API calls)
    - Embedding caching for performance
    - Batch processing support
    - Configurable model selection
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",  # 384-dim, fast, accurate
        cache_dir: Optional[Path] = None,
        device: str = "cpu",
        trust_remote_code: bool = False,
        truncate_dim: Optional[int] = None,
        max_cache_size: int = 10000
    ):
        """
        Initialize embedding engine.

        Args:
            model_name: SentenceTransformer model name
                       - all-MiniLM-L6-v2: 384 dims, 14KB model, very fast (default)
                       - all-mpnet-base-v2: 768 dims, 47KB model, most accurate
                       - paraphrase-MiniLM-L3-v2: 384 dims, tiny, ultra-fast
            cache_dir: Directory for embedding cache
            device: "cpu" or "cuda" for GPU acceleration
            trust_remote_code: Allow custom code from model (required for some models like nomic-ai)
            truncate_dim: Truncate embeddings to this dimension (for Matryoshka models like Nomic)
            max_cache_size: Maximum number of embeddings to cache (LRU eviction, default 10000)
        """
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install it with: pip install sentence-transformers"
            )

        self.model_name = model_name
        self.device = device
        self.truncate_dim = truncate_dim
        self.cache_dir = cache_dir or Path("~/.kloros/embedding_cache").expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load model
        logger.info(f"[embeddings] Loading model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device, trust_remote_code=trust_remote_code)
        self.full_embedding_dim = self.model.get_sentence_embedding_dimension()
        self.embedding_dim = truncate_dim if truncate_dim else self.full_embedding_dim

        if truncate_dim and truncate_dim < self.full_embedding_dim:
            logger.info(f"[embeddings] Model loaded: {self.full_embedding_dim} dims → truncating to {self.embedding_dim} dims")
        else:
            logger.info(f"[embeddings] Model loaded: {self.embedding_dim} dimensions")

        # In-memory LRU cache for frequently accessed embeddings
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    def embed(
        self,
        text: Union[str, List[str]],
        use_cache: bool = True,
        normalize: bool = True
    ) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Generate embedding(s) for text.

        Args:
            text: Single string or list of strings to embed
            use_cache: Whether to use embedding cache
            normalize: Whether to L2-normalize embeddings (recommended for cosine similarity)

        Returns:
            numpy array (single text) or list of arrays (multiple texts)
        """
        is_batch = isinstance(text, list)
        texts = text if is_batch else [text]

        embeddings = []
        uncached_texts = []
        uncached_indices = []

        # Check cache
        for i, t in enumerate(texts):
            if use_cache:
                cache_key = self._get_cache_key(t)
                if cache_key in self._cache:
                    embeddings.append(self._cache[cache_key])
                    self._cache.move_to_end(cache_key)
                    self._cache_hits += 1
                    continue

            # Need to compute this one
            uncached_texts.append(t)
            uncached_indices.append(i)
            embeddings.append(None)  # Placeholder
            self._cache_misses += 1

        # Compute uncached embeddings in batch
        if uncached_texts:
            new_embeddings = self.model.encode(
                uncached_texts,
                normalize_embeddings=normalize,
                show_progress_bar=False,
                batch_size=32
            )

            # Truncate if needed (Matryoshka representation)
            if self.truncate_dim and self.truncate_dim < self.full_embedding_dim:
                new_embeddings = [emb[:self.truncate_dim] for emb in new_embeddings]

            # Fill in results and update cache
            for idx, emb in zip(uncached_indices, new_embeddings):
                embeddings[idx] = emb
                if use_cache:
                    cache_key = self._get_cache_key(texts[idx])

                    if len(self._cache) >= self._max_cache_size:
                        self._cache.popitem(last=False)
                        self._cache_evictions += 1

                    self._cache[cache_key] = emb
                    self._cache.move_to_end(cache_key)

        # Return single or batch
        if is_batch:
            return embeddings
        else:
            return embeddings[0]

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        normalize: bool = True,
        show_progress: bool = False
    ) -> List[np.ndarray]:
        """
        Efficiently embed large batches of text.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            normalize: Whether to L2-normalize
            show_progress: Whether to show progress bar

        Returns:
            List of embeddings
        """
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
            batch_size=batch_size
        )

        # Truncate if needed (Matryoshka representation)
        if self.truncate_dim and self.truncate_dim < self.full_embedding_dim:
            embeddings = [emb[:self.truncate_dim] for emb in embeddings]

        return list(embeddings)

    def similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        metric: str = "cosine"
    ) -> float:
        """
        Calculate similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            metric: "cosine" or "euclidean"

        Returns:
            Similarity score (0-1 for cosine, distance for euclidean)
        """
        if metric == "cosine":
            # Cosine similarity (assumes normalized vectors)
            return float(np.dot(embedding1, embedding2))
        elif metric == "euclidean":
            # Euclidean distance (lower is more similar)
            return float(np.linalg.norm(embedding1 - embedding2))
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: List[np.ndarray],
        top_k: int = 5,
        threshold: Optional[float] = None
    ) -> List[tuple[int, float]]:
        """
        Find most similar embeddings to query.

        Args:
            query_embedding: Query vector
            candidate_embeddings: List of candidate vectors
            top_k: Number of results to return
            threshold: Minimum similarity threshold (cosine)

        Returns:
            List of (index, similarity_score) tuples, sorted by similarity
        """
        # Compute similarities
        similarities = [
            (i, self.similarity(query_embedding, emb))
            for i, emb in enumerate(candidate_embeddings)
        ]

        # Filter by threshold
        if threshold is not None:
            similarities = [(i, score) for i, score in similarities if score >= threshold]

        # Sort and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0

        return {
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache_size,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_evictions": self._cache_evictions,
            "hit_rate": hit_rate,
            "embedding_dim": self.embedding_dim,
            "model_name": self.model_name
        }

    def clear_cache(self):
        """Clear embedding cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0
        logger.info("[embeddings] Cache cleared")


# Global embedding engine instance
_embedding_engine: Optional[EmbeddingEngine] = None


def get_embedding_engine(
    model_name: Optional[str] = None,
    force_reload: bool = False
) -> Optional[EmbeddingEngine]:
    """
    Get or create global embedding engine instance.

    Args:
        model_name: Model to use (default from env or all-MiniLM-L6-v2)
        force_reload: Force reload of model

    Returns:
        EmbeddingEngine instance or None if sentence-transformers is not available
    """
    global _embedding_engine

    if not HAS_SENTENCE_TRANSFORMERS:
        logger.warning("[embeddings] sentence-transformers not installed, embeddings disabled")
        return None

    if _embedding_engine is None or force_reload:
        # Load config from models.toml directly
        truncate_dim = None
        trust_remote_code = False

        try:
            import tomllib
            config_path = Path("/home/kloros/config/models.toml")
            if config_path.exists():
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)

                embeddings_config = config.get("embeddings", {})
                model_name = model_name or embeddings_config.get("model", "all-MiniLM-L6-v2")
                truncate_dim = embeddings_config.get("truncate_dim")
                trust_remote_code = embeddings_config.get("trust_remote_code", False)

                logger.info(f"[embeddings] Loaded from SSOT: model={model_name}, truncate_dim={truncate_dim}")
            else:
                # Fallback to env vars if config file not found
                model_name = model_name or os.getenv("KLR_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
                trust_remote_code = os.getenv("KLR_EMBEDDING_TRUST_REMOTE_CODE", "false").lower() == "true"
        except Exception as e:
            logger.warning(f"[embeddings] Could not load config: {e}, using defaults")
            model_name = model_name or os.getenv("KLR_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            trust_remote_code = os.getenv("KLR_EMBEDDING_TRUST_REMOTE_CODE", "false").lower() == "true"

        device = os.getenv("KLR_EMBEDDING_DEVICE", "cpu")

        try:
            _embedding_engine = EmbeddingEngine(
                model_name=model_name,
                device=device,
                trust_remote_code=trust_remote_code,
                truncate_dim=truncate_dim
            )
        except Exception as e:
            logger.error(f"[embeddings] Failed to load embedding engine: {e}")
            return None

    return _embedding_engine
