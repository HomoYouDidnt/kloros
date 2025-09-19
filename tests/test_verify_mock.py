from kloROS_accuracy_stack.verify.cove import cove_verify

CONTEXT = "[DOC:001.md]\nEvidence line."
DOC_TEXT = {
    "001.md": "[DOC:001.md]\nEvidence line.",
    "002.md": "[DOC:002.md]\nSecond evidence block.",
}
LOCAL_CONTEXT = "\n\n".join(DOC_TEXT.values())


def test_mock_verifier_passes_with_matching_citations() -> None:
    trace = {"doc_text": {"001.md": CONTEXT}}
    draft = {"answer": "ok", "citations": ["001.md"]}
    result = cove_verify("q", draft, CONTEXT, {"verification": {"provider": "mock"}}, trace)
    assert result.get("verified") is True


def test_mock_verifier_abstains_with_unknown_citation() -> None:
    trace = {"doc_text": {"001.md": CONTEXT}}
    draft = {"answer": "ok", "citations": ["missing"]}
    result = cove_verify("q", draft, CONTEXT, {"verification": {"provider": "mock"}}, trace)
    assert result.get("abstained") is True


def test_local_verifier_marks_verified_when_markers_present() -> None:
    trace = {"doc_text": DOC_TEXT.copy()}
    draft = {
        "answer": "See [DOC:001.md] and [DOC:002.md] for details.",
        "citations": ["001.md", "002.md"],
    }
    cfg = {"verification": {"provider": "local", "abstain_threshold": 0.5}}
    result = cove_verify("q", draft, LOCAL_CONTEXT, cfg, trace)
    assert result.get("verified") is True
    assert result.get("meta", {}).get("citation_support") == 1.0


def test_local_verifier_abstains_when_marker_missing() -> None:
    trace = {"doc_text": DOC_TEXT.copy()}
    draft = {"answer": "See [DOC:001.md]", "citations": ["001.md", "002.md"]}
    cfg = {"verification": {"provider": "local", "abstain_threshold": 0.2}}
    bad_context = DOC_TEXT["001.md"]
    result = cove_verify("q", draft, bad_context, cfg, trace)
    assert result.get("abstained") is True
    assert result.get("reason") == "missing_markers"
