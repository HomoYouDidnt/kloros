"""Local citation verification helpers for the accuracy stack."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

_MARKER_PATTERN = re.compile(r"\[DOC:([^\]]+)\]")


def _normalise_citations(citations: Iterable[Any]) -> List[str]:
    return [str(cid) for cid in citations if str(cid).strip()]


def _collect_support(
    citations: Sequence[str], context: str, doc_text: Dict[str, str]
) -> tuple[List[str], List[str], List[str]]:
    markers = set(_MARKER_PATTERN.findall(context))
    available = set(doc_text)
    missing_ids = [cid for cid in citations if cid not in available]
    missing_markers = [cid for cid in citations if cid not in markers]
    supported = [cid for cid in citations if cid not in missing_ids and cid not in missing_markers]
    return supported, missing_ids, missing_markers


def _abstain(
    reason: str, *, missing: Iterable[str] | None = None, score: float | None = None
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "answer": None,
        "abstained": True,
        "reason": reason,
    }
    if missing:
        result["missing"] = sorted(set(missing))
    if score is not None:
        result["score"] = float(score)
    return result


def cove_verify(
    question: str,
    draft: Dict[str, Any],
    context: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    verification_cfg = cfg.get("verification", {})
    provider = verification_cfg.get("provider", "mock").lower()
    citations = _normalise_citations(draft.get("citations", []))
    doc_text = trace.get("doc_text", {})
    supported, missing_ids, missing_markers = _collect_support(citations, context, doc_text)

    if provider == "mock":
        if missing_ids or missing_markers:
            return _abstain(
                "insufficient citations",
                missing=[*missing_ids, *missing_markers],
            )
        verified = dict(draft)
        verified["verified"] = True
        return verified

    if provider != "local":
        raise NotImplementedError(
            f"Verification provider '{provider}' not implemented in accuracy stack"
        )

    threshold = float(verification_cfg.get("abstain_threshold", 0.75))
    support_score = len(supported) / max(1, len(citations)) if citations else 0.0
    verification_trace = trace.setdefault("verification", {})
    verification_trace.update(
        {
            "provider": provider,
            "citations": citations,
            "supported": supported,
            "score": round(support_score, 3),
        }
    )

    if not citations:
        return _abstain("no_citations", score=support_score)
    if missing_ids or missing_markers:
        return _abstain(
            "missing_markers",
            missing=[*missing_ids, *missing_markers],
            score=support_score,
        )
    if support_score < threshold:
        return _abstain("support_below_threshold", score=support_score)

    verified = dict(draft)
    meta = dict(verified.get("meta", {}))
    meta["citation_support"] = round(support_score, 3)
    verified["meta"] = meta
    verified["verified"] = True
    return verified
