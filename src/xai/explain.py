from .record import DecisionRecord
def _fmt_pct(x): 
    try: return f"{100*float(x):.0f}%"
    except: return "—"
def render(rec: DecisionRecord, cfg: dict) -> dict:
    show_u = bool(cfg.get("render",{}).get("show_uncertainty", True))
    show_b = bool(cfg.get("render",{}).get("show_budgets", True))
    show_t = bool(cfg.get("render",{}).get("show_tools", True))
    max_c = int(cfg.get("render",{}).get("max_citations", 5))
    evidence_sorted = sorted(rec.evidence, key=lambda e: e.weight, reverse=True)[:max_c]
    tools_sorted = list(rec.tools)
    sections = []
    sections.append({"title":"What I answered (short)", "body": rec.answer_summary})
    if rec.citations or evidence_sorted:
        cites = [e.source or e.doc_id for e in evidence_sorted]
        sections.append({"title":"Why I trusted these sources", "list":[f"{c}  (weight: {_fmt_pct(e.weight)})" for c, e in zip(cites, evidence_sorted)]})
    if show_t and tools_sorted:
        lines = [f"{t.name} — Δuncertainty: {_fmt_pct(t.delta_uncertainty)}; gain: {t.expected_gain:.2f}, cost: {t.expected_cost:.2f}, risk: {t.expected_risk:.2f}" for t in tools_sorted]
        sections.append({"title":"Why I used these tools", "list": lines})
    if show_u:
        sections.append({"title":"Confidence", "body": f"Before: {_fmt_pct(1.0 - rec.uncertainty_before)} → After: {_fmt_pct(1.0 - rec.uncertainty_after)}"})
    if show_b and rec.budgets:
        kv = [f"{k}: {v}" for k,v in rec.budgets.items()]
        sections.append({"title":"Constraints", "list": kv})
    if rec.rationale_outline:
        sections.append({"title":"How I approached it (outline)", "body": rec.rationale_outline})
    return {"id": rec.id, "query": rec.query, "mode": rec.mode, "sections": sections, "citations": rec.citations[:max_c]}
