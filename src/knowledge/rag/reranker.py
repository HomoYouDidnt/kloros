"""Reranking for improving retrieval quality."""
from typing import List, Dict, Any, Optional


class Reranker:
    """Reranks retrieved chunks using cross-encoder or heuristics."""

    def __init__(self, model_name: Optional[str] = None, device: str = "cpu"):
        """Initialize reranker.

        Args:
            model_name: Cross-encoder model name (e.g., 'cross-encoder/ms-marco-MiniLM-L-6-v2')
            device: Device for model
        """
        self.model_name = model_name
        self.model = None
        self.device = device

        if model_name:
            self._load_model()

    def _load_model(self):
        """Load cross-encoder model."""
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(self.model_name, device=self.device)
        except ImportError:
            print("[reranker] sentence-transformers not available, using heuristic reranking")
            self.model = None

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Rerank chunks by relevance to query.

        Args:
            query: Query string
            chunks: List of chunk dicts with 'text' key
            top_k: Number of top results to return (None = all)

        Returns:
            Reranked list of chunks with 'rerank_score' added
        """
        if not chunks:
            return []

        if self.model is not None:
            return self._rerank_with_model(query, chunks, top_k)
        else:
            return self._rerank_heuristic(query, chunks, top_k)

    def _rerank_with_model(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Rerank using cross-encoder model.

        Args:
            query: Query string
            chunks: Chunks to rerank
            top_k: Number to return

        Returns:
            Reranked chunks
        """
        # Prepare pairs
        pairs = [[query, chunk["text"]] for chunk in chunks]

        # Score
        scores = self.model.predict(pairs)

        # Add scores and sort
        for i, chunk in enumerate(chunks):
            chunk["rerank_score"] = float(scores[i])

        chunks_sorted = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)

        if top_k is not None:
            chunks_sorted = chunks_sorted[:top_k]

        return chunks_sorted

    def _rerank_heuristic(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Rerank using simple heuristic (term overlap).

        Args:
            query: Query string
            chunks: Chunks to rerank
            top_k: Number to return

        Returns:
            Reranked chunks
        """
        query_terms = set(query.lower().split())

        # Score by term overlap
        for chunk in chunks:
            chunk_terms = set(chunk["text"].lower().split())
            overlap = len(query_terms & chunk_terms)
            # Normalize by query length
            score = overlap / len(query_terms) if query_terms else 0.0
            chunk["rerank_score"] = score

        chunks_sorted = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)

        if top_k is not None:
            chunks_sorted = chunks_sorted[:top_k]

        return chunks_sorted


def rerank_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    top_k: Optional[int] = None,
    device: str = "cpu"
) -> List[Dict[str, Any]]:
    """Convenience function for reranking.

    Args:
        query: Query string
        chunks: Chunks to rerank
        model_name: Optional cross-encoder model
        top_k: Number of top results
        device: Device for model

    Returns:
        Reranked chunks
    """
    reranker = Reranker(model_name=model_name, device=device)
    return reranker.rerank(query, chunks, top_k=top_k)


def extract_best_spans(
    chunk: Dict[str, Any],
    query: str,
    max_spans: int = 2,
    context_window: int = 100
) -> List[str]:
    """Extract most relevant spans from chunk.

    Args:
        chunk: Chunk dict with 'text' key
        query: Query string
        max_spans: Maximum number of spans to extract
        context_window: Characters of context around match

    Returns:
        List of text spans
    """
    text = chunk["text"]
    query_terms = set(query.lower().split())

    # Find sentences/passages containing query terms
    import re
    sentences = re.split(r'[.!?]+', text)

    # Score sentences by term overlap
    scored = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        sent_terms = set(sent.lower().split())
        overlap = len(query_terms & sent_terms)
        if overlap > 0:
            scored.append((sent, overlap))

    # Sort by score
    scored.sort(key=lambda x: x[1], reverse=True)

    # Return top spans
    spans = [sent for sent, _ in scored[:max_spans]]
    return spans if spans else [text[:500]]  # Fallback to beginning
