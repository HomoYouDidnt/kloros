from typing import Any, Dict, List, Tuple


def graphrag_expand(question: str, rr: List[Dict[str, Any]], cfg: Dict[str, Any], trace: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    # TODO: build entity graph offline; here we produce a tiny synopsis.
    synopsis = "Entities: KLoROS, RAG, SLED, CoVe. Relations: RAG→Decode, Verify→Answer."
    trace["graphrag"] = {"nodes": 4, "edges": 2}
    return {"nodes": [], "edges": []}, synopsis
