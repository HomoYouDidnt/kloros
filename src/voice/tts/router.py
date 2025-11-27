from .adapters.xtts_v2 import XTTSBackend
from .adapters.kokoro import KokoroBackend
from .adapters.mimic3 import Mimic3Backend
from .adapters.piper import PiperBackend
import yaml, os

class TTSRouter:
    """Multi-backend TTS router with intent mapping and fallback."""

    def __init__(self, cfg_path: str = None, cfg_dict: dict = None):
        """Initialize router with config file or dict.

        Args:
            cfg_path: Path to YAML config file
            cfg_dict: Config dictionary (takes precedence over cfg_path)
        """
        if cfg_dict:
            self.cfg = cfg_dict
        elif cfg_path:
            with open(os.path.expanduser(cfg_path), "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f)
        else:
            # Default config
            self.cfg = {
                "audio": {"sample_rate": 22050},
                "router": {
                    "order": ["xtts_v2", "kokoro", "mimic3", "piper"],
                    "intent_map": {}
                },
                "xtts_v2": {"enabled": False},
                "kokoro": {"enabled": False},
                "mimic3": {"enabled": False},
                "piper": {"enabled": True, "model_path": "~/KLoROS/models/piper/glados_piper_medium.onnx"}
            }

        self.backends = {}

    def _get(self, name: str):
        """Get or create backend by name."""
        if name in self.backends:
            return self.backends[name]

        c = self.cfg.get(name, {})
        if name == "xtts_v2" and self.cfg.get("xtts_v2", {}).get("enabled", False):
            self.backends[name] = XTTSBackend(self.cfg)
        elif name == "kokoro" and self.cfg.get("kokoro", {}).get("enabled", False):
            self.backends[name] = KokoroBackend(self.cfg)
        elif name == "mimic3" and self.cfg.get("mimic3", {}).get("enabled", False):
            self.backends[name] = Mimic3Backend(self.cfg)
        elif name == "piper" and self.cfg.get("piper", {}).get("enabled", False):
            self.backends[name] = PiperBackend(self.cfg)
        else:
            self.backends[name] = None

        return self.backends[name]

    def pick(self, intent: str = "default", gpu_free: bool = True):
        """Pick best backend for intent.

        Args:
            intent: Intent string (e.g., "explain", "ack", "confirm")
            gpu_free: Whether GPU is available

        Returns:
            Backend instance or raises RuntimeError if none available
        """
        # Check intent map first
        intent_map = self.cfg.get("router", {}).get("intent_map", {})
        if intent in intent_map:
            b = self._get(intent_map[intent])
            if b:
                return b

        # Fall back to order
        for name in self.cfg.get("router", {}).get("order", ["xtts_v2", "kokoro", "mimic3", "piper"]):
            b = self._get(name)
            if b:
                return b

        raise RuntimeError("No TTS backends enabled")

    def start(self, backend):
        """Start a backend."""
        backend.start()

    def stop(self, backend):
        """Stop a backend."""
        backend.stop()
