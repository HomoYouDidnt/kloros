"""Failure specification DSL and loader."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import yaml
from pathlib import Path


@dataclass
class FailureSpec:
    """Declarative failure scenario specification."""

    id: str
    target: str  # "dream.domain:cpu", "tts", "rag.synthesis", "validator"
    mode: str  # "timeout"|"race"|"deadlock"|"oom"|"corrupt"|"quota"|"latency"|"jitter"
    params: Dict = field(default_factory=dict)
    triggers: List[Dict] = field(default_factory=list)  # when/how to inject
    guards: Dict = field(default_factory=dict)  # safety: max_duration, abort_on_event
    expected: Dict = field(default_factory=dict)  # expected heal events / metrics deltas

    def __repr__(self) -> str:
        return f"<FailureSpec {self.id}: {self.target}/{self.mode}>"


def load_specs(path: str) -> List[FailureSpec]:
    """Load failure specs from YAML file.

    Args:
        path: Path to YAML file with failure scenarios

    Returns:
        List of FailureSpec objects
    """
    spec_file = Path(path)

    if not spec_file.exists():
        print(f"[chaos] Spec file not found: {path}")
        return []

    try:
        with open(spec_file, 'r') as f:
            raw = yaml.safe_load(f) or []

        # Handle both list format and dict with 'scenarios' key
        if isinstance(raw, dict):
            raw = raw.get('scenarios', [])

        specs = [FailureSpec(**r) for r in raw]
        print(f"[chaos] Loaded {len(specs)} failure scenarios from {path}")
        return specs

    except Exception as e:
        print(f"[chaos] Failed to load specs: {e}")
        return []


def save_spec(spec: FailureSpec, path: str):
    """Save a single failure spec to YAML.

    Args:
        spec: FailureSpec to save
        path: Path to save to
    """
    data = {
        'id': spec.id,
        'target': spec.target,
        'mode': spec.mode,
        'params': spec.params,
        'triggers': spec.triggers,
        'guards': spec.guards,
        'expected': spec.expected
    }

    with open(path, 'w') as f:
        yaml.dump([data], f, default_flow_style=False, sort_keys=False)
