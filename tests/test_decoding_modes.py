from kloROS_accuracy_stack.pipeline.qa import decode

CONTEXT = (
    "[DOC:001.md]\nKLoROS combines RAG and verification.\n\n"
    "[DOC:002.md]\nSLED adjusts logits by layer mixing."
)


CFG_BASE = {
    "decoding": {
        "mode": ["greedy", "sled", "cisc", "topk", "nucleus"],
        "active": "greedy",
        "sled": {"alpha": 0.2, "keep_final_topk_union": 10},
        "cisc": {"samples": 3},
        "topk": {"k": 4},
        "nucleus": {"p": 0.8, "max_tokens": 16},
    }
}


def _run(mode: str):
    cfg = {"decoding": dict(CFG_BASE["decoding"], active=mode)}
    trace = {"doc_text": {"001.md": "chunk"}, "reranked_full": [], "reranked_ids": []}
    result, meta = decode("What does KLoROS use?", CONTEXT, cfg, trace)
    assert trace["decode_mode"] == mode
    assert result["citations"]
    return result, meta


def test_decoding_modes_emit_distinct_answers() -> None:
    greedy, _ = _run("greedy")
    sled, _ = _run("sled")
    cisc, _ = _run("cisc")
    topk, _ = _run("topk")
    nucleus, _ = _run("nucleus")
    answers = {greedy["answer"], sled["answer"], cisc["answer"], topk["answer"], nucleus["answer"]}
    assert len(answers) == 5


def test_topk_uses_configured_k() -> None:
    cfg = {"decoding": dict(CFG_BASE["decoding"], active="topk", topk={"k": 7})}
    trace = {"doc_text": {"001.md": "chunk"}, "reranked_full": [], "reranked_ids": []}
    result, _ = decode("Explain KLoROS", CONTEXT, cfg, trace)
    assert result["meta"]["k"] == 7


def test_nucleus_respects_probability() -> None:
    cfg = {"decoding": dict(CFG_BASE["decoding"], active="nucleus", nucleus={"p": 0.7, "max_tokens": 10})}
    trace = {"doc_text": {"001.md": "chunk"}, "reranked_full": [], "reranked_ids": []}
    result, _ = decode("Describe SLED", CONTEXT, cfg, trace)
    assert result["meta"]["p"] == 0.7
    assert result["meta"]["nucleus_size"] >= 1
