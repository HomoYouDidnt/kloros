"""
Real-time reasoning trace system for KLoROS XAI (Explainable AI).

Captures the decision-making process during response generation to provide
transparency into how KLoROS arrives at her responses.
"""

from __future__ import annotations
import time
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum
from pathlib import Path


class ReasoningStepType(Enum):
    """Types of reasoning steps."""
    QUERY_RECEIVED = "query_received"
    QUERY_CLASSIFICATION = "query_classification"
    CONTEXT_RETRIEVAL = "context_retrieval"
    TOOL_DETECTION = "tool_detection"
    TOOL_EXECUTION = "tool_execution"
    LLM_GENERATION = "llm_generation"
    STREAMING_CHUNK = "streaming_chunk"
    RESPONSE_COMPLETE = "response_complete"
    ERROR = "error"


@dataclass
class ReasoningStep:
    """A single step in the reasoning process."""
    step_type: ReasoningStepType
    timestamp: float
    description: str
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result['step_type'] = self.step_type.value
        return result


@dataclass
class ReasoningTrace:
    """Complete reasoning trace for a single response."""
    trace_id: str
    user_query: str
    start_time: float
    steps: List[ReasoningStep] = field(default_factory=list)
    final_response: Optional[str] = None
    total_duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None

    def add_step(
        self,
        step_type: ReasoningStepType,
        description: str,
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        confidence: Optional[float] = None
    ) -> ReasoningStep:
        """Add a reasoning step to the trace."""
        step = ReasoningStep(
            step_type=step_type,
            timestamp=time.time(),
            description=description,
            data=data or {},
            duration_ms=duration_ms,
            confidence=confidence
        )
        self.steps.append(step)
        return step

    def complete(self, final_response: str, success: bool = True, error: Optional[str] = None):
        """Mark the trace as complete."""
        self.final_response = final_response
        self.total_duration_ms = (time.time() - self.start_time) * 1000
        self.success = success
        self.error_message = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'trace_id': self.trace_id,
            'user_query': self.user_query,
            'start_time': self.start_time,
            'steps': [step.to_dict() for step in self.steps],
            'final_response': self.final_response,
            'total_duration_ms': self.total_duration_ms,
            'success': self.success,
            'error_message': self.error_message
        }

    def to_human_readable(self) -> str:
        """Generate human-readable explanation of the reasoning process."""
        lines = []
        lines.append(f"=== Reasoning Trace: {self.trace_id[:8]} ===")
        lines.append(f"Query: {self.user_query}")
        lines.append(f"Duration: {self.total_duration_ms:.0f}ms\n")

        for i, step in enumerate(self.steps, 1):
            duration_str = f" ({step.duration_ms:.0f}ms)" if step.duration_ms else ""
            confidence_str = f" [confidence: {step.confidence:.2f}]" if step.confidence else ""
            lines.append(f"{i}. {step.step_type.value.upper()}{duration_str}{confidence_str}")
            lines.append(f"   {step.description}")

            # Add relevant data details
            if step.data:
                if step.step_type == ReasoningStepType.CONTEXT_RETRIEVAL:
                    doc_count = step.data.get('retrieved_count', 0)
                    top_score = step.data.get('top_score', 0)
                    lines.append(f"   → Retrieved {doc_count} docs (top score: {top_score:.3f})")
                elif step.step_type == ReasoningStepType.TOOL_DETECTION:
                    tool_name = step.data.get('tool_name', 'unknown')
                    lines.append(f"   → Tool: {tool_name}")
                elif step.step_type == ReasoningStepType.LLM_GENERATION:
                    tokens = step.data.get('tokens_generated', 0)
                    model = step.data.get('model', 'unknown')
                    lines.append(f"   → Model: {model}, Tokens: {tokens}")
            lines.append("")

        if self.success:
            lines.append(f"✓ Response: {self.final_response[:100]}...")
        else:
            lines.append(f"✗ Error: {self.error_message}")

        return "\n".join(lines)


class ReasoningTracer:
    """Manages reasoning traces for KLoROS responses."""

    def __init__(self, log_dir: Optional[str] = None, max_traces: int = 100):
        """Initialize the reasoning tracer.

        Args:
            log_dir: Directory to store trace logs (None to disable file logging)
            max_traces: Maximum number of traces to keep in memory
        """
        self.log_dir = Path(log_dir) if log_dir else None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self.max_traces = max_traces
        self.active_traces: Dict[str, ReasoningTrace] = {}
        self.completed_traces: List[ReasoningTrace] = []

    def start_trace(self, trace_id: str, user_query: str) -> ReasoningTrace:
        """Start a new reasoning trace."""
        trace = ReasoningTrace(
            trace_id=trace_id,
            user_query=user_query,
            start_time=time.time()
        )
        self.active_traces[trace_id] = trace

        # Add initial step
        trace.add_step(
            ReasoningStepType.QUERY_RECEIVED,
            f"Received query: {user_query[:80]}...",
            data={'query_length': len(user_query)}
        )

        return trace

    def get_trace(self, trace_id: str) -> Optional[ReasoningTrace]:
        """Get an active or completed trace by ID."""
        if trace_id in self.active_traces:
            return self.active_traces[trace_id]

        for trace in self.completed_traces:
            if trace.trace_id == trace_id:
                return trace

        return None

    def complete_trace(self, trace_id: str, final_response: str, success: bool = True, error: Optional[str] = None):
        """Complete a reasoning trace."""
        trace = self.active_traces.get(trace_id)
        if not trace:
            return

        trace.complete(final_response, success, error)

        # Move to completed traces
        del self.active_traces[trace_id]
        self.completed_traces.append(trace)

        # Trim if needed
        if len(self.completed_traces) > self.max_traces:
            self.completed_traces = self.completed_traces[-self.max_traces:]

        # Log to file if enabled
        if self.log_dir:
            self._log_trace_to_file(trace)

        print(f"[xai] Reasoning trace {trace_id[:8]} completed: {trace.total_duration_ms:.0f}ms")

    def _log_trace_to_file(self, trace: ReasoningTrace):
        """Log trace to JSON file."""
        try:
            timestamp = int(trace.start_time)
            filename = f"trace_{timestamp}_{trace.trace_id[:8]}.json"
            filepath = self.log_dir / filename

            with open(filepath, 'w') as f:
                json.dump(trace.to_dict(), f, indent=2)

        except Exception as e:
            print(f"[xai] Failed to log trace to file: {e}")

        # Also export to dashboard directory for real-time display
        self._export_trace_for_dashboard(trace)

    def _export_trace_for_dashboard(self, trace: ReasoningTrace):
        """
        Export trace to dashboard-compatible format.

        Converts the trace to match the XAITrace model expected by the dashboard.
        """
        try:
            dashboard_dir = Path("/tmp/kloros_xai_traces")
            dashboard_dir.mkdir(parents=True, exist_ok=True)

            # Convert to dashboard format
            dashboard_trace = {
                "decision_id": trace.trace_id,
                "decision_type": "response_generation",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(trace.start_time)),
                "question": trace.user_query,
                "final_decision": trace.final_response[:200] if trace.final_response else "No response generated",
                "reasoning_steps": [
                    {
                        "step": i + 1,
                        "description": step.description,
                        "inputs": {
                            "step_type": step.step_type.value,
                            "timestamp": step.timestamp
                        },
                        "outputs": step.data,
                        "confidence": step.confidence if step.confidence is not None else 0.8
                    }
                    for i, step in enumerate(trace.steps)
                ],
                "confidence": 0.85 if trace.success else 0.3,
                "alternatives_considered": []  # Could be enhanced later
            }

            # Write to dashboard directory
            filename = f"{trace.trace_id}.json"
            filepath = dashboard_dir / filename

            with open(filepath, 'w') as f:
                json.dump(dashboard_trace, f, indent=2)

        except Exception as e:
            print(f"[xai] Failed to export trace for dashboard: {e}")

    def get_recent_traces(self, limit: int = 10) -> List[ReasoningTrace]:
        """Get recent completed traces."""
        return self.completed_traces[-limit:]

    def get_trace_summary(self, trace_id: str) -> Optional[str]:
        """Get human-readable summary of a trace."""
        trace = self.get_trace(trace_id)
        if not trace:
            return None

        return trace.to_human_readable()

    def get_last_trace_summary(self) -> Optional[str]:
        """Get summary of the most recent trace."""
        if not self.completed_traces:
            return "No reasoning traces available"

        return self.completed_traces[-1].to_human_readable()


# Global tracer instance
_global_tracer: Optional[ReasoningTracer] = None


def get_tracer() -> ReasoningTracer:
    """Get or create the global reasoning tracer."""
    global _global_tracer
    if _global_tracer is None:
        log_dir = Path.home() / ".kloros" / "reasoning_traces"
        _global_tracer = ReasoningTracer(log_dir=str(log_dir), max_traces=100)
    return _global_tracer


def start_trace(trace_id: str, user_query: str) -> ReasoningTrace:
    """Convenience function to start a trace."""
    return get_tracer().start_trace(trace_id, user_query)


def get_trace(trace_id: str) -> Optional[ReasoningTrace]:
    """Convenience function to get a trace."""
    return get_tracer().get_trace(trace_id)


def complete_trace(trace_id: str, final_response: str, success: bool = True, error: Optional[str] = None):
    """Convenience function to complete a trace."""
    get_tracer().complete_trace(trace_id, final_response, success, error)
