from typing import List, Dict, Any

def retrieve(question: str, cfg: Dict[str, Any], trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    # TODO: plug in bge-m3 encoder and vector store. This is a stub that returns fixture docs.
    docs = [
        {"id": "doc1", "score": 0.9, "text": "KLoROS uses a RAG pipeline to answer questions."},
        {"id": "doc2", "score": 0.7, "text": "SLED adjusts final logits using mid-layer evidence."},
        {"id": "doc3", "score": 0.6, "text": "CoVe verifies claims against retrieved spans."},
    ]
    trace["retrieved"] = [d["id"] for d in docs]
    return docs
