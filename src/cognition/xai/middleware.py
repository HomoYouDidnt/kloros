import yaml, os
from .record import DecisionRecord, Evidence, ToolCall
from .store import write as store_write

_cfg = None
_current = None

def load_cfg(path="~/.kloros/xai.yaml"):
    global _cfg
    expanded_path = os.path.expanduser(path)
    _cfg = yaml.safe_load(open(expanded_path,"r",encoding="utf-8"))
    return _cfg

def start_turn(query: str, user_id: str | None = None, mode: str = "fast", budgets: dict | None = None, uncertainty: float = 0.0):
    global _current
    if _cfg is None: load_cfg()
    _current = DecisionRecord(query=query, user_id=user_id, mode=mode, budgets=budgets or {}, uncertainty_before=uncertainty)

def log_retrieval(hits):
    global _current
    if not _current or not hits: return
    scores = [float(h.get("score",0.0)) for h in hits]
    mn, mx = min(scores), max(scores)
    span = (mx - mn) or 1.0
    weights = [(s - mn)/span for s in scores]
    total = sum(weights) or 1.0
    weights = [w/total for w in weights]
    for h, w in zip(hits, weights):
        _current.evidence.append(Evidence(doc_id=str(h.get("doc_id")), source=str(h.get("source","")),
                                          snippet=str(h.get("snippet",""))[:400], score=float(h.get("score",0.0)), weight=float(w)))

def log_tool(name, args, start_ms, end_ms, success, output_summary, eg, ec, er, d_unc):
    global _current
    if not _current: return
    _current.tools.append(ToolCall(name=name, args=args, start_ms=int(start_ms), end_ms=int(end_ms),
                                   success=bool(success), output_summary=str(output_summary)[:400],
                                   expected_gain=float(eg), expected_cost=float(ec), expected_risk=float(er), delta_uncertainty=float(d_unc)))

def log_tool_call(name, args, output, success=True):
    """Simplified tool call logger for structured tool execution.

    This is a convenience wrapper around log_tool() for simple tool calls
    that don't have timing/uncertainty metrics. Used by chat API tool execution.
    """
    import time
    global _current
    if not _current: return
    now_ms = int(time.time() * 1000)
    output_summary = str(output)[:400] if output else ""
    log_tool(
        name=name,
        args=args,
        start_ms=now_ms,
        end_ms=now_ms,
        success=success,
        output_summary=output_summary,
        eg=0.0,  # Expected gain - unknown for simple calls
        ec=0.0,  # Expected cost - unknown for simple calls
        er=0.0,  # Expected risk - unknown for simple calls
        d_unc=0.0  # Delta uncertainty - unknown for simple calls
    )

def finalize(answer_summary, citations, uncertainty_after, rationale_outline=""):
    global _current, _cfg
    if not _current: return None
    _current.answer_summary = str(answer_summary)[:400]
    _current.citations = list(citations)[:10]
    _current.uncertainty_after = float(uncertainty_after)
    _current.rationale_outline = str(rationale_outline)[:600]
    store_write(_cfg, _current)
    rec = _current
    _current = None
    return rec
