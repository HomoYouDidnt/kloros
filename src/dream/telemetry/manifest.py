#!/usr/bin/env python3
"""
D-REAM Run Manifest Module
Manifest generation and management for evolution runs.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class RunManifest:
    """Evolution run manifest with reproducibility information."""

    def __init__(self, run_id: str, config: Dict[str, Any]):
        """
        Initialize run manifest.

        Args:
            run_id: Unique run identifier
            config: Run configuration
        """
        self.run_id = run_id
        self.config = config
        self.timestamp = datetime.now().isoformat()
        self.code_hashes = {}
        self.artifacts = {}
        self.random_seeds = {}
        self.regimes = []
        self.metadata = {}

    def add_code_hash(self, file_path: str):
        """Add hash of a code file."""
        path = Path(file_path)
        if path.exists():
            content = path.read_text(encoding='utf-8')
            hash_val = hashlib.sha256(content.encode()).hexdigest()
            self.code_hashes[str(path)] = f"sha256:{hash_val}"
            logger.debug(f"Hashed {path}: {hash_val[:8]}...")

    def add_artifact(self, artifact_type: str, path: str):
        """Add artifact path."""
        self.artifacts[artifact_type] = path

    def set_seeds(self, seeds: Dict[str, int]):
        """Set random seeds used."""
        self.random_seeds = seeds

    def set_regimes(self, regime_names: List[str]):
        """Set evaluation regime names."""
        self.regimes = regime_names

    def compute_config_hash(self) -> str:
        """Compute hash of configuration."""
        config_str = json.dumps(self.config, sort_keys=True)
        return f"sha256:{hashlib.sha256(config_str.encode()).hexdigest()}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "config_hash": self.compute_config_hash(),
            "code_hashes": self.code_hashes,
            "artifacts": self.artifacts,
            "random_seeds": self.random_seeds,
            "regimes": self.regimes,
            "metadata": self.metadata,
            "config": self.config
        }

    def save(self, path: str):
        """Save manifest to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        logger.info(f"Saved manifest to {path}")

    @classmethod
    def load(cls, path: str) -> 'RunManifest':
        """Load manifest from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        manifest = cls(data['run_id'], data['config'])
        manifest.timestamp = data['timestamp']
        manifest.code_hashes = data.get('code_hashes', {})
        manifest.artifacts = data.get('artifacts', {})
        manifest.random_seeds = data.get('random_seeds', {})
        manifest.regimes = data.get('regimes', [])
        manifest.metadata = data.get('metadata', {})
        
        return manifest


class ManifestManager:
    """Manage collection of run manifests."""

    def __init__(self, manifests_dir: str = "artifacts/manifests"):
        """
        Initialize manifest manager.

        Args:
            manifests_dir: Directory for manifests
        """
        self.manifests_dir = Path(manifests_dir)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def create_manifest(self, config: Dict[str, Any]) -> RunManifest:
        """Create new manifest for run."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}_{hashlib.sha256(str(config).encode()).hexdigest()[:8]}"
        
        manifest = RunManifest(run_id, config)
        
        # Hash critical source files
        source_files = [
            "src/dream/fitness.py",
            "src/dream/novelty.py",
            "src/dream/evaluation_plan.py",
            "src/evolutionary_optimization.py"
        ]
        
        for file_path in source_files:
            if Path(file_path).exists():
                manifest.add_code_hash(file_path)
        
        return manifest

    def save_manifest(self, manifest: RunManifest) -> str:
        """Save manifest and return path."""
        path = self.manifests_dir / f"{manifest.run_id}.json"
        manifest.save(str(path))
        return str(path)

    def load_manifest(self, run_id: str) -> Optional[RunManifest]:
        """Load manifest by run ID."""
        path = self.manifests_dir / f"{run_id}.json"
        if path.exists():
            return RunManifest.load(str(path))
        return None

    def list_manifests(self) -> List[str]:
        """List all manifest run IDs."""
        manifests = []
        for path in self.manifests_dir.glob("*.json"):
            manifest_id = path.stem
            manifests.append(manifest_id)
        return sorted(manifests)

    def compare_manifests(self, run_id1: str, run_id2: str) -> Dict[str, Any]:
        """Compare two manifests for differences."""
        m1 = self.load_manifest(run_id1)
        m2 = self.load_manifest(run_id2)
        
        if not m1 or not m2:
            return {"error": "One or both manifests not found"}
        
        differences = {
            "config_same": m1.compute_config_hash() == m2.compute_config_hash(),
            "seeds_same": m1.random_seeds == m2.random_seeds,
            "code_changes": []
        }
        
        # Compare code hashes
        for file_path in set(m1.code_hashes.keys()) | set(m2.code_hashes.keys()):
            hash1 = m1.code_hashes.get(file_path)
            hash2 = m2.code_hashes.get(file_path)
            
            if hash1 != hash2:
                differences["code_changes"].append({
                    "file": file_path,
                    "hash1": hash1,
                    "hash2": hash2
                })
        
        return differences


def create_reproducibility_report(manifest: RunManifest) -> str:
    """
    Create human-readable reproducibility report.

    Args:
        manifest: Run manifest

    Returns:
        Report text
    """
    report = []
    report.append(f"D-REAM Run Reproducibility Report")
    report.append("=" * 50)
    report.append(f"Run ID: {manifest.run_id}")
    report.append(f"Timestamp: {manifest.timestamp}")
    report.append(f"Config Hash: {manifest.compute_config_hash()[:16]}...")
    report.append("")
    
    report.append("Random Seeds:")
    for name, seed in manifest.random_seeds.items():
        report.append(f"  {name}: {seed}")
    report.append("")
    
    report.append("Code Versions:")
    for file_path, hash_val in manifest.code_hashes.items():
        report.append(f"  {Path(file_path).name}: {hash_val[7:15]}...")
    report.append("")
    
    report.append("Evaluation Regimes:")
    for regime in manifest.regimes:
        report.append(f"  - {regime}")
    report.append("")
    
    report.append("Artifacts:")
    for artifact_type, path in manifest.artifacts.items():
        report.append(f"  {artifact_type}: {path}")
    
    return "\n".join(report)
