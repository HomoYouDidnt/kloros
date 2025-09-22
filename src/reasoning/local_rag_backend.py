"""Local RAG backend wrapper for KLoROS."""

from __future__ import annotations

from .base import ReasoningResult


class LocalRagBackend:
    """Local RAG backend that wraps src.rag module if available."""

    def __init__(self, **kwargs):
        """Initialize local RAG backend.

        Args:
            **kwargs: Passed to RAG constructor if needed

        Raises:
            RuntimeError: If RAG module is unavailable
        """
        try:
            from src import rag as rag_mod

            self.rag_mod = rag_mod
        except ImportError as e:
            raise RuntimeError("rag backend unavailable") from e

        self.rag_kwargs = kwargs

    def reply(self, transcript: str) -> ReasoningResult:
        """Generate a response using the RAG module.

        Args:
            transcript: Input transcript to process

        Returns:
            ReasoningResult with RAG response and sources
        """
        if not transcript.strip():
            return ReasoningResult(reply_text="", sources=[], meta={"empty_input": True})

        try:
            # Try common RAG entrypoints in order
            result = None
            sources = []

            # First try: instantiate RAG class and call answer method
            if hasattr(self.rag_mod, "RAG"):
                try:
                    rag_instance = self.rag_mod.RAG(**self.rag_kwargs)
                    if hasattr(rag_instance, "answer"):
                        # RAG.answer() returns {"response": text, "retrieved": docs, "prompt": prompt}
                        rag_result = rag_instance.answer(transcript)
                        if isinstance(rag_result, dict):
                            result = rag_result.get("response", "")
                            # Extract sources from retrieved documents
                            retrieved = rag_result.get("retrieved", [])
                            if isinstance(retrieved, list):
                                sources = [
                                    doc.get("content", str(doc))[:100] + "..."
                                    if isinstance(doc, dict) and len(doc.get("content", "")) > 100
                                    else str(doc)[:100] + "..."
                                    if len(str(doc)) > 100
                                    else str(doc)
                                    for doc in retrieved
                                ]
                        else:
                            result = str(rag_result)
                except Exception:
                    # If RAG instantiation or answer fails, try other methods
                    pass

            # Second try: direct function calls if available
            if result is None:
                if hasattr(self.rag_mod, "answer"):
                    answer_result = self.rag_mod.answer(transcript)
                    if isinstance(answer_result, tuple) and len(answer_result) >= 2:
                        result, sources = answer_result[0], answer_result[1]
                    else:
                        result = str(answer_result)
                elif hasattr(self.rag_mod, "query"):
                    query_result = self.rag_mod.query(transcript)
                    if isinstance(query_result, tuple) and len(query_result) >= 2:
                        result, sources = query_result[0], query_result[1]
                    else:
                        result = str(query_result)

            if result is None:
                raise RuntimeError("No compatible RAG entrypoint found")

            # Ensure sources is a list of strings
            if not isinstance(sources, list):
                sources = [str(sources)] if sources else []

            sources = [str(s) for s in sources]

            return ReasoningResult(
                reply_text=str(result),
                sources=sources,
                meta={"backend": "local_rag", "input_length": len(transcript)},
            )

        except Exception as e:
            # Fallback for any errors
            return ReasoningResult(
                reply_text=f"RAG processing failed: {str(e)}",
                sources=[],
                meta={"backend": "local_rag", "error": str(e)},
            )
