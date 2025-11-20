from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime
import uuid

@dataclass
class Lineage:
    origin: str           # "phase" | "user_experiment" | "system"
    episode_id: str       # phase window id or user task id
    generator_sha: str
    judge_sha: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class Candidate:
    id: str
    domain: str
    params: Dict
    metrics: Dict
    notes: str = ""

@dataclass
class CandidatePack:
    run_id: str
    candidates: List[Candidate]
    lineage: Lineage
    summary: Dict

    @staticmethod
    def new(cands: List[Candidate], lin: Lineage):
        rid = str(uuid.uuid4())[:8]
        best = max(cands, key=lambda c: c.metrics.get("score", 0.0), default=None)
        return CandidatePack(rid, cands, lin, {"best_id": getattr(best, "id", None), "num": len(cands)})
