from .types import ReportSpec
HEADER = "# {title}\n{authors_line}\n\n*{abstract}*\n"
SECTION_TMPL = "\n## {title}\n{body}\n"
def render_markdown(spec: ReportSpec) -> str:
    authors_line = ", ".join(spec.authors)
    out = HEADER.format(title=spec.title, authors_line=authors_line, abstract=spec.abstract_md)
    for s in spec.sections:
        out += SECTION_TMPL.format(title=s.title, body=s.body_md)
        for fig in s.figs:
            out += f"\n![{fig.caption}]({fig.path})\n"
        for tab in s.tabs:
            with open(tab.path,'r',encoding='utf-8') as tf:
                out += f"\n**Table ({tab.id})**: {tab.caption}\n\n" + tf.read() + "\n"
    if spec.appendix_md:
        out += "\n## Appendix\n" + spec.appendix_md + "\n"
    if spec.citations:
        out += "\n## References\n"
        for c in spec.citations:
            out += f"- {c.author} ({c.year}). *{c.title}*. {c.venue}. {c.url}\n"
    return out
