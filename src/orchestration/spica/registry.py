import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

class RegistrationError(Exception):
    pass

@dataclass
class CapabilityEntry:
    provider: str
    state: str
    socket: str
    version: str
    last_heartbeat: float

class CapabilityRegistry:
    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.storage_path.exists():
            self._save({"capabilities": {}})

        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        with open(self.storage_path) as f:
            return json.load(f)

    def _save(self, data: Dict[str, Any]):
        temp_path = self.storage_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self.storage_path)

    def register(
        self,
        capability: str,
        specialization: str,
        provider: str,
        socket: str,
        version: str,
        state: str = "INTEGRATED"
    ):
        if capability not in self.data["capabilities"]:
            self.data["capabilities"][capability] = {}

        self.data["capabilities"][capability][specialization] = {
            "provider": provider,
            "state": state,
            "socket": socket,
            "version": version,
            "last_heartbeat": time.time()
        }

        self._save(self.data)

    def query(self, capability: str, specialization: str) -> Optional[Dict[str, Any]]:
        return self.data["capabilities"].get(capability, {}).get(specialization)

    def heartbeat(self, provider: str):
        for capability_dict in self.data["capabilities"].values():
            for spec_name, entry in capability_dict.items():
                if entry["provider"] == provider:
                    entry["last_heartbeat"] = time.time()
                    self._save(self.data)
                    return

        raise RegistrationError(f"Provider not found: {provider}")

    def deregister(self, provider: str):
        for capability, capability_dict in list(self.data["capabilities"].items()):
            for spec_name, entry in list(capability_dict.items()):
                if entry["provider"] == provider:
                    del capability_dict[spec_name]
                    if not capability_dict:
                        del self.data["capabilities"][capability]
                    self._save(self.data)
                    return

        raise RegistrationError(f"Provider not found: {provider}")

    def list_all(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return self.data["capabilities"]

    def update_state(self, provider: str, new_state: str):
        for capability_dict in self.data["capabilities"].values():
            for entry in capability_dict.values():
                if entry["provider"] == provider:
                    entry["state"] = new_state
                    self._save(self.data)
                    return

        raise RegistrationError(f"Provider not found: {provider}")
