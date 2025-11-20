from dataclasses import dataclass
import yaml
import json
import os
import hashlib

@dataclass
class JudgingCfg:
    score_threshold: float
    novelty_threshold: float
    weights: dict

@dataclass
class AnchorsCfg:
    kl_tau: float
    holdout_regressions_block: bool
    rehearsal_fraction: float

@dataclass
class MixCfg:
    max_synthetic_ratio: float
    min_fresh_env_ratio: float
    replay_ratio: float

@dataclass
class RuntimeCfg:
    generator_sha: str
    judge_sha: str

@dataclass
class DreamConfig:
    judging: JudgingCfg
    anchors: AnchorsCfg
    mix: MixCfg
    runtime: RuntimeCfg

def _compute_content_hash() -> str:
    """Compute content hash of src/ + config for lineage tracking when git unavailable."""
    hasher = hashlib.sha256()

    # Hash key source files
    src_dir = "/home/kloros/src/dream"
    key_files = ["schema.py", "config.py", "admit.py", "judges/frozen.py"]

    for fname in key_files:
        fpath = os.path.join(src_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                hasher.update(f.read())

    # Hash config
    cfg_path = os.path.expanduser("~/.kloros/dream_config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "rb") as f:
            hasher.update(f.read())

    return f"content-{hasher.hexdigest()[:12]}"

def load_cfg(path=None) -> DreamConfig:
    """Load D-REAM config from YAML or JSON fallback."""
    if path is None:
        path = os.environ.get("DREAM_CFG_PATH", "configs/dream.yml")

    y = None

    # Try YAML first
    if os.path.exists(path):
        with open(path) as f:
            y = yaml.safe_load(f)
    else:
        # Fallback to JSON (check kloros home first, then current user)
        json_paths = [
            "/home/kloros/.kloros/dream_config.json",
            os.path.expanduser("~/.kloros/dream_config.json")
        ]
        y = None
        for home_json in json_paths:
            if os.path.exists(home_json):
                with open(home_json) as f:
                    y = json.load(f)
                break
        if y is None:
            raise FileNotFoundError(f"No config found at {path} or {json_paths}")

    # Auto-fill generator_sha if unknown
    if y["runtime"]["generator_sha"] == "UNKNOWN":
        y["runtime"]["generator_sha"] = _compute_content_hash()

    return DreamConfig(
        judging=JudgingCfg(**y["judging"]),
        anchors=AnchorsCfg(**y["anchors"]),
        mix=MixCfg(**y["mix"]),
        runtime=RuntimeCfg(**y["runtime"]),
    )
