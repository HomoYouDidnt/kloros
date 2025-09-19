from typing import Dict, Any

def cove_verify(question: str, draft: Dict[str, Any], context: str, cfg: Dict[str, Any], trace: Dict[str, Any]) -> Dict[str, Any]:
    # Stub: verify claims exist in context; else abstain.
    ok = all(cit in context for cit in draft.get("citations", []))
    if ok:
        draft["verified"] = True
        return draft
    return {"answer": None, "abstained": True, "reason": "insufficient citations"}
