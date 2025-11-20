from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class Citation:
    key: str
    title: str
    author: str
    year: int
    venue: str = ""
    url: str = ""

@dataclass
class FigureSpec:
    id: str
    caption: str
    path: str

@dataclass
class TableSpec:
    id: str
    caption: str
    path: str

@dataclass
class Section:
    title: str
    body_md: str
    figs: List[FigureSpec] = field(default_factory=list)
    tabs: List[TableSpec] = field(default_factory=list)

@dataclass
class ReportSpec:
    title: str
    authors: List[str]
    abstract_md: str
    sections: List[Section]
    citations: List[Citation] = field(default_factory=list)
    appendix_md: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
