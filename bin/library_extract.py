#!/usr/bin/env python3
"""
Pattern Library Extractor - Phase 3

Scans winner bundles → fingerprints → clusters → writes snippet manifests.
"""
from __future__ import annotations
import ast, hashlib, json, os, re, sys, time
from pathlib import Path
from typing import Dict, List, Tuple

WINNERS = Path("/home/kloros/artifacts/dream/winners")
LIBROOT = Path("/home/kloros/toolgen/library")
SNIPPETS = LIBROOT / "patterns"  # patterns/<spec_id>/<cluster_id>/
SNIPPETS.mkdir(parents=True, exist_ok=True)

def sha256(s: bytes) -> str:
    return hashlib.sha256(s).hexdigest()

def ast_fingerprint(code: str) -> str:
    """Generate AST-based fingerprint for code."""
    try:
        tree = ast.parse(code)
        dump = ast.dump(tree, annotate_fields=False, include_attributes=False)
        return "ast:" + sha256(dump.encode())
    except Exception:
        return "ast:ERR"

def token_ngrams(code: str, n=5) -> List[str]:
    """Extract token n-grams for similarity."""
    toks = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|==|!=|<=|>=|[-+/*%=<>()[\]{}.,:;]", code)
    return [" ".join(toks[i:i+n]) for i in range(max(0, len(toks)-n+1))]

def minhash_fingerprint(code: str, n=5, buckets=64) -> str:
    """Generate MinHash fingerprint for near-duplicate detection."""
    ngrams = token_ngrams(code, n=n)
    if not ngrams:
        return "tok:EMPTY"
    hashes = [int(sha256(x.encode()), 16) for x in ngrams]
    # Take k smallest as sketch
    sketch = sorted(hashes)[:buckets]
    b = b"".join(h.to_bytes(32, "big") for h in sketch)
    return "tok:" + sha256(b)

def read_json(p: Path) -> dict:
    """Safely read JSON file."""
    try:
        return json.loads(p.read_text())
    except:
        return {}

def gather_winners() -> List[dict]:
    """Collect all winner records from artifacts."""
    items: List[dict] = []

    # Canonical single-file per domain
    p = WINNERS / "spica_toolgen.json"
    if p.exists():
        j = read_json(p)
        if isinstance(j, dict):
            # Extract best from winner structure
            best = j.get("best", {})
            metrics = best.get("metrics", {})
            if metrics.get("bundle_path"):
                items.append({
                    "bundle_dir": metrics.get("bundle_path"),
                    "spec_id": metrics.get("tool_id") or best.get("params", {}).get("spec_id"),
                    "spec_path": f"/home/kloros/toolgen/specs/{metrics.get('tool_id')}.json",
                    "fitness": best.get("fitness"),
                    "median_ms": metrics.get("median_ms"),
                    "stability": 1.0,  # Winners are stable by definition
                    "correctness": metrics.get("correctness"),
                    "safety": metrics.get("safety"),
                    "performance": metrics.get("performance"),
                })
        elif isinstance(j, list):
            items.extend(j)

    # Optional historical store (JSONL)
    jl = WINNERS / "spica_toolgen.jsonl"
    if jl.exists():
        for line in jl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except:
                pass

    # De-duplicate
    seen = set()
    uniq = []
    for it in items:
        bundle_dir = it.get("bundle_dir", "")
        spec_id = it.get("spec_id") or Path(it.get("spec_path", "")).stem
        key = (bundle_dir, spec_id)
        if key in seen or not bundle_dir:
            continue
        seen.add(key)
        uniq.append(it)

    return uniq

def extract_snippet(bundle_dir: Path) -> Tuple[str, str]:
    """Extract code and fingerprint from bundle."""
    # Try multiple locations
    candidates = [
        bundle_dir / "tool.py",
        bundle_dir / "tool" / "tool.py",
        bundle_dir / "__init__.py",
    ]

    for candidate in candidates:
        if candidate.exists():
            code = candidate.read_text()
            return code, ast_fingerprint(code)

    raise FileNotFoundError(f"No tool code found in {bundle_dir}")

def cluster_by_fingerprint(items: List[dict]) -> Dict[str, List[dict]]:
    """Group winners by AST fingerprint."""
    clusters: Dict[str, List[dict]] = {}

    for it in items:
        try:
            bundle_path = Path(it["bundle_dir"])
            if not bundle_path.exists():
                continue
            code, afp = extract_snippet(bundle_path)
        except Exception as e:
            print(f"[library_extract] skip {it.get('bundle_dir')}: {e}")
            continue

        tfp = minhash_fingerprint(code)
        it["_code"] = code
        it["_afp"] = afp
        it["_tfp"] = tfp

        # Cluster by AST fingerprint (exact match)
        clusters.setdefault(afp, []).append(it)

    return clusters

def write_cluster(spec_id: str, cid: str, members: List[dict]):
    """Write cluster manifest and snippet to library."""
    d = SNIPPETS / spec_id / cid
    d.mkdir(parents=True, exist_ok=True)

    # Choose the fastest stable member as canonical snippet
    best = sorted(
        members,
        key=lambda m: (-(m.get("stability", 1.0)), m.get("median_ms", 9e9))
    )[0]

    (d / "snippet.py").write_text(best["_code"])

    manifest = {
        "spec_id": spec_id,
        "cluster_id": cid,
        "fingerprints": list({m["_afp"] for m in members}) + list({m["_tfp"] for m in members}),
        "quality": {
            "wins": len(members),
            "median_ms": min([m.get("median_ms", 9e9) for m in members]),
            "stability": min([m.get("stability", 1.0) for m in members])
        },
        "interfaces": [{"fn": guess_export_fn(best["_code"]), "sig": "<inferred>"}],
        "constraints": {"deps": [], "forbidden_calls": []},
        "provenance": [
            {
                "bundle_dir": m.get("bundle_dir"),
                "sha256": directory_hash(Path(m.get("bundle_dir")))
            }
            for m in members
            if m.get("bundle_dir") and Path(m.get("bundle_dir")).exists()
        ],
        "ts": time.time()
    }

    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"  ✓ Cluster {cid}: {len(members)} members, {manifest['quality']['median_ms']:.2f}ms")

def guess_export_fn(code: str) -> str:
    """Infer the main export function name."""
    try:
        t = ast.parse(code)
        for n in t.body:
            if isinstance(n, ast.FunctionDef):
                return n.name
    except:
        pass
    return "tool"

def directory_hash(path: Path) -> str:
    """Calculate SHA256 hash of directory contents."""
    h = hashlib.sha256()
    try:
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(path).as_posix().encode())
                h.update(p.read_bytes())
    except Exception:
        return "unknown"
    return h.hexdigest()

def main():
    print("[library_extract] Scanning winners...")
    winners = gather_winners()
    print(f"[library_extract] Found {len(winners)} winner records")

    # Per-spec clusters
    per_spec: Dict[str, List[dict]] = {}
    for it in winners:
        spec_id = it.get("spec_id") or Path(it.get("spec_path", "")).stem
        per_spec.setdefault(spec_id, []).append(it)

    total_clusters = 0
    for spec_id, items in per_spec.items():
        print(f"\n[library_extract] Processing spec: {spec_id}")
        clusters = cluster_by_fingerprint(items)

        for i, (k, members) in enumerate(clusters.items(), start=1):
            write_cluster(spec_id, f"c{i:04d}", members)
            total_clusters += 1

    print(f"\n[library_extract] ✓ Wrote {total_clusters} clusters to: {SNIPPETS}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
