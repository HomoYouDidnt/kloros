from typing import Any, Dict

from kloROS_accuracy_stack.retrieval.crag import corrective_loop, need_correction
from kloROS_accuracy_stack.retrieval.embedder import retrieve
from kloROS_accuracy_stack.retrieval.reranker import rerank


def _cfg() -> Dict[str, Any]:
    return {
        "retrieval": {"provider": "mock", "top_k": 5},
        "rerank": {"provider": "mock", "keep_top_k": 3},
        "crag": {"quality_threshold": 0.8},
    }


def test_mock_retrieval_returns_scored_docs() -> None:
    cfg = _cfg()
    trace: Dict[str, Any] = {}
    results = retrieve("What pipeline does KLoROS use?", cfg, trace)
    assert results, "expected at least one mock hit"
    assert all(isinstance(doc.get("score"), float) for doc in results)
    assert trace.get("retrieved_full") == results
    assert trace.get("retrieved_ids")


def test_crag_corrective_loop_returns_full_docs() -> None:
    cfg = _cfg()
    trace: Dict[str, Any] = {}
    hits = retrieve("What pipeline does KLoROS use?", cfg, trace)
    reranked = rerank("What pipeline does KLoROS use?", hits, cfg, trace)
    assert need_correction(reranked, cfg) is True
    corrected = corrective_loop("What pipeline does KLoROS use?", reranked, cfg, trace)
    assert corrected and isinstance(corrected[0], dict)
    assert "text" in corrected[0]
    assert trace["crag"].get("expanded_query")
