import os
from .collector import Collector
from .analysis import summarize_episodes, compare_generations, macro_usage, safety_summary
from .figures import bar_fig
from .tables import write_table_md
from .types import ReportSpec, Section, FigureSpec, TableSpec, Citation
from .writer import render_markdown
from .reviewers.committee_tumix import run_committee
from .citations.chroma_retriever import index_bibliography, query_citations

def build_plus_report(col: Collector, out_dir: str = "reports",
                      title="KLoROS Experimental Report", authors=None,
                      citations_query_terms=None, citations_bib_path=None,
                      chroma_client_or_path=None, chroma_collection="citations",
                      run_reviewer=True):
    authors = authors or ["KLoROS"]
    snap = col.snapshot()
    os.makedirs(out_dir, exist_ok=True)
    figs_dir, tabs_dir = os.path.join(out_dir, "figures"), os.path.join(out_dir, "tables")
    os.makedirs(figs_dir, exist_ok=True); os.makedirs(tabs_dir, exist_ok=True)

    epi = summarize_episodes(snap["episodes"])
    gens = compare_generations(snap["generations"])
    macros = macro_usage(snap["macro_traces"])
    saf = safety_summary(snap["petri_reports"])

    # Figures
    fig1_path = os.path.join(figs_dir, "success_rate.png")
    bar_fig(fig1_path, "Episode Success Rate", ["success%"], [epi["success_rate"]])

    # Tables
    tab1_path = os.path.join(tabs_dir, "macro_usage.md")
    rows = [[mid, d["uses"], f'{d["win_rate"]}%', d["avg_cost"]] for mid, d in macros["per_macro"].items()] or [["(none)",0,"0%",0]]
    write_table_md(tab1_path, ["Macro", "Uses", "WinRate", "AvgTokenCost"], rows)

    # Citations
    citations = []
    if citations_bib_path and os.path.exists(citations_bib_path):
        # If a chroma path/client provided, index once (idempotent).
        try:
            index_bibliography(chroma_client_or_path, citations_bib_path, chroma_collection)
        except Exception:
            pass
        q_terms = citations_query_terms or ["agentic context", "macro reasoning", "evolutionary agents"]
        seen_keys = set()
        for q in q_terms:
            try:
                hits = query_citations(chroma_client_or_path, q, chroma_collection, k=5, refs_json_path=citations_bib_path)
            except Exception:
                hits = []
            for h in hits:
                key = h.get("id") or h.get("key") or h.get("title","")[:24]
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                citations.append(Citation(
                    key=str(key),
                    title=h.get("title","(untitled)"),
                    author=", ".join(h.get("authors", [])) or h.get("author","Unknown"),
                    year=int(h.get("year", 0)) if str(h.get("year","")).isdigit() else 0,
                    venue=h.get("venue",""),
                    url=h.get("url","")
                ))

    # Sections
    abstract = f"We report on {epi['n']} episodes; success={epi['success_rate']}%, avg score={epi['avg_score']}, avg latency={epi['avg_latency_ms']}ms."
    sec_methods = Section(
        title="Methods",
        body_md="- AgentFlow orchestrated Planner/Executor/Verifier\n- D‑REAM evolved strategies\n- RA³ applied macros where applicable\n- PETRI gated risky operations\n- ACE accumulated playbook bullets"
    )
    sec_results = Section(
        title="Results",
        body_md=f"- Episodes: {epi['n']} (success {epi['success_rate']}%)\n- Best Generation: {gens.get('best_gen')} with fitness {gens.get('best_fitness')}\n- Safety: blocked {saf['blocked']} of {saf['total_reports']} actions",
        figs=[FigureSpec(id="fig-success", caption="Success rate", path=fig1_path)],
        tabs=[TableSpec(id="tab-macros", caption="Macro usage summary", path=tab1_path)]
    )
    sec_related = None
    if citations:
        bullets = "\n".join([f"- {c.author} ({c.year}). *{c.title}*. {c.venue}. {c.url}" for c in citations[:10]])
        sec_related = Section(title="Related Work", body_md=bullets)

    # Reviewer committee notes
    appendix_extra = ""
    if run_reviewer:
        secs_for_review = [
            {"title": "Methods", "body_md": sec_methods.body_md},
            {"title": "Results", "body_md": sec_results.body_md},
        ]
        notes = run_committee(secs_for_review, rounds=1)
        appendix_extra += "\n### Reviewer Notes (Heuristic Committee)\n"
        for n in notes:
            if n["notes"]:
                appendix_extra += f"- **{n['section']}**: " + " ".join(n["notes"]) + f" (Δscore={n['score_delta']})\n"

    sections = [sec_methods, sec_results]
    if sec_related: sections.append(sec_related)

    from .writer import render_markdown
    spec = ReportSpec(
        title=title, authors=authors, abstract_md=abstract,
        sections=sections, citations=citations,
        appendix_md=appendix_extra
    )
    md = render_markdown(spec)
    out_md = os.path.join(out_dir, "plus_report.md")
    with open(out_md, "w", encoding="utf-8") as f: f.write(md)
    return out_md
