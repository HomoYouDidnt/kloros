from typing import Any, Dict


def cove_verify(
    question: str, draft: Dict[str, Any], context: str, cfg: Dict[str, Any], trace: Dict[str, Any]
) -> Dict[str, Any]:
    doc_text = trace.get("doc_text", {})
    citations = draft.get("citations", [])
    missing = [cit for cit in citations if cit not in doc_text]
    if missing:
        return {"answer": None, "abstained": True, "reason": "unknown citations"}
    draft["verified"] = True
    return draft
