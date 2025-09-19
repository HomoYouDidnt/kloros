
from kloROS_accuracy_stack.pipeline.qa import build_context
from kloROS_accuracy_stack.retrieval.crag import corrective_loop
from kloROS_accuracy_stack.verify.cove import cove_verify


def test_corrective_loop_returns_docs():
    docs = [{"id": "doc1", "text": "alpha"}, {"id": "doc2", "text": "beta"}]
    trace = {}
    corrected = corrective_loop("q", docs, {}, trace)
    assert corrected == docs
    assert trace["crag_branch"] == "noop"


def test_cove_verify_uses_doc_text():
    trace = {}
    context = build_context([{ "id": "doc1", "text": "alpha" }], trace, synopsis=None)
    draft = {"answer": "alpha", "citations": ["doc1"]}
    verified = cove_verify("q", draft, context, {}, trace)
    assert verified["verified"] is True
    abstain = cove_verify("q", {"answer": "", "citations": ["missing"]}, context, {}, trace)
    assert abstain.get("abstained") is True
