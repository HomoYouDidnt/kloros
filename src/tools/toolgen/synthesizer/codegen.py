"""
ToolGen Code Generator: Stub implementation generating Python code from spec.

In production, this would be LLM-driven with few-shot examples.
For PoC, we emit hardcoded working implementation.
"""
from typing import Dict, Any
import json
import shutil
from pathlib import Path

# Corrected implementation for text deduplication
DEDUPE_CODE = '''from typing import List, Tuple

def deduplicate_lines(text: str, threshold: float = 0.8) -> str:
    """Remove near-duplicate lines while preserving order.

    Rules:
    - threshold >= 0.9999: exact duplicate removal on the *raw* stripped line (case-sensitive).
    - threshold < 1.0: near-duplicate via Jaccard over lowercased token sets.
      When a near-duplicate is found, keep the "most informative" representative:
        * more tokens wins
        * tie-break by longer character length
        * if still tied, keep the earlier line
    """
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln != ""]

    if threshold >= 0.9999:
        seen_raw = set()
        out = []
        for ln in lines:
            if ln not in seen_raw:
                seen_raw.add(ln)
                out.append(ln)
        return "\\n".join(out)

    def norm_tokens(s: str) -> List[str]:
        return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in s).split()).split()

    # Each entry: (raw_line, token_set, token_count, char_len, first_index)
    reps: List[Tuple[str, set, int, int, int]] = []

    for idx, ln in enumerate(lines):
        toks = set(norm_tokens(ln))
        tokc = len(toks)
        chlen = len(ln)

        # Try to match an existing representative by Jaccard
        match_i = -1
        best_sim = -1.0
        for i, (_r, stoks, _c, _L, _idx0) in enumerate(reps):
            inter = len(toks & stoks)
            union = len(toks | stoks) or 1
            sim = inter / union
            if sim > best_sim:
                best_sim = sim
                match_i = i

        if best_sim >= threshold:
            # candidate duplicate; decide if we should replace the representative
            r_line, r_stoks, r_tokc, r_len, r_idx0 = reps[match_i]
            replace = False
            if tokc > r_tokc:
                replace = True
            elif tokc == r_tokc and chlen > r_len:
                replace = True

            if replace:
                reps[match_i] = (ln, toks, tokc, chlen, r_idx0)
        else:
            reps.append((ln, toks, tokc, chlen, idx))

    # Reconstruct in the order representatives first appeared
    reps.sort(key=lambda t: t[4])
    return "\\n".join([r[0] for r in reps])
'''

LIBROOT = Path.home() / "toolgen" / "library" / "patterns"

def seed_from_library(bundle_dir: str, spec_path: str) -> bool:
    """
    Attempt to seed synthesis from pattern library.

    If successful, copies snippet and writes marker for telemetry.

    Args:
        bundle_dir: Output directory for tool bundle
        spec_path: Path to spec JSON file

    Returns:
        True if seeded from library, False if no match found
    """
    spec_id = Path(spec_path).stem
    pattern_dir = LIBROOT / spec_id

    if not pattern_dir.exists():
        return False

    # Pick best cluster by quality (fastest, then most wins)
    best_cluster = None
    best_score = (float('inf'), -1)  # (median_ms, wins)
    best_manifest = None

    for cluster_path in sorted(pattern_dir.iterdir()):
        manifest_file = cluster_path / "manifest.json"
        if not manifest_file.exists():
            continue

        try:
            manifest = json.loads(manifest_file.read_text())
            quality = manifest.get("quality", {})
            score = (quality.get("median_ms", float('inf')), quality.get("wins", 0))

            if score < best_score:
                best_score = score
                best_cluster = cluster_path
                best_manifest = manifest
        except Exception:
            continue

    if not best_cluster:
        return False

    # Copy snippet to bundle
    tool_dir = Path(bundle_dir) / "tool"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "__init__.py").write_text("from .tool import *\n")
    shutil.copy2(best_cluster / "snippet.py", tool_dir / "tool.py")

    # Write telemetry marker
    marker = {
        "pattern_id": f'{best_manifest["spec_id"]}:{best_manifest["cluster_id"]}',
        "pattern_dir": str(best_cluster),
        "pattern_quality": best_manifest.get("quality", {}),
        "source": "seed"  # vs "match" added by evaluator
    }
    (Path(bundle_dir) / "library_seed.json").write_text(json.dumps(marker, indent=2))

    return True

# Implementation for json flattening
FLATTEN_CODE = '''def flatten_json(data: dict, parent_key: str = "", sep: str = ".") -> dict:
    """
    Flatten nested JSON dict to single-level dict with dot/bracket paths.

    Arrays use bracket notation: x[0], x[1]
    Nested dicts use dot notation: a.b.c
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, elem in enumerate(v):
                list_key = f"{new_key}[{i}]"
                if isinstance(elem, dict):
                    items.extend(flatten_json(elem, list_key, sep=sep).items())
                else:
                    items.append((list_key, elem))
        else:
            items.append((new_key, v))
    return dict(items)
'''

def generate_code(spec: Dict[str, Any], plan: list) -> str:
    """
    Generate Python implementation code for the tool.

    Args:
        spec: Tool specification dict
        plan: List of implementation steps from planner

    Returns:
        Python source code as string
    """
    spec_id = spec.get("id", spec.get("tool_id", ""))

    # Branch on spec id to select implementation
    if "json_flatten" in spec_id:
        return FLATTEN_CODE
    elif "text_deduplicate" in spec_id or spec.get("tool_id") == "text_deduplicate":
        return DEDUPE_CODE
    else:
        # Fallback: return dedupe for unknown specs
        return DEDUPE_CODE
