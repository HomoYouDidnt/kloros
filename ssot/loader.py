"""SSOT Loader - Single Source of Truth configuration loader with invariant checks."""
import json
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import yaml
except ImportError:
    yaml = None


class SSOT:
    """Single Source of Truth configuration loader."""

    def __init__(self, root: str = None):
        """
        Initialize SSOT loader.

        Args:
            root: Config directory path (default: /home/kloros/config)
        """
        if root is None:
            root = os.environ.get("KLR_CONFIG_DIR", "/home/kloros/config")

        self.root = Path(root)
        if not self.root.exists():
            raise RuntimeError(f"Config directory not found: {self.root}")

        # Load configuration files
        self.models = self._load_toml(self.root / "models.toml")
        self.services = self._load_toml(self.root / "services.toml")
        self.emb_lock = self._load_json(self.root / "embeddings.lock.json")
        self.checksums = self._load_json(self.root / "checksums.json")

        # Load tools if available
        if yaml and (self.root / "tools.yaml").exists():
            self.tools = self._load_yaml(self.root / "tools.yaml")
        else:
            self.tools = {}

        # Initialize config watcher if enabled
        self.watcher = None
        if os.environ.get("KLR_CONFIG_WATCH", "true").lower() == "true":
            try:
                from ssot.config_watcher import setup_ssot_watcher
                self.watcher = setup_ssot_watcher(self.root, self._reload_callback)
            except Exception as e:
                print(f"[ssot] Warning: Failed to start config watcher: {e}", file=sys.stderr)

    def _load_toml(self, path: Path) -> dict:
        """Load TOML file."""
        if not path.exists():
            raise RuntimeError(f"Config file not found: {path}")
        with open(path, "rb") as f:
            return tomllib.load(f)

    def _load_json(self, path: Path) -> dict:
        """Load JSON file."""
        if not path.exists():
            raise RuntimeError(f"Config file not found: {path}")
        with open(path, "r") as f:
            return json.load(f)

    def _load_yaml(self, path: Path) -> dict:
        """Load YAML file."""
        if not path.exists():
            return {}
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    def embedder_id(self) -> str:
        """
        Generate embedder identity string.

        Returns:
            Embedder ID in format: model|norm:bool|dim:int
        """
        e = self.models["embeddings"]
        return f'{e["model"]}|norm:{e["normalize"]}|dim:{e["dim"]}'

    def assert_invariants(self, strict: bool = True) -> None:
        """
        Assert SSOT invariants - fail-closed on mismatch.

        Args:
            strict: If True, exit on any mismatch. If False, print warnings only.

        Raises:
            SystemExit: If invariants fail in strict mode
        """
        failures = []

        # 1) Embedding lock must match models.toml
        want_emb = self.embedder_id()
        have_emb = self.emb_lock.get("embedder_id")

        if want_emb != have_emb:
            msg = f"Embedder mismatch:\n  models.toml: {want_emb}\n  lock: {have_emb}\n  → Run: kloros-vec-rebuild"
            failures.append(msg)

        # 2) Tool count should match if lock has been built
        if self.emb_lock.get("built_at") and self.emb_lock.get("tool_count") != 47:
            msg = f"Tool count mismatch: lock has {self.emb_lock.get('tool_count')}, expected 47"
            failures.append(msg)

        # 3) Check file hashes for models with sha256 (if file paths are resolvable)
        for section_name, section in self.models.items():
            if isinstance(section, dict):
                self._check_section_hashes(section_name, section, failures)

        # Report results
        if failures:
            print("[FATAL] SSOT invariants failed:", file=sys.stderr)
            for f in failures:
                print(f"  • {f}", file=sys.stderr)
            if strict:
                sys.exit(1)
        else:
            print("[OK] SSOT invariants satisfied.")

    def _check_section_hashes(self, section_name: str, section: dict, failures: list) -> None:
        """Check file hashes for a config section."""
        if "sha256" in section and section["sha256"]:
            # Try to resolve model path
            if "model" in section:
                try:
                    path = resolve_model_path(section["model"])
                    if os.path.exists(path):
                        got_hash = sha256_file(path)
                        if got_hash != section["sha256"]:
                            failures.append(
                                f"Hash mismatch for {section_name}:{section['model']}\n"
                                f"    expected: {section['sha256']}\n"
                                f"    got: {got_hash}"
                            )
                except Exception as e:
                    # Model path resolution can fail for remote models
                    pass

    def get_embedder_model(self) -> str:
        """Get embedder model name."""
        return self.models["embeddings"]["model"]

    def get_embedder_normalize(self) -> bool:
        """Get embedder normalize flag."""
        return self.models["embeddings"]["normalize"]

    def get_embedder_dim(self) -> int:
        """Get embedder embedding dimension."""
        return self.models["embeddings"]["dim"]

    def get_embedder_fallbacks(self) -> list[str]:
        """Get fallback embedder models."""
        return self.models["embeddings"].get("fallbacks", {}).get("models", [])

    def get_embedder_trust_remote_code(self) -> bool:
        """Get embedder trust_remote_code flag."""
        return self.models["embeddings"].get("trust_remote_code", False)

    def get_ollama_model(self) -> str:
        """Get Ollama LLM model (defaults to main)."""
        return os.getenv("OLLAMA_MODEL", self.models["llm"]["main"]["model"])

    def get_ollama_url(self) -> str:
        """Get Ollama API URL (defaults to main)."""
        return os.getenv("OLLAMA_URL", self.models["llm"]["main"]["url"])

    def get_whisper_model(self) -> str:
        """Get Whisper STT model."""
        return os.getenv("KLR_WHISPER_MODEL", self.models["stt"]["whisper"]["model"])

    def get_piper_voice(self) -> str:
        """Get Piper TTS voice."""
        return os.getenv("KLR_PIPER_VOICE", self.models["tts"]["piper"]["voice"])

    def get_service_config(self, key: str, default: Any = None) -> Any:
        """Get service configuration value."""
        keys = key.split(".")
        val = self.services
        for k in keys:
            val = val.get(k, default)
            if val == default:
                return default
        return val

    def attestation(self) -> dict:
        """
        Generate runtime attestation data.

        Returns:
            Dict with current model IDs and versions
        """
        return {
            "embedder_id": self.embedder_id(),
            "models": {
                "embedder": self.get_embedder_model(),
                "ollama": self.get_ollama_model(),
                "whisper": self.get_whisper_model(),
                "piper": self.get_piper_voice(),
            },
            "lock": {
                "embedder_id": self.emb_lock.get("embedder_id"),
                "built_at": self.emb_lock.get("built_at"),
                "tool_count": self.emb_lock.get("tool_count"),
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    def _reload_callback(self, changed_files: list[str]):
        """Callback for config file changes - reload configurations."""
        print(f"[ssot] Config files changed: {changed_files}", file=sys.stderr)

        try:
            # Reload changed config files
            if "models" in changed_files:
                self.models = self._load_toml(self.root / "models.toml")
                print("[ssot] ✓ Reloaded models.toml", file=sys.stderr)

            if "services" in changed_files:
                self.services = self._load_toml(self.root / "services.toml")
                print("[ssot] ✓ Reloaded services.toml", file=sys.stderr)

            if "embeddings_lock" in changed_files:
                self.emb_lock = self._load_json(self.root / "embeddings.lock.json")
                print("[ssot] ✓ Reloaded embeddings.lock.json", file=sys.stderr)

            # Re-check invariants after reload
            print("[ssot] Checking invariants after reload...", file=sys.stderr)
            self.assert_invariants(strict=False)  # Warning only, don't exit
            print("[ssot] ✓ Configuration reloaded successfully", file=sys.stderr)

        except Exception as e:
            print(f"[ssot] ✗ Failed to reload configuration: {e}", file=sys.stderr)
            import traceback
            print(traceback.format_exc(), file=sys.stderr)


def sha256_file(path: str) -> str:
    """
    Compute SHA256 hash of file.

    Args:
        path: File path

    Returns:
        Hex digest of SHA256 hash
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_model_path(name: str) -> str:
    """
    Resolve model name to local file path.

    Args:
        name: Model name (e.g., HuggingFace ID or local name)

    Returns:
        Local file path

    Note:
        HuggingFace IDs are stored in ~/.cache/huggingface/hub/
        Custom models in KLR_MODELS_DIR or ~/.kloros/models
    """
    # Check if it's a HuggingFace model ID
    if "/" in name:
        # HF format: org/model -> models--org--model
        hf_name = name.replace("/", "--")
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        model_dir = os.path.join(cache_dir, f"models--{hf_name}")
        if os.path.exists(model_dir):
            return model_dir

    # Check custom models directory
    models_dir = os.environ.get("KLR_MODELS_DIR", "~/.kloros/models")
    models_dir = os.path.expanduser(models_dir)
    local_path = os.path.join(models_dir, name.replace("/", "__"))

    if os.path.exists(local_path):
        return local_path

    # Return name as-is if not found (let caller handle)
    return name


# Global instance
_SSOT = None


def get_ssot() -> SSOT:
    """Get or create global SSOT instance."""
    global _SSOT
    if _SSOT is None:
        _SSOT = SSOT()
    return _SSOT
