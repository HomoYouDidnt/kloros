"""
Cognition Module - KLoROS's Thinking and Reasoning Systems

Core components for:
- Curiosity-driven question generation and investigation
- Capability evaluation and discovery
- Semantic evidence storage and analysis
- Reasoning coordination
- System introspection
"""

from .curiosity_core import (
    CuriosityCore,
    CuriosityQuestion,
    ActionClass,
    QuestionStatus,
)
from .capability_evaluator import (
    CapabilityEvaluator,
    CapabilityMatrix,
    CapabilityRecord,
    CapabilityState,
)
from .semantic_evidence import SemanticEvidenceStore
from .question_prioritizer import QuestionPrioritizer
from .curiosity_archive_manager import ArchiveManager
from .reasoning_coordinator import get_reasoning_coordinator, ReasoningMode
from .module_investigator import get_module_investigator
from .systemd_investigator import get_systemd_investigator

__all__ = [
    "CuriosityCore",
    "CuriosityQuestion",
    "ActionClass",
    "QuestionStatus",
    "CapabilityEvaluator",
    "CapabilityMatrix",
    "CapabilityRecord",
    "CapabilityState",
    "SemanticEvidenceStore",
    "QuestionPrioritizer",
    "ArchiveManager",
    "get_reasoning_coordinator",
    "ReasoningMode",
    "get_module_investigator",
    "get_systemd_investigator",
]
