"""Browser automation agent with PETRI-gated security.

Requires playwright for full functionality:
    pip install playwright
    playwright install chromium
"""

try:
    from .agent.executor import BrowserExecutor
    from .agent.petri_policy import PetriPolicy
    BROWSER_AGENT_AVAILABLE = True
except ImportError as e:
    BROWSER_AGENT_AVAILABLE = False
    _import_error = e

    class BrowserExecutor:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                f"playwright is required for browser_agent. "
                f"Install with: pip install playwright && playwright install chromium\n"
                f"Original error: {_import_error}"
            )

    class PetriPolicy:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                f"playwright is required for browser_agent. "
                f"Install with: pip install playwright && playwright install chromium\n"
                f"Original error: {_import_error}"
            )

__all__ = ["BrowserExecutor", "PetriPolicy", "BROWSER_AGENT_AVAILABLE"]
