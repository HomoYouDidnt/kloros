"""PHASE Test Domains

Available domains for overnight PHASE testing.

Legacy hardware domains are explicitly denied to prevent accidental use.
"""
import logging
import sys

logger = logging.getLogger(__name__)

# DENY LIST: Legacy hardware domains that should never be imported
LEGACY_DENIED_DOMAINS = [
    "cpu_domain_evaluator",
    "gpu_domain_evaluator",
    "hardware_domain_evaluator",
]

# Domain registry
AVAILABLE_DOMAINS = [
    "code_repair",
    "conversation_domain",
    "mcp_domain",
    "rag_context_domain",
    "system_health_domain",
    "tts_domain",
]


def _check_legacy_import():
    """Check if any legacy domains were imported and block them."""
    for module_name in list(sys.modules.keys()):
        for denied in LEGACY_DENIED_DOMAINS:
            if denied in module_name:
                logger.error(
                    f"⚠️  BLOCKED: Legacy hardware domain '{denied}' detected in imports. "
                    f"These domains are quarantined and must not be loaded."
                )
                raise ImportError(
                    f"Legacy domain '{denied}' is explicitly denied. "
                    f"Use new PHASE domains instead."
                )


# Run check on module import
_check_legacy_import()


__all__ = AVAILABLE_DOMAINS
