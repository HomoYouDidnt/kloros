"""
Evidence Plugin Framework for Generic Investigation Handler

Extensible plugin system for gathering different types of evidence during investigations.
"""

from .base import EvidencePlugin, Evidence
from .code_structure import CodeStructurePlugin
from .runtime_logs import RuntimeLogsPlugin
from .system_metrics import SystemMetricsPlugin
from .integration import IntegrationPlugin
from .experimentation import ExperimentationPlugin
from .documentation import DocumentationPlugin

__all__ = [
    "EvidencePlugin",
    "Evidence",
    "CodeStructurePlugin",
    "RuntimeLogsPlugin",
    "SystemMetricsPlugin",
    "IntegrationPlugin",
    "ExperimentationPlugin",
    "DocumentationPlugin",
]
