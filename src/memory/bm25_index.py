"""BM25 keyword-based index for conversation retrieval."""
from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi
import re


class BM25ConversationIndex:
    """BM25 index for keyword-based conversation retrieval."""

    def __init__(self):
        """Initialize BM25 index."""
        self.documents: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: BM25Okapi = None

    def tokenize(self, text: str) -> List[str]:
        """Simple tokenizer that splits on whitespace and punctuation.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens (lowercase)
        """
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r'\w+', text.lower())
        return tokens

    def add_documents(self, documents: List[Dict[str, Any]]):
        """Add documents to BM25 index.

        Args:
            documents: List of document dicts with 'id', 'document', 'metadata'
        """
        for doc in documents:
            self.documents.append(doc)
            tokens = self.tokenize(doc['document'])
            self.tokenized_corpus.append(tokens)

        # Rebuild BM25 index
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """Search for documents matching query keywords.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of documents ranked by BM25 score
        """
        if not self.bm25 or not self.documents:
            return []

        # Tokenize query
        query_tokens = self.tokenize(query)

        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)

        # Get top k indices
        top_indices = scores.argsort()[-k:][::-1]

        # Return documents with scores
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include docs with positive scores
                doc = self.documents[idx].copy()
                doc['bm25_score'] = float(scores[idx])
                results.append(doc)

        return results

    def clear(self):
        """Clear the index."""
        self.documents = []
        self.tokenized_corpus = []
        self.bm25 = None
