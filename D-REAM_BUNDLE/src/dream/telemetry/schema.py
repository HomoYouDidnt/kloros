#!/usr/bin/env python3
"""
D-REAM Telemetry Schema Module
Event schema definitions and validation.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from enum import Enum
import json


class EventLevel(str, Enum):
    """Event severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """Standard event types."""
    # Lifecycle events
    RUN_START = "run_start"
    RUN_END = "run_end"
    GENERATION_START = "generation_start"
    GENERATION_END = "generation_end"
    
    # Evaluation events
    CANDIDATE_EVAL = "candidate_eval"
    FITNESS_CALC = "fitness_calc"
    NOVELTY_CALC = "novelty_calc"
    REGIME_EVAL = "regime_eval"
    
    # Selection events
    SELECTION = "selection"
    PARETO_FRONT = "pareto_front"
    ARCHIVE_UPDATE = "archive_update"
    
    # Mutation events
    MUTATION = "mutation"
    CROSSOVER = "crossover"
    
    # Deployment events
    PATCH_CREATE = "patch_create"
    PATCH_APPLY = "patch_apply"
    PATCH_ROLLBACK = "patch_rollback"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESULT = "approval_result"
    
    # Safety events
    SAFETY_CHECK = "safety_check"
    SAFETY_VIOLATION = "safety_violation"
    RESOURCE_LIMIT = "resource_limit"
    
    # Metrics
    METRIC = "metric"
    TIMER_START = "timer_start"
    TIMER_STOP = "timer_stop"


@dataclass
class BaseEvent:
    """Base event structure."""
    event_type: EventType
    timestamp: float
    payload: Dict[str, Any]
    level: EventLevel = EventLevel.INFO
    tags: Dict[str, str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['level'] = self.level.value
        return data

    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps(self.to_dict())


@dataclass
class RunEvent(BaseEvent):
    """Run lifecycle event."""
    run_id: str
    config_hash: str
    seed: int
    
    @classmethod
    def start(cls, run_id: str, config_hash: str, seed: int) -> 'RunEvent':
        return cls(
            event_type=EventType.RUN_START,
            timestamp=time.time(),
            run_id=run_id,
            config_hash=config_hash,
            seed=seed,
            payload={"status": "started"}
        )


@dataclass
class FitnessEvent(BaseEvent):
    """Fitness calculation event."""
    candidate_id: str
    fitness_score: float
    components: Dict[str, float]
    regime: Optional[str] = None
    
    @classmethod
    def create(cls, candidate_id: str, score: float, 
               components: Dict[str, float], regime: str = None) -> 'FitnessEvent':
        return cls(
            event_type=EventType.FITNESS_CALC,
            timestamp=time.time(),
            candidate_id=candidate_id,
            fitness_score=score,
            components=components,
            regime=regime,
            payload={
                "candidate_id": candidate_id,
                "score": score,
                "components": components
            }
        )


@dataclass
class SafetyEvent(BaseEvent):
    """Safety check event."""
    check_type: str
    passed: bool
    details: Dict[str, Any]
    
    @classmethod
    def violation(cls, check_type: str, details: Dict[str, Any]) -> 'SafetyEvent':
        return cls(
            event_type=EventType.SAFETY_VIOLATION,
            timestamp=time.time(),
            level=EventLevel.WARNING,
            check_type=check_type,
            passed=False,
            details=details,
            payload={
                "check_type": check_type,
                "passed": False,
                "details": details
            }
        )


class EventValidator:
    """Validate events against schema."""
    
    REQUIRED_FIELDS = {
        "ts": float,
        "event": str,
        "payload": dict
    }
    
    @classmethod
    def validate(cls, event_data: Dict) -> bool:
        """Validate event structure."""
        for field, expected_type in cls.REQUIRED_FIELDS.items():
            if field not in event_data:
                return False
            if not isinstance(event_data[field], expected_type):
                return False
        return True

    @classmethod
    def validate_jsonl(cls, path: str) -> tuple[int, int]:
        """
        Validate all events in a JSONL file.
        
        Returns:
            Tuple of (valid_count, invalid_count)
        """
        valid = 0
        invalid = 0
        
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line)
                    if cls.validate(data):
                        valid += 1
                    else:
                        invalid += 1
                        logger.warning(f"Invalid event at line {line_num}")
                except json.JSONDecodeError:
                    invalid += 1
                    logger.warning(f"Invalid JSON at line {line_num}")
        
        return valid, invalid


def create_event(event_type: str, **kwargs) -> Dict[str, Any]:
    """Factory function for creating events."""
    import time
    
    event = {
        "ts": time.time(),
        "event": event_type,
        "payload": kwargs
    }
    
    # Add optional fields
    if "level" in kwargs:
        event["level"] = kwargs.pop("level")
    if "tags" in kwargs:
        event["tags"] = kwargs.pop("tags")
    
    return event
