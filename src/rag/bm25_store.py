"""BM25 text retrieval store."""
import math
from typing import List, Dict, Any, Optional
from collections import defaultdict, Counter


class BM25Store:
    """BM25 retrieval using simple inverted index.

    Implements BM25 scoring for keyword-based retrieval.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 store.

        Args:
            k1: Term frequency saturation parameter
            b: Length normalization parameter
        """
        self.k1 = k1
        self.b = b

        # Index structures
        self.documents: Dict[str, Dict[str, Any]] = {}  # doc_id -> {text, meta}
        self.inverted_index: Dict[str, List[str]] = defaultdict(list)  # term -> [doc_ids]
        self.doc_freqs: Dict[str, int] = Counter()  # term -> number of docs containing it
        self.doc_lengths: Dict[str, int] = {}  # doc_id -> length
        self.avg_doc_length: float = 0.0
        self.num_docs: int = 0

    def add_documents(self, documents: List[Dict[str, Any]]):
        """Add documents to index.

        Args:
            documents: List of dicts with keys: id, text, meta (optional)
        """
        for doc in documents:
            self.add_document(doc["id"], doc["text"], doc.get("meta", {}))

    def add_document(self, doc_id: str, text: str, meta: Optional[Dict[str, Any]] = None):
        """Add single document to index.

        Args:
            doc_id: Document ID
            text: Document text
            meta: Optional metadata
        """
        # Store document
        self.documents[doc_id] = {
            "text": text,
            "meta": meta or {}
        }

        # Tokenize
        terms = self._tokenize(text)
        self.doc_lengths[doc_id] = len(terms)

        # Update inverted index
        unique_terms = set(terms)
        for term in unique_terms:
            self.inverted_index[term].append(doc_id)
            self.doc_freqs[term] += 1

        # Update stats
        self.num_docs += 1
        self.avg_doc_length = sum(self.doc_lengths.values()) / self.num_docs

    def search(self, query: str, k: int = 50) -> List[str]:
        """Search using BM25 scoring.

        Args:
            query: Query string
            k: Number of results to return

        Returns:
            List of document IDs ranked by BM25 score
        """
        query_terms = self._tokenize(query)

        # Compute BM25 scores
        scores = defaultdict(float)

        for term in query_terms:
            if term not in self.inverted_index:
                continue

            # IDF component
            df = self.doc_freqs[term]
            idf = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1.0)

            # Score each document containing this term
            for doc_id in self.inverted_index[term]:
                # Term frequency in document
                doc_terms = self._tokenize(self.documents[doc_id]["text"])
                tf = doc_terms.count(term)

                # Document length normalization
                doc_len = self.doc_lengths[doc_id]
                norm_factor = 1 - self.b + self.b * (doc_len / self.avg_doc_length)

                # BM25 score
                score = idf * (tf * (self.k1 + 1)) / (tf + self.k1 * norm_factor)
                scores[doc_id] += score

        # Rank by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _ in ranked[:k]]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict or None
        """
        if doc_id not in self.documents:
            return None

        doc = self.documents[doc_id]
        return {
            "id": doc_id,
            "text": doc["text"],
            "meta": doc["meta"]
        }

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        # Lowercase and split on non-alphanumeric
        import re
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        return tokens

    def clear(self):
        """Clear all documents from index."""
        self.documents.clear()
        self.inverted_index.clear()
        self.doc_freqs.clear()
        self.doc_lengths.clear()
        self.num_docs = 0
        self.avg_doc_length = 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics.

        Returns:
            Statistics dict
        """
        return {
            "num_docs": self.num_docs,
            "num_terms": len(self.inverted_index),
            "avg_doc_length": self.avg_doc_length,
            "total_terms": sum(self.doc_lengths.values())
        }
