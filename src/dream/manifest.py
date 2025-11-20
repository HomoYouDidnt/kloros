#!/usr/bin/env python3
"""
Run manifest generation for D-REAM.
Tracks seeds, code hashes, and configuration for each run.
"""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from baseline import hash_code


def generate_run_id() -> str:
    """Generate unique run ID with timestamp."""
    return time.strftime("%Y-%m-%dT%H-%M-%S") + f"_r{int(time.time()) % 1000}"


def write_manifest(
    run_id: str,
    domains: List[str],
    config_paths: List[str],
    code_paths: List[str],
    seed_map: Dict[str, int],
    sinq_meta: Optional[Dict] = None,
    output_dir: str = "/home/kloros/src/dream/artifacts/manifests"
) -> Path:
    """
    Write run manifest for traceability.
    
    Args:
        run_id: Unique run identifier
        domains: List of domain names being evaluated
        config_paths: Paths to configuration files
        code_paths: Paths to key source files
        seed_map: Dictionary of seeds (e.g., {"python": 1337, "numpy": 1337})
        sinq_meta: Optional SINQ metadata if using quantization
        output_dir: Directory to write manifest
    
    Returns:
        Path to written manifest file
    """
    manifest = {
        "run_id": run_id,
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "domains": domains,
        "seeds": seed_map,
        "code_hash": hash_code(code_paths),
        "configs": {
            Path(p).name: hash_code([p]) for p in config_paths if Path(p).exists()
        },
        "sinq": sinq_meta or {"enabled": False}
    }
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    filepath = output_path / f"{run_id}.json"
    filepath.write_text(json.dumps(manifest, indent=2))
    
    return filepath


def load_manifest(run_id: str, manifest_dir: str = "/home/kloros/src/dream/artifacts/manifests") -> Optional[Dict]:
    """
    Load manifest for a specific run.
    
    Args:
        run_id: Run identifier
        manifest_dir: Directory containing manifests
    
    Returns:
        Manifest dict or None if not found
    """
    filepath = Path(manifest_dir) / f"{run_id}.json"
    if not filepath.exists():
        return None
    
    return json.loads(filepath.read_text())
