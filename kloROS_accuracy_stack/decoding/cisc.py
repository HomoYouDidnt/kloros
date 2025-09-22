"""Mock decoding implementations (greedy + CISC)."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, Iterable, List

_DOC_PATTERN = re.compile(r"\[DOC:([^\]]+)\]")


def _citations(context: str) -> List[str]:
    seen = []
    for match in _DOC_PATTERN.findall(context):
        if match not in seen:
            seen.append(match)
    return seen or ["unknown"]


def _snippet(tokens: Iterable[str], length: int = 18) -> str:
    out: List[str] = []
    for token in tokens:
        if not token:
            continue
        out.append(token)
        if len(out) >= length:
            break
    return " ".join(out) if out else "No supporting context."


def greedy_generate(
    question: str,
    context: str,
    cfg: Dict[str, Any],
    doc_text: Dict[str, str],
) -> Dict[str, Any]:
    first_chunk = context.split("\n\n", 1)[0] if context else ""
    tokens = first_chunk.split()
    answer = f"[Greedy] {_snippet(tokens)}"
    citations = _citations(context)[:1]
    return {"answer": answer, "citations": citations}


def cisc_generate(
    question: str,
    context: str,
    cfg: Dict[str, Any],
    doc_text: Dict[str, str],
) -> Dict[str, Any]:
    tokens = context.split()
    samples = int(cfg.get("decoding", {}).get("cisc", {}).get("samples", 5))
    rng = random.Random(hash((question, context)))
    variants: List[tuple[float, str]] = []
    for idx in range(max(1, samples)):
        if tokens:
            start = rng.randrange(0, max(1, len(tokens) - 12))
            window = tokens[start : start + 12]
        else:
            window = []
        snippet = _snippet(window or tokens)
        confidence = 1.0 / (1 + idx) + (len(snippet) / max(1, len(context))) * 0.1
        variants.append((confidence, snippet))
    variants.sort(key=lambda item: (-item[0], item[1]))
    best_conf, best_snippet = variants[0]
    answer = f"[CISC k={samples}] {best_snippet}"
    citations = _citations(context)[:2]
    return {
        "answer": answer,
        "citations": citations,
        "meta": {"confidence": round(best_conf, 3)},
    }
