"""
Semantic Analysis - Architectural Pattern Recognition for Capability Discovery

Purpose:
    Prevent phantom capability discoveries by understanding the semantic meaning
    of code references rather than just pattern-matching on names.

Core Problem:
    KLoROS saw "inference" mentioned in multiple files and assumed there should
    be a unified module.inference - but "inference" was actually implemented as
    intentional distributed functionality across llm.ollama, RAG backends, and
    scanners. This generated 5,115 phantom questions (51% of missing_deps queue).

Solution:
    Semantic analysis to distinguish between:
    1. Real gaps: Code imports missing modules
    2. Distributed patterns: Functionality spread across multiple modules
    3. Phantoms: Name mentioned but not actually used as dependency

Architecture:
    - ReferenceAnalyzer: Parses code to classify how terms are referenced
    - PatternDetector: Identifies architectural patterns (distributed, unified, etc.)
    - ConfidenceScorer: Rates gap hypothesis strength based on evidence
    - ArchitecturalReasoner: Orchestrates analysis and explains findings

Example:
    >>> analyzer = ArchitecturalReasoner()
    >>> result = analyzer.analyze_gap_hypothesis("inference", references)
    >>> result.pattern
    'DISTRIBUTED_PATTERN'
    >>> result.confidence
    0.05  # Low confidence this is actually a gap
    >>> result.explanation
    'inference is implemented across 4 modules (llm.ollama, rag.retrieval, etc.)'
"""

from .reference_analyzer import ReferenceAnalyzer, ReferenceType
from .pattern_detector import PatternDetector, ArchitecturalPattern
from .confidence_scorer import ConfidenceScorer
from .architectural_reasoner import ArchitecturalReasoner

__all__ = [
    'ReferenceAnalyzer',
    'ReferenceType',
    'PatternDetector',
    'ArchitecturalPattern',
    'ConfidenceScorer',
    'ArchitecturalReasoner',
]
