"""Hybrid retrieval combining BM25 and vector search."""
from typing import List, Dict, Any, Optional
from .rrf_fusion import reciprocal_rank_fusion


class HybridRetriever:
    """Combines BM25 keyword search with vector semantic search using RRF."""

    def __init__(
        self,
        vector_store,
        bm25_store,
        embedder=None,
        k_vec: int = 12,
        k_bm25: int = 50,
        rrf_k: int = 60
    ):
        """Initialize hybrid retriever.

        Args:
            vector_store: Vector store (ChromaDB, FAISS, etc.)
            bm25_store: BM25 text index
            embedder: Embedding model (optional, uses vector_store's if available)
            k_vec: Number of results from vector search
            k_bm25: Number of results from BM25 search
            rrf_k: RRF constant
        """
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.embedder = embedder
        self.k_vec = k_vec
        self.k_bm25 = k_bm25
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        top_k: int = 20,
        diversity_per_doc: int = 2
    ) -> List[Dict[str, Any]]:
        """Retrieve chunks using hybrid search.

        Args:
            query: Query string
            top_k: Number of chunks to return
            diversity_per_doc: Max chunks per source document

        Returns:
            List of chunk dicts with text, meta, score
        """
        # Get BM25 results
        bm25_ids = self.bm25_store.search(query, k=self.k_bm25)

        # Get vector results
        vector_ids = self._vector_search(query, k=self.k_vec)

        # Fuse with RRF
        fused_scores = reciprocal_rank_fusion(vector_ids, bm25_ids, k=self.rrf_k)

        # Rank by fused score
        ranked_ids = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)

        # Retrieve chunks with diversity constraint
        chunks = []
        doc_counts = {}

        for chunk_id, score in ranked_ids:
            # Get chunk
            chunk = self._get_chunk(chunk_id)
            if chunk is None:
                continue

            # Check diversity constraint
            doc_id = chunk.get("meta", {}).get("doc_id", chunk_id)
            if doc_counts.get(doc_id, 0) >= diversity_per_doc:
                continue

            # Add chunk
            chunk["score"] = score
            chunks.append(chunk)
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

            if len(chunks) >= top_k:
                break

        return chunks

    def _vector_search(self, query: str, k: int) -> List[str]:
        """Perform vector search.

        Args:
            query: Query string
            k: Number of results

        Returns:
            List of chunk IDs
        """
        # Encode query
        if self.embedder:
            query_vec = self.embedder.encode_queries([query])[0]
        else:
            # Try to use vector store's encoder
            query_vec = self.vector_store.encode_query(query)

        # Search
        results = self.vector_store.query(
            query_embeddings=[query_vec.tolist()] if hasattr(query_vec, 'tolist') else [query_vec],
            n_results=k
        )

        # Extract IDs
        if "ids" in results and len(results["ids"]) > 0:
            return results["ids"][0]

        return []

    def _get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get chunk by ID from either store.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk dict or None
        """
        # Try vector store first
        try:
            result = self.vector_store.get(ids=[chunk_id])
            if result and "documents" in result and len(result["documents"]) > 0:
                text = result["documents"][0]
                meta = result.get("metadatas", [{}])[0]
                return {
                    "id": chunk_id,
                    "text": text,
                    "meta": meta
                }
        except:
            pass

        # Try BM25 store
        doc = self.bm25_store.get_document(chunk_id)
        if doc:
            return doc

        return None


def retrieve_with_fusion(
    query: str,
    vector_store,
    bm25_store,
    embedder=None,
    k_vec: int = 12,
    k_bm25: int = 50,
    top_k: int = 20,
    diversity_per_doc: int = 2
) -> List[Dict[str, Any]]:
    """Convenience function for hybrid retrieval.

    Args:
        query: Query string
        vector_store: Vector store
        bm25_store: BM25 store
        embedder: Optional embedder
        k_vec: Vector search results
        k_bm25: BM25 search results
        top_k: Final number of results
        diversity_per_doc: Max chunks per document

    Returns:
        List of retrieved chunks
    """
    retriever = HybridRetriever(
        vector_store=vector_store,
        bm25_store=bm25_store,
        embedder=embedder,
        k_vec=k_vec,
        k_bm25=k_bm25
    )

    return retriever.retrieve(query, top_k=top_k, diversity_per_doc=diversity_per_doc)
