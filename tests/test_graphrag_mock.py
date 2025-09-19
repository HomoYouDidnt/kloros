from kloROS_accuracy_stack.retrieval.graphrag import graphrag_expand


def test_graphrag_mock_returns_synopsis_and_trace() -> None:
    cfg = {"graphrag": {"provider": "mock", "enabled": True}}
    reranked = [
        {"id": "001.md", "text": "KLoROS Orchestrator links RAG and GraphRAG."},
        {"id": "002.md", "text": "SLED Decoder refines logits."},
    ]
    trace: dict = {}
    graph, synopsis = graphrag_expand("Explain KLoROS", reranked, cfg, trace)
    assert synopsis
    assert trace["graphrag"]["nodes"] >= 1
    assert "nodes" in graph and "edges" in graph
