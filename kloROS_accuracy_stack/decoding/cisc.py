from typing import Any, Dict


def greedy_generate(question: str, context: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {"answer": f"[Greedy] {context.splitlines()[0]}", "citations": ["doc1"]}

def cisc_generate(question: str, context: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    # Stub: sample k candidates and weight by confidence (logprob). Here we return a deterministic string.
    return {"answer": f"[CISC] Using confidence-weighted vote on: {context[:60]}...", "citations": ["doc1","doc2"]}
