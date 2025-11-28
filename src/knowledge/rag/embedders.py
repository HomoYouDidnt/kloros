"""Advanced embedding models for RAG."""
import numpy as np
from typing import List, Optional, Dict, Any


class DualEmbedder:
    """Dual encoder for queries and documents.

    Uses separate encoders optimized for query and document embedding.
    """

    def __init__(
        self,
        query_model: Optional[str] = None,
        doc_model: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: int = 32,
        truncate_dim: Optional[int] = None,
        trust_remote_code: Optional[bool] = None
    ):
        """Initialize dual embedder.

        Args:
            query_model: Model for encoding queries (defaults to SSOT config)
            doc_model: Model for encoding documents (defaults to query_model)
            device: Device ('cuda' or 'cpu')
            batch_size: Batch size for encoding
            truncate_dim: Truncate embeddings to this dimension
        """
        # Get defaults from SSOT config if not provided
        if query_model is None:
            from src.config.models_config import get_embedder_model
            query_model = get_embedder_model()
        if trust_remote_code is None:
            from src.config.models_config import get_embedder_trust_remote_code
            trust_remote_code = get_embedder_trust_remote_code()

        self.query_model_name = query_model
        self.doc_model_name = doc_model or query_model
        self.device = device or self._get_device()
        self.batch_size = batch_size
        self.truncate_dim = truncate_dim
        self.trust_remote_code = trust_remote_code

        self._load_models()

    def _get_device(self) -> str:
        """Get best available device with intelligent GPU selection.

        Selects the GPU with the most available memory. Falls back to CPU
        if all GPUs are heavily loaded (>90% used).

        Returns:
            Device string ('cuda:0', 'cuda:1', or 'cpu')
        """
        try:
            import torch
            if not torch.cuda.is_available():
                return "cpu"

            # Check all available GPUs and select the one with most free memory
            device_count = torch.cuda.device_count()
            if device_count == 0:
                return "cpu"

            max_free_memory = 0
            best_device = 0

            for i in range(device_count):
                try:
                    # Get memory stats for this GPU
                    total_mem = torch.cuda.get_device_properties(i).total_memory
                    reserved = torch.cuda.memory_reserved(i)
                    allocated = torch.cuda.memory_allocated(i)
                    free = total_mem - max(reserved, allocated)

                    # Track GPU with most free memory
                    if free > max_free_memory:
                        max_free_memory = free
                        best_device = i
                except Exception:
                    continue

            # Calculate free percentage for best GPU
            total_mem = torch.cuda.get_device_properties(best_device).total_memory
            free_pct = (max_free_memory / total_mem) * 100

            # If best GPU has <10% free, use CPU instead
            if free_pct < 10:
                return "cpu"

            return f"cuda:{best_device}"

        except ImportError:
            return "cpu"

    def _load_models(self):
        """Load embedding models with OOM fallback to CPU."""
        try:
            from sentence_transformers import SentenceTransformer
            import torch

            # Try loading on selected device first
            try:
                self.query_encoder = SentenceTransformer(
                    self.query_model_name,
                    device=self.device,
                    trust_remote_code=self.trust_remote_code
                )

                if self.doc_model_name == self.query_model_name:
                    self.doc_encoder = self.query_encoder
                else:
                    self.doc_encoder = SentenceTransformer(
                        self.doc_model_name,
                        device=self.device,
                        trust_remote_code=self.trust_remote_code
                    )

            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                # OOM on GPU - fallback to CPU
                if "out of memory" in str(e).lower() or "CUDA" in str(e):
                    import logging
                    logging.warning(
                        f"GPU OOM when loading embeddings on {self.device}. "
                        f"Falling back to CPU."
                    )
                    self.device = "cpu"

                    # Retry on CPU
                    self.query_encoder = SentenceTransformer(
                        self.query_model_name,
                        device="cpu",
                        trust_remote_code=self.trust_remote_code
                    )

                    if self.doc_model_name == self.query_model_name:
                        self.doc_encoder = self.query_encoder
                    else:
                        self.doc_encoder = SentenceTransformer(
                            self.doc_model_name,
                            device="cpu",
                            trust_remote_code=self.trust_remote_code
                        )
                else:
                    raise

        except ImportError as e:
            raise ImportError(
                "sentence-transformers required for embeddings. "
                "Install with: pip install sentence-transformers"
            ) from e

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        """Encode queries.

        Args:
            queries: List of query strings

        Returns:
            Embedding matrix (n_queries, embedding_dim)
        """
        embeddings = self.query_encoder.encode(
            queries,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        return self._truncate_embeddings(embeddings)

    def encode_documents(self, documents: List[str]) -> np.ndarray:
        """Encode documents.

        Args:
            documents: List of document strings

        Returns:
            Embedding matrix (n_docs, embedding_dim)
        """
        embeddings = self.doc_encoder.encode(
            documents,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        return self._truncate_embeddings(embeddings)

    def _truncate_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Truncate embeddings to specified dimension.

        Args:
            embeddings: Full embeddings

        Returns:
            Truncated embeddings
        """
        if self.truncate_dim and self.truncate_dim < embeddings.shape[1]:
            return embeddings[:, :self.truncate_dim]
        return embeddings

    def get_embedding_dim(self) -> int:
        """Get embedding dimension.

        Returns:
            Embedding dimension
        """
        if self.truncate_dim:
            return self.truncate_dim
        return self.query_encoder.get_sentence_embedding_dimension()


class CachedEmbedder:
    """Embedder with LRU cache for repeated queries."""

    def __init__(
        self,
        base_embedder: DualEmbedder,
        cache_size: int = 1000
    ):
        """Initialize cached embedder.

        Args:
            base_embedder: Base embedder to wrap
            cache_size: Maximum cache size
        """
        self.base_embedder = base_embedder
        self.cache_size = cache_size
        self._query_cache: Dict[str, np.ndarray] = {}
        self._cache_order: List[str] = []

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        """Encode queries with caching.

        Args:
            queries: Query strings

        Returns:
            Embeddings
        """
        embeddings = []
        uncached = []
        uncached_indices = []

        # Check cache
        for i, query in enumerate(queries):
            if query in self._query_cache:
                embeddings.append(self._query_cache[query])
            else:
                embeddings.append(None)
                uncached.append(query)
                uncached_indices.append(i)

        # Encode uncached
        if uncached:
            new_embeddings = self.base_embedder.encode_queries(uncached)

            for i, query in enumerate(uncached):
                emb = new_embeddings[i]
                self._add_to_cache(query, emb)
                embeddings[uncached_indices[i]] = emb

        return np.array(embeddings)

    def encode_documents(self, documents: List[str]) -> np.ndarray:
        """Encode documents (no caching for docs).

        Args:
            documents: Document strings

        Returns:
            Embeddings
        """
        return self.base_embedder.encode_documents(documents)

    def _add_to_cache(self, query: str, embedding: np.ndarray):
        """Add query to cache with LRU eviction.

        Args:
            query: Query string
            embedding: Query embedding
        """
        # Evict if needed
        if len(self._query_cache) >= self.cache_size:
            oldest = self._cache_order.pop(0)
            del self._query_cache[oldest]

        # Add to cache
        self._query_cache[query] = embedding
        self._cache_order.append(query)

    def get_embedding_dim(self) -> int:
        """Get embedding dimension.

        Returns:
            Embedding dimension
        """
        return self.base_embedder.get_embedding_dim()


def create_embedder(
    model_name: Optional[str] = None,
    use_cache: bool = True,
    **kwargs
) -> DualEmbedder:
    """Factory function to create embedder.

    Args:
        model_name: Model name (defaults to SSOT config)
        use_cache: Use caching
        **kwargs: Additional arguments for DualEmbedder

    Returns:
        Embedder instance
    """
    # Get model from SSOT if not provided
    if model_name is None:
        from src.config.models_config import get_embedder_model
        model_name = get_embedder_model()

    base = DualEmbedder(query_model=model_name, **kwargs)

    if use_cache:
        return CachedEmbedder(base)

    return base
