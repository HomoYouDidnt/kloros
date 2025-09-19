from kloROS_accuracy_stack.pipeline.qa import decode

CONTEXT = "[DOC:001.md]\nKLoROS combines RAG and verification.\n\n[DOC:002.md]\nSLED adjusts logits by layer mixing."


CFG_BASE = {
    "decoding": {
        "mode": ["greedy", "sled", "cisc"],
        "active": "greedy",
        "sled": {"alpha": 0.2, "keep_final_topk_union": 10},
        "cisc": {"samples": 3},
    }
}


def _run(mode: str) -> str:
    cfg = {"decoding": dict(CFG_BASE["decoding"], active=mode)}
    trace = {"doc_text": {"001.md": "chunk"}, "reranked_full": [], "reranked_ids": []}
    result, _ = decode("What does KLoROS use?", CONTEXT, cfg, trace)
    assert trace["decode_mode"] == mode
    assert result["citations"]
    return result["answer"]


def test_decoding_modes_emit_distinct_answers() -> None:
    greedy = _run("greedy")
    sled = _run("sled")
    cisc = _run("cisc")
    assert greedy != sled and sled != cisc and greedy != cisc
