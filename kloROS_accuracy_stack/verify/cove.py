"""Mock CoVe verification for the accuracy stack."""
from __future__ import annotations

from typing import Any, Dict


def cove_verify(
    question: str,
    draft: Dict[str, Any],
    context: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    provider = cfg.get("verification", {}).get("provider", "mock").lower()
    if provider != "mock":
        raise NotImplementedError(f"Verification provider '{provider}' not implemented in mock stack")

    citations = draft.get("citations", [])
    doc_text = trace.get("doc_text", {})
    missing_ids = [cid for cid in citations if cid not in doc_text]
    missing_markers = [cid for cid in citations if f"[DOC:{cid}]" not in context]
    if missing_ids or missing_markers:
        return {
            "answer": None,
            "abstained": True,
            "reason": "insufficient citations",
            "missing": sorted(set(missing_ids + missing_markers)),
        }
    draft = dict(draft)
    draft["verified"] = True
    return draft
