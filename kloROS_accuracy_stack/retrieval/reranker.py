from typing import List, Dict, Any

def rerank(question: str, hits: List[Dict[str, Any]], cfg: Dict[str, Any], trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    # TODO: integrate bge-reranker-v2-m3 or provider. Here we sort by score descending.
    rr = sorted(hits, key=lambda d: d.get("score", 0), reverse=True)
    keep_k = cfg.get("rerank", {}).get("keep_top_k", 5)
    rr = rr[:keep_k]
    trace["reranked"] = [d["id"] for d in rr]
    return rr
