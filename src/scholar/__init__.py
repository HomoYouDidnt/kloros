"""KLoROS Scholar PLUS: Report generation with citations and TUMIX reviewers."""
from .types import ReportSpec, Section, Citation, FigureSpec, TableSpec
from .collector import Collector
from .pipeline_plus import build_plus_report
from .analysis import summarize_episodes, compare_generations, macro_usage, safety_summary
from .writer import render_markdown

__all__ = [
    "ReportSpec",
    "Section",
    "Citation",
    "FigureSpec",
    "TableSpec",
    "Collector",
    "build_plus_report",
    "summarize_episodes",
    "compare_generations",
    "macro_usage",
    "safety_summary",
    "render_markdown",
]
