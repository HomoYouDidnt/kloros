from kloROS_accuracy_stack.verify.cove import cove_verify

CONTEXT = "[DOC:001.md]\nEvidence line."


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
