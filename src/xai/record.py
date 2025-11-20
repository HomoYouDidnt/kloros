from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import time, uuid

class Evidence(BaseModel):
    doc_id: str
    source: str
    snippet: str
    score: float
    weight: float = 0.0

class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any] = {}
    start_ms: int = 0
    end_ms: int = 0
    success: bool = True
    output_summary: str = ""
    expected_gain: float = 0.0
    expected_cost: float = 0.0
    expected_risk: float = 0.0
    delta_uncertainty: float = 0.0

class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = Field(default_factory=lambda: time.time())
    user_id: Optional[str] = None
    query: str
    mode: str = "fast"
    budgets: Dict[str, Any] = {}
    uncertainty_before: float = 0.0
    uncertainty_after: float = 0.0
    rationale_outline: str = ""
    evidence: List[Evidence] = []
    tools: List[ToolCall] = []
    answer_summary: str = ""
    citations: List[str] = []
