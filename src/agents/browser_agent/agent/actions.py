"""Browser action definitions."""
from typing import Dict, Any, List
from pydantic import BaseModel, Field

class BrowserAction(BaseModel):
    """Base browser action model."""
    type: str
    args: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 8000

    class Config:
        extra = "allow"

# Action type definitions
class NavigateAction(BrowserAction):
    """Navigate to URL."""
    type: str = "navigate"
    url: str

class ClickAction(BrowserAction):
    """Click element."""
    type: str = "click"
    selector: str

class TypeAction(BrowserAction):
    """Type text into element."""
    type: str = "type"
    selector: str
    text: str

class WaitAction(BrowserAction):
    """Wait for element or time."""
    type: str = "wait"
    selector: str | None = None
    time_ms: int | None = None

class ExtractAction(BrowserAction):
    """Extract text from element."""
    type: str = "extract"
    selector: str
    attribute: str | None = None  # Extract attribute value, or text if None

class ScreenshotAction(BrowserAction):
    """Take screenshot."""
    type: str = "screenshot"
    path: str | None = None

class ScrollAction(BrowserAction):
    """Scroll page."""
    type: str = "scroll"
    direction: str = "down"  # up, down, top, bottom
    amount: int = 500

class EvaluateAction(BrowserAction):
    """Execute JavaScript."""
    type: str = "evaluate"
    script: str

# Action registry
ACTION_TYPES = {
    "navigate": NavigateAction,
    "click": ClickAction,
    "type": TypeAction,
    "wait": WaitAction,
    "extract": ExtractAction,
    "screenshot": ScreenshotAction,
    "scroll": ScrollAction,
    "evaluate": EvaluateAction
}

def parse_action(action_dict: Dict[str, Any]) -> BrowserAction:
    """Parse action dict into typed action.

    Args:
        action_dict: Action dictionary

    Returns:
        Typed action instance
    """
    action_type = action_dict.get("type", "")
    action_class = ACTION_TYPES.get(action_type, BrowserAction)
    return action_class(**action_dict)

# Type alias for backward compatibility
Action = Dict[str, Any]
