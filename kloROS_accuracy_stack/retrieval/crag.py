from typing import List, Dict, Any

def _quality(rr: List[Dict[str, Any]]) -> float:
    return sum(d.get("score", 0) for d in rr) / max(1, len(rr))

def need_correction(rr: List[Dict[str, Any]], cfg: Dict[str, Any]) -> bool:
    th = cfg.get("crag", {}).get("quality_threshold", 0.62)
    return _quality(rr) < th

def corrective_loop(question: str, cfg: Dict[str, Any], trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    # TODO: implement expand/decompose. For now, return rr as-is but mark branch.
    trace["crag_branch"] = "noop"
    return trace.get("reranked", [])
