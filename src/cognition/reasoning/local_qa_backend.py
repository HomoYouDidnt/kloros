"""Local QA backend wrapper for KLoROS."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import ReasoningResult


class LocalQaBackend:
    """Local QA backend that wraps rag_pipeline.pipeline.qa module if available."""

    def __init__(self, config_path: Optional[str] = None, **kwargs):
        """Initialize local QA backend.

        Args:
            config_path: Path to QA configuration file
            **kwargs: Additional configuration options

        Raises:
            RuntimeError: If QA module is unavailable
        """
        try:
            from src.knowledge.rag_pipeline.pipeline import qa as qa_mod

            self.qa_mod = qa_mod
        except ImportError as e:
            raise RuntimeError("qa backend unavailable") from e

        self.config_path = config_path
        self.qa_kwargs = kwargs

    def _load_default_config(self) -> dict:
        """Load a minimal default configuration for QA processing."""
        return {
            "retrieval": {"enabled": True, "top_k": 5},
            "reranking": {"enabled": True},
            "crag": {"enabled": False},  # Disable complex features by default
            "graphrag": {"enabled": False},
            "decoding": {"mode": "greedy", "llm": {"provider": "local"}},
            "verification": {"enabled": False},
        }

    def reply(self, transcript: str) -> ReasoningResult:
        """Generate a response using the QA module.

        Args:
            transcript: Input transcript to process

        Returns:
            ReasoningResult with QA response and sources
        """
        if not transcript.strip():
            return ReasoningResult(reply_text="", sources=[], meta={"empty_input": True})

        try:
            # Load configuration
            config = self._load_default_config()
            if self.config_path:
                try:
                    import yaml

                    with open(self.config_path, "r") as f:
                        file_config = yaml.safe_load(f)
                    config.update(file_config)
                except Exception:
                    # If config loading fails, use default
                    pass  # nosec B110

            # Update config with any provided kwargs
            config.update(self.qa_kwargs)

            result = None
            sources = []
            trace: Dict[str, Any] = {}

            # Try primary entrypoint: answer(question, config)
            if hasattr(self.qa_mod, "answer"):
                try:
                    # qa.answer returns (final_answer, trace)
                    final_answer, trace = self.qa_mod.answer(transcript, config)

                    if isinstance(final_answer, dict):
                        # Extract text from the answer dict
                        result = final_answer.get(
                            "answer", final_answer.get("text", str(final_answer))
                        )
                    else:
                        result = str(final_answer)

                    # Extract sources from trace
                    if isinstance(trace, dict):
                        # Try to get reranked documents as sources
                        reranked = trace.get("reranked_full", [])
                        if isinstance(reranked, list):
                            sources = [
                                f"Doc {doc.get('id', i)}: {doc.get('text', str(doc))[:100]}..."
                                if isinstance(doc, dict) and len(doc.get("text", "")) > 100
                                else str(doc)[:100] + "..."
                                if len(str(doc)) > 100
                                else str(doc)
                                for i, doc in enumerate(reranked[:5])  # Limit to top 5 sources
                            ]

                        # Fallback: try other trace fields
                        if not sources:
                            doc_text = trace.get("doc_text", {})
                            if isinstance(doc_text, dict):
                                sources = [
                                    f"{k}: {v[:100]}..." for k, v in list(doc_text.items())[:5]
                                ]

                except Exception as e:
                    # If answer fails, try fallback
                    result = f"QA processing error: {str(e)}"

            # Fallback: try run method if available
            if result is None and hasattr(self.qa_mod, "run"):
                try:
                    run_result = self.qa_mod.run(transcript)
                    if isinstance(run_result, tuple) and len(run_result) >= 2:
                        result, sources = run_result[0], run_result[1]
                    else:
                        result = str(run_result)
                except Exception:
                    pass  # nosec B110

            if result is None:
                raise RuntimeError("No compatible QA entrypoint found")

            # Ensure sources is a list of strings
            if not isinstance(sources, list):
                sources = [str(sources)] if sources else []

            sources = [str(s) for s in sources]

            return ReasoningResult(
                reply_text=str(result),
                sources=sources,
                meta={
                    "backend": "local_qa",
                    "input_length": len(transcript),
                    "config_used": bool(self.config_path),
                    "trace_keys": list(trace.keys()) if isinstance(trace, dict) else [],
                },
            )

        except Exception as e:
            # Fallback for any errors
            return ReasoningResult(
                reply_text=f"QA processing failed: {str(e)}",
                sources=[],
                meta={"backend": "local_qa", "error": str(e)},
            )
