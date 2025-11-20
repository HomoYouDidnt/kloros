from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any, List
from datetime import datetime

class Improvement(BaseModel):
    id: int
    created_at: datetime
    title: str
    description: str
    domain: str = "general"
    status: Literal["pending", "approved", "declined"] = "pending"
    score: float = 0.0
    meta: Dict[str, Any] = Field(default_factory=dict)

class QueueItem(BaseModel):
    id: int
    created_at: datetime
    type_key: str
    params: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    note: Optional[str] = None

class ExperimentType(BaseModel):
    key: str
    name: str
    description: str
    params_schema: Dict[str, Any] = Field(default_factory=dict)  # JSON-schema-ish
