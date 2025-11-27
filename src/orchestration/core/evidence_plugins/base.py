#!/usr/bin/env python3
"""
Base Evidence Plugin - Abstract interface for evidence gathering plugins.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Evidence:
    """
    Single piece of evidence gathered during investigation.
    """
    source: str
    evidence_type: str
    content: Any
    metadata: Dict[str, Any]
    timestamp: str
    confidence: float = 1.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class EvidencePlugin(ABC):
    """
    Abstract base class for evidence gathering plugins.

    Each plugin represents a different way of gathering evidence:
    - Code structure (AST parsing, file analysis)
    - Runtime logs (system logs, service status)
    - System metrics (resource usage, performance)
    - Integration analysis (how modules connect)
    - Experimentation (running code, testing hypotheses)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier"""
        pass

    @abstractmethod
    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        """
        Determine if this plugin can contribute to this investigation.

        Args:
            investigation_type: Type of investigation (code_behavior, system_state, etc.)
            question: The question being investigated
            context: Current investigation context (evidence gathered so far, etc.)

        Returns:
            True if this plugin can help, False otherwise
        """
        pass

    @abstractmethod
    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        """
        Gather evidence relevant to the question.

        Args:
            question: The question being investigated
            context: Investigation context including:
                - investigation_type: str
                - intent: Dict[str, Any] from LLM classification
                - existing_evidence: List[Evidence] gathered so far
                - iteration: int

        Returns:
            List of Evidence objects
        """
        pass

    @abstractmethod
    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate cost of gathering evidence from this plugin.

        Returns:
            Dict with keys:
                - time_estimate_seconds: float
                - token_cost: int (if LLM involved)
                - complexity: str (low|medium|high)
        """
        pass

    def priority(self, investigation_type: str) -> int:
        """
        Priority for this plugin in the evidence gathering order.

        Higher priority plugins are consulted first.
        Default: 50 (medium priority)

        Returns:
            Priority value (0-100)
        """
        return 50
