import itertools
import uuid
from typing import Any, Dict, List


def propose_candidates(baseline_cfg: Dict[str, Any], knobs: Dict[str, List], n: int = 4) -> List[Dict[str, Any]]:
    # Produce small YAML-able patches limited to knob grid.
    keys = list(knobs.keys())
    grid = list(itertools.product(*[knobs[k] for k in keys]))
    out = []
    for vals in grid[:n]:
        patch = {'id': str(uuid.uuid4()), 'knobs': dict(zip(keys, vals, strict=False))}
        out.append(patch)
    return out
