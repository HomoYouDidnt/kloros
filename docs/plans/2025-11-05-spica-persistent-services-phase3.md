# SPICA Persistent Services (Phase 3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable long-running specialized SPICA agents with lifecycle management, IPC, and capability registry.

**Architecture:** Implement state machine (PLURIPOTENT → INTEGRATED), DR YAML system, Unix socket RPC server, capability registry, and systemd service orchestration. Tournament mode (active) continues unchanged; this adds persistent service mode.

**Tech Stack:** Python 3.11+, YAML, Unix domain sockets, JSON-RPC, systemd, pytest

**Prerequisites:**
- Phase 0-2 complete (✅ tournament mode, ResourceGovernor, observability)
- SPICA template exists at `/home/kloros/experiments/spica/template/`
- Virtual environment at `/home/kloros/.venv/`

**Timeline Estimate:** 2-4 weeks (8 tasks × 2-3 days each)

---

## Task 1: State Machine Implementation

**Goal:** Implement SPICA lifecycle states (PLURIPOTENT → PRIMED → DIFFERENTIATING → SPECIALIZED → INTEGRATED → REPROGRAM).

**Files:**
- Create: `/home/kloros/src/spica/lifecycle.py`
- Create: `/home/kloros/tests/spica/test_lifecycle.py`

### Step 1: Write failing test for state machine

Create test file:

```python
import pytest
from src.spica.lifecycle import LifecycleStateMachine, LifecycleState

def test_initial_state_is_pluripotent():
    sm = LifecycleStateMachine()
    assert sm.current_state == LifecycleState.PLURIPOTENT

def test_transition_pluripotent_to_primed():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path/to/dr.yaml"})
    assert sm.current_state == LifecycleState.PRIMED

def test_invalid_transition_raises_error():
    sm = LifecycleStateMachine()
    with pytest.raises(ValueError, match="Invalid transition"):
        sm.transition_to(LifecycleState.SPECIALIZED)

def test_reprogram_from_integrated_to_pluripotent():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path"})
    sm.transition_to(LifecycleState.DIFFERENTIATING)
    sm.transition_to(LifecycleState.SPECIALIZED)
    sm.transition_to(LifecycleState.INTEGRATED)
    sm.reprogram()
    assert sm.current_state == LifecycleState.PLURIPOTENT
    assert sm.history[-1]["event"] == "reprogram"

def test_state_history_tracking():
    sm = LifecycleStateMachine()
    sm.transition_to(LifecycleState.PRIMED, metadata={"dr_path": "/path"})
    assert len(sm.history) == 2
    assert sm.history[0]["state"] == LifecycleState.PLURIPOTENT
    assert sm.history[1]["state"] == LifecycleState.PRIMED
```

### Step 2: Run test to verify it fails

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_lifecycle.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.spica.lifecycle'"

### Step 3: Implement state machine

Create implementation file:

```python
import time
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

class LifecycleState(Enum):
    PLURIPOTENT = "pluripotent"
    PRIMED = "primed"
    DIFFERENTIATING = "differentiating"
    SPECIALIZED = "specialized"
    INTEGRATED = "integrated"

@dataclass
class StateTransition:
    from_state: LifecycleState
    to_state: LifecycleState
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    event: str = "transition"

class LifecycleStateMachine:
    VALID_TRANSITIONS = {
        LifecycleState.PLURIPOTENT: [LifecycleState.PRIMED],
        LifecycleState.PRIMED: [LifecycleState.DIFFERENTIATING],
        LifecycleState.DIFFERENTIATING: [LifecycleState.SPECIALIZED],
        LifecycleState.SPECIALIZED: [LifecycleState.INTEGRATED],
        LifecycleState.INTEGRATED: [LifecycleState.PLURIPOTENT],
    }

    def __init__(self):
        self.current_state = LifecycleState.PLURIPOTENT
        self.history: List[StateTransition] = [
            StateTransition(
                from_state=LifecycleState.PLURIPOTENT,
                to_state=LifecycleState.PLURIPOTENT,
                timestamp=time.time(),
                event="init"
            )
        ]

    def transition_to(self, new_state: LifecycleState, metadata: Optional[Dict[str, Any]] = None):
        if new_state not in self.VALID_TRANSITIONS.get(self.current_state, []):
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {new_state.value}"
            )

        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=time.time(),
            metadata=metadata or {},
            event="transition"
        )
        self.history.append(transition)
        self.current_state = new_state

    def reprogram(self):
        if self.current_state != LifecycleState.INTEGRATED:
            raise ValueError("Can only reprogram from INTEGRATED state")

        transition = StateTransition(
            from_state=self.current_state,
            to_state=LifecycleState.PLURIPOTENT,
            timestamp=time.time(),
            event="reprogram"
        )
        self.history.append(transition)
        self.current_state = LifecycleState.PLURIPOTENT

    def get_state(self) -> Dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "history_length": len(self.history),
            "last_transition": self.history[-1].timestamp if self.history else None
        }
```

### Step 4: Run test to verify it passes

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_lifecycle.py -v
```

Expected: PASS (5/5 tests)

### Step 5: Commit

```bash
cd /home/kloros
git add src/spica/lifecycle.py tests/spica/test_lifecycle.py
git commit -m "feat(spica): implement lifecycle state machine

- Add LifecycleState enum (PLURIPOTENT -> INTEGRATED)
- Implement state transition validation
- Add reprogram capability (INTEGRATED -> PLURIPOTENT)
- Track state history with timestamps and metadata
- Full test coverage"
```

---

## Task 2: Differentiation Recipe (DR) Schema & Loader

**Goal:** Implement YAML schema for differentiation recipes and validation logic.

**Files:**
- Create: `/home/kloros/src/spica/differentiation.py`
- Create: `/home/kloros/tests/spica/test_differentiation.py`
- Create: `/etc/kloros/recipes/spica/observer-health.yaml` (example DR)

### Step 1: Write failing test for DR loader

```python
import pytest
import yaml
from pathlib import Path
from src.spica.differentiation import DifferentiationRecipe, load_recipe, ValidationError

def test_load_valid_recipe(tmp_path):
    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: observer-health
  version: "1.0"
spec:
  target_capability: observer
  specialization: health-monitoring
  prompt_config:
    system_prompt: "You are a health observer."
  pipeline:
    - cell: health_monitor
      config:
        threshold: 80
  safety:
    max_tokens: 8192
    kl_drift_persona: 0.5
  resources:
    memory: "2Gi"
    cpu: "1.0"
"""
    recipe_path = tmp_path / "test.yaml"
    recipe_path.write_text(recipe_yaml)

    recipe = load_recipe(recipe_path)
    assert recipe.metadata["name"] == "observer-health"
    assert recipe.spec["target_capability"] == "observer"
    assert recipe.spec["safety"]["max_tokens"] == 8192

def test_load_invalid_recipe_missing_apiVersion(tmp_path):
    recipe_yaml = """
kind: DifferentiationRecipe
metadata:
  name: test
"""
    recipe_path = tmp_path / "bad.yaml"
    recipe_path.write_text(recipe_yaml)

    with pytest.raises(ValidationError, match="Missing required field: apiVersion"):
        load_recipe(recipe_path)

def test_load_invalid_recipe_wrong_kind(tmp_path):
    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: WrongKind
"""
    recipe_path = tmp_path / "bad.yaml"
    recipe_path.write_text(recipe_yaml)

    with pytest.raises(ValidationError, match="kind must be 'DifferentiationRecipe'"):
        load_recipe(recipe_path)

def test_recipe_to_dict():
    recipe = DifferentiationRecipe(
        apiVersion="spica.kloros/v1",
        kind="DifferentiationRecipe",
        metadata={"name": "test"},
        spec={"target_capability": "observer"}
    )
    data = recipe.to_dict()
    assert data["metadata"]["name"] == "test"
```

### Step 2: Run test to verify it fails

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_differentiation.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.spica.differentiation'"

### Step 3: Implement DR loader

```python
import yaml
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field

class ValidationError(Exception):
    pass

@dataclass
class DifferentiationRecipe:
    apiVersion: str
    kind: str
    metadata: Dict[str, Any]
    spec: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "apiVersion": self.apiVersion,
            "kind": self.kind,
            "metadata": self.metadata,
            "spec": self.spec
        }

    def validate(self):
        if self.apiVersion != "spica.kloros/v1":
            raise ValidationError(f"Unsupported apiVersion: {self.apiVersion}")

        if self.kind != "DifferentiationRecipe":
            raise ValidationError(f"kind must be 'DifferentiationRecipe', got: {self.kind}")

        required_metadata = ["name", "version"]
        for field in required_metadata:
            if field not in self.metadata:
                raise ValidationError(f"Missing required metadata field: {field}")

        required_spec = ["target_capability", "prompt_config", "pipeline", "safety"]
        for field in required_spec:
            if field not in self.spec:
                raise ValidationError(f"Missing required spec field: {field}")

def load_recipe(path: Path) -> DifferentiationRecipe:
    if not path.exists():
        raise FileNotFoundError(f"Recipe not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required_top_level = ["apiVersion", "kind", "metadata", "spec"]
    for field in required_top_level:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

    recipe = DifferentiationRecipe(
        apiVersion=data["apiVersion"],
        kind=data["kind"],
        metadata=data["metadata"],
        spec=data["spec"]
    )

    recipe.validate()
    return recipe
```

### Step 4: Run test to verify it passes

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_differentiation.py -v
```

Expected: PASS (4/4 tests)

### Step 5: Create example DR file

```bash
sudo mkdir -p /etc/kloros/recipes/spica
sudo tee /etc/kloros/recipes/spica/observer-health.yaml > /dev/null << 'EOF'
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: observer-health
  version: "1.0"
  description: "Health monitoring observer for ASTRAEA components"
spec:
  target_capability: observer
  specialization: health-monitoring

  prompt_config:
    system_prompt: |
      You are a health observer for ASTRAEA system components.
      Monitor telemetry streams and report anomalies.
      Focus on: CPU, memory, disk, GPU utilization.
      Alert on: thresholds exceeded, sudden changes, unusual patterns.

  pipeline:
    - cell: health_monitor
      config:
        thresholds:
          cpu: 80
          memory: 90
          disk: 95
          gpu: 85
        window_seconds: 300

    - cell: anomaly_detector
      config:
        sensitivity: 0.8
        baseline_window: 3600

  safety:
    max_tokens: 8192
    kl_drift_persona: 0.5
    kl_drift_task: 1.0
    timeout_seconds: 60

  resources:
    memory: "2Gi"
    cpu: "1.0"
EOF
```

### Step 6: Commit

```bash
cd /home/kloros
git add src/spica/differentiation.py tests/spica/test_differentiation.py
git commit -m "feat(spica): add differentiation recipe loader

- Implement DR YAML schema (apiVersion, kind, metadata, spec)
- Add validation for required fields
- Create load_recipe() function with error handling
- Add example observer-health.yaml recipe
- Full test coverage with tmp_path fixtures"
```

---

## Task 3: IPC RPC Server (Unix Sockets)

**Goal:** Implement JSON-RPC server over Unix domain sockets for SPICA communication.

**Files:**
- Create: `/home/kloros/src/spica/rpc_server.py`
- Create: `/home/kloros/tests/spica/test_rpc_server.py`

### Step 1: Write failing test for RPC server

```python
import pytest
import json
import socket
from pathlib import Path
from src.spica.rpc_server import RPCServer, rpc_method

def test_rpc_server_starts_and_stops(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))
    server.start()
    assert socket_path.exists()
    server.stop()

def test_rpc_method_registration():
    socket_path = "/tmp/test-rpc.sock"
    server = RPCServer(socket_path)

    @rpc_method(server)
    def test_method(params):
        return {"result": params["value"] * 2}

    assert "test_method" in server.methods

def test_rpc_call_via_socket(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def echo(params):
        return {"echoed": params.get("message", "")}

    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "echo",
        "params": {"message": "hello"},
        "id": "test-123"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert data["result"]["echoed"] == "hello"
    assert data["id"] == "test-123"

    client.close()
    server.stop()

def test_rpc_error_on_unknown_method(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))
    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "unknown_method",
        "params": {},
        "id": "test-456"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32601
    assert "not found" in data["error"]["message"]

    client.close()
    server.stop()
```

### Step 2: Run test to verify it fails

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_rpc_server.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.spica.rpc_server'"

### Step 3: Implement RPC server

```python
import json
import socket
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)

class RPCError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

class RPCServer:
    def __init__(self, socket_path: str):
        self.socket_path = Path(socket_path)
        self.methods: Dict[str, Callable] = {}
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def register_method(self, name: str, handler: Callable):
        self.methods[name] = handler
        logger.info(f"Registered RPC method: {name}")

    def start(self):
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(str(self.socket_path))
        self.server_socket.listen(5)
        self.socket_path.chmod(0o600)

        self.running = True
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()

        logger.info(f"RPC server started on {self.socket_path}")

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if self.socket_path.exists():
            self.socket_path.unlink()
        logger.info("RPC server stopped")

    def _accept_loop(self):
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=True
                ).start()
            except OSError:
                break

    def _handle_client(self, client_socket: socket.socket):
        try:
            data = client_socket.recv(4096)
            if not data:
                return

            request = json.loads(data.decode())
            response = self._process_request(request)

            client_socket.sendall(json.dumps(response).encode() + b"\n")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def _process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request.get("id")
        method_name = request.get("method")
        params = request.get("params", {})

        if method_name not in self.methods:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method_name}"
                },
                "id": request_id
            }

        try:
            result = self.methods[method_name](params)
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "id": request_id
            }

def rpc_method(server: RPCServer):
    def decorator(func: Callable):
        server.register_method(func.__name__, func)
        return func
    return decorator
```

### Step 4: Run test to verify it passes

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_rpc_server.py -v
```

Expected: PASS (4/4 tests)

### Step 5: Commit

```bash
cd /home/kloros
git add src/spica/rpc_server.py tests/spica/test_rpc_server.py
git commit -m "feat(spica): implement JSON-RPC server over Unix sockets

- Add RPCServer class with start/stop lifecycle
- Implement JSON-RPC 2.0 protocol (request/response)
- Add @rpc_method decorator for handler registration
- Thread-based client handling
- Error handling (method not found, internal errors)
- Full test coverage with tmp_path sockets"
```

---

## Task 4: Capability Registry

**Goal:** Central coordination for tracking SPICA capabilities, providers, and status.

**Files:**
- Create: `/home/kloros/src/spica/registry.py`
- Create: `/home/kloros/tests/spica/test_registry.py`

### Step 1: Write failing test for capability registry

```python
import pytest
import json
from pathlib import Path
from src.spica.registry import CapabilityRegistry, RegistrationError

def test_registry_initialization(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)
    assert registry.storage_path == registry_path
    assert registry_path.exists()

def test_register_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    result = registry.query("observer", "health")
    assert result["provider"] == "spica-observer@health"
    assert result["state"] == "INTEGRATED"
    assert result["socket"] == "/run/spica/observer-health.sock"

def test_query_nonexistent_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    result = registry.query("nonexistent", "capability")
    assert result is None

def test_heartbeat_updates_timestamp(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    first_heartbeat = registry.query("observer", "health")["last_heartbeat"]
    registry.heartbeat("spica-observer@health")
    second_heartbeat = registry.query("observer", "health")["last_heartbeat"]

    assert second_heartbeat > first_heartbeat

def test_deregister_capability(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register(
        capability="observer",
        specialization="health",
        provider="spica-observer@health",
        socket="/run/spica/observer-health.sock",
        version="1.0"
    )

    assert registry.query("observer", "health") is not None
    registry.deregister("spica-observer@health")
    assert registry.query("observer", "health") is None

def test_list_all_capabilities(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = CapabilityRegistry(registry_path)

    registry.register("observer", "health", "provider1", "/sock1", "1.0")
    registry.register("observer", "gpu", "provider2", "/sock2", "1.0")
    registry.register("ranker", "default", "provider3", "/sock3", "1.0")

    capabilities = registry.list_all()
    assert len(capabilities) == 3
    assert "observer" in capabilities
    assert len(capabilities["observer"]) == 2
```

### Step 2: Run test to verify it fails

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_registry.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.spica.registry'"

### Step 3: Implement capability registry

```python
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
```

### Step 4: Run test to verify it passes

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_registry.py -v
```

Expected: PASS (6/6 tests)

### Step 5: Create production registry storage

```bash
sudo mkdir -p /var/lib/kloros
sudo touch /var/lib/kloros/spica_registry.json
sudo chmod 600 /var/lib/kloros/spica_registry.json
echo '{"capabilities": {}}' | sudo tee /var/lib/kloros/spica_registry.json
```

### Step 6: Commit

```bash
cd /home/kloros
git add src/spica/registry.py tests/spica/test_registry.py
git commit -m "feat(spica): implement capability registry

- Add CapabilityRegistry with JSON storage
- Support register/query/heartbeat/deregister operations
- Track provider state (INTEGRATED, SPECIALIZED, etc.)
- Atomic file writes with temp file + replace
- list_all() for debugging and monitoring
- Full test coverage with tmp_path fixtures"
```

---

## Task 5: Service Lifecycle Manager

**Goal:** Integrate state machine, DR loader, RPC server, and registry into service lifecycle.

**Files:**
- Create: `/home/kloros/src/spica/service_manager.py`
- Create: `/home/kloros/tests/spica/test_service_manager.py`

### Step 1: Write failing test for service manager

```python
import pytest
from pathlib import Path
from src.spica.service_manager import SPICAServiceManager
from src.spica.lifecycle import LifecycleState

def test_service_manager_initialization(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    manager = SPICAServiceManager(
        role="observer-health",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    assert manager.role == "observer-health"
    assert manager.lifecycle.current_state == LifecycleState.PLURIPOTENT

def test_differentiate_loads_recipe_and_transitions(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: observer-health
  version: "1.0"
spec:
  target_capability: observer
  specialization: health-monitoring
  prompt_config:
    system_prompt: "You are a health observer."
  pipeline:
    - cell: health_monitor
  safety:
    max_tokens: 8192
  resources:
    memory: "2Gi"
"""
    recipe_path = tmp_path / "test-recipe.yaml"
    recipe_path.write_text(recipe_yaml)

    manager = SPICAServiceManager(
        role="observer-health",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    result = manager.differentiate(str(recipe_path))

    assert result["success"] is True
    assert manager.lifecycle.current_state == LifecycleState.INTEGRATED
    assert manager.recipe is not None
    assert manager.recipe.metadata["name"] == "observer-health"

def test_reprogram_resets_to_pluripotent(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: test
  version: "1.0"
spec:
  target_capability: observer
  specialization: health
  prompt_config:
    system_prompt: "test"
  pipeline: []
  safety:
    max_tokens: 8192
  resources:
    memory: "2Gi"
"""
    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text(recipe_yaml)

    manager = SPICAServiceManager(
        role="test",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    manager.differentiate(str(recipe_path))
    assert manager.lifecycle.current_state == LifecycleState.INTEGRATED

    result = manager.reprogram()
    assert result["success"] is True
    assert manager.lifecycle.current_state == LifecycleState.PLURIPOTENT
    assert manager.recipe is None

def test_get_status_returns_current_state(tmp_path):
    socket_path = tmp_path / "test.sock"
    registry_path = tmp_path / "registry.json"

    manager = SPICAServiceManager(
        role="test",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    status = manager.get_status()
    assert status["role"] == "test"
    assert status["state"] == "pluripotent"
    assert status["recipe"] is None
```

### Step 2: Run test to verify it fails

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_service_manager.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.spica.service_manager'"

### Step 3: Implement service manager

```python
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from src.spica.lifecycle import LifecycleStateMachine, LifecycleState
from src.spica.differentiation import DifferentiationRecipe, load_recipe
from src.spica.rpc_server import RPCServer, rpc_method
from src.spica.registry import CapabilityRegistry

logger = logging.getLogger(__name__)

class SPICAServiceManager:
    def __init__(
        self,
        role: str,
        socket_path: str,
        registry_path: Path,
    ):
        self.role = role
        self.socket_path = socket_path

        self.lifecycle = LifecycleStateMachine()
        self.registry = CapabilityRegistry(registry_path)
        self.rpc_server = RPCServer(socket_path)

        self.recipe: Optional[DifferentiationRecipe] = None

        self._register_rpc_methods()

    def _register_rpc_methods(self):
        @rpc_method(self.rpc_server)
        def differentiate(params):
            recipe_path = params["recipe_path"]
            result = self.differentiate(recipe_path)
            return result

        @rpc_method(self.rpc_server)
        def query_state(params):
            return self.get_status()

        @rpc_method(self.rpc_server)
        def reprogram(params):
            return self.reprogram()

    def differentiate(self, recipe_path: str) -> Dict[str, Any]:
        try:
            self.lifecycle.transition_to(LifecycleState.PRIMED, metadata={"recipe_path": recipe_path})

            self.recipe = load_recipe(Path(recipe_path))

            self.lifecycle.transition_to(LifecycleState.DIFFERENTIATING)

            self._apply_recipe()

            self.lifecycle.transition_to(LifecycleState.SPECIALIZED)

            capability = self.recipe.spec["target_capability"]
            specialization = self.recipe.spec["specialization"]

            self.registry.register(
                capability=capability,
                specialization=specialization,
                provider=self.role,
                socket=self.socket_path,
                version=self.recipe.metadata["version"],
                state="SPECIALIZED"
            )

            self.lifecycle.transition_to(LifecycleState.INTEGRATED)

            self.registry.update_state(self.role, "INTEGRATED")

            logger.info(f"SPICA {self.role} differentiated to {capability}/{specialization}")

            return {
                "success": True,
                "capability": capability,
                "specialization": specialization,
                "state": self.lifecycle.current_state.value
            }

        except Exception as e:
            logger.error(f"Differentiation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _apply_recipe(self):
        pass

    def reprogram(self) -> Dict[str, Any]:
        try:
            if self.recipe:
                capability = self.recipe.spec["target_capability"]
                specialization = self.recipe.spec["specialization"]

                self.registry.deregister(self.role)

            self.lifecycle.reprogram()
            self.recipe = None

            logger.info(f"SPICA {self.role} reprogrammed to PLURIPOTENT")

            return {
                "success": True,
                "state": self.lifecycle.current_state.value
            }

        except Exception as e:
            logger.error(f"Reprogram failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "state": self.lifecycle.current_state.value,
            "recipe": self.recipe.metadata["name"] if self.recipe else None,
            "socket": self.socket_path
        }

    def start(self):
        self.rpc_server.start()
        logger.info(f"SPICA service {self.role} started")

    def stop(self):
        if self.recipe and self.lifecycle.current_state == LifecycleState.INTEGRATED:
            try:
                self.registry.deregister(self.role)
            except Exception as e:
                logger.warning(f"Failed to deregister on stop: {e}")

        self.rpc_server.stop()
        logger.info(f"SPICA service {self.role} stopped")
```

### Step 4: Run test to verify it passes

```bash
/home/kloros/.venv/bin/pytest tests/spica/test_service_manager.py -v
```

Expected: PASS (4/4 tests)

### Step 5: Commit

```bash
cd /home/kloros
git add src/spica/service_manager.py tests/spica/test_service_manager.py
git commit -m "feat(spica): implement service lifecycle manager

- Integrate state machine, DR loader, RPC server, registry
- Add differentiate() method (PLURIPOTENT -> INTEGRATED)
- Add reprogram() method (INTEGRATED -> PLURIPOTENT)
- Auto-register RPC methods (differentiate, query_state, reprogram)
- Registry integration (register on INTEGRATED, deregister on reprogram/stop)
- Full test coverage"
```

---

## Task 6: Systemd Service Entry Point

**Goal:** Create CLI entry point for systemd service units to launch SPICA services.

**Files:**
- Create: `/home/kloros/src/spica/__main__.py`
- Modify: `/etc/systemd/system/spica@.service`

### Step 1: Write CLI entry point

```python
import sys
import signal
import logging
from pathlib import Path
from src.spica.service_manager import SPICAServiceManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2 or not sys.argv[1].startswith("--role="):
        print("Usage: python -m src.spica --role=<role-name>")
        sys.exit(1)

    role = sys.argv[1].split("=", 1)[1]
    socket_path = f"/run/spica/spica-{role}.sock"
    registry_path = Path("/var/lib/kloros/spica_registry.json")

    manager = SPICAServiceManager(
        role=role,
        socket_path=socket_path,
        registry_path=registry_path
    )

    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        manager.start()
        logger.info(f"SPICA service {role} running at {socket_path}")

        signal.pause()

    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Step 2: Update systemd service template

```bash
sudo tee /etc/systemd/system/spica@.service > /dev/null << 'EOF'
[Unit]
Description=SPICA Service - %i
Documentation=file:///home/kloros/docs/SPICA_ARCHITECTURE_SPEC.md
After=network.target kloros-orchestrator.service
PartOf=kloros.target

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros

Environment="PYTHONPATH=/home/kloros"
ExecStart=/home/kloros/.venv/bin/python3 -m src.spica --role=%i

Restart=on-failure
RestartSec=10s

MemoryMax=4G
CPUQuota=200%

PrivateNetwork=yes
ProtectSystem=strict
ReadWritePaths=/run/spica /var/lib/kloros

StandardOutput=journal
StandardError=journal
SyslogIdentifier=spica-%i

[Install]
WantedBy=multi-user.target kloros.target
EOF
```

### Step 3: Create socket directory

```bash
sudo mkdir -p /run/spica
sudo chown kloros:kloros /run/spica
sudo chmod 700 /run/spica
```

### Step 4: Test service manually (without systemd)

```bash
cd /home/kloros
/home/kloros/.venv/bin/python3 -m src.spica --role=test-observer &
SPICA_PID=$!

sleep 2

ls -la /run/spica/

kill $SPICA_PID
```

Expected: Socket file created at `/run/spica/spica-test-observer.sock`

### Step 5: Reload systemd and verify template

```bash
sudo systemctl daemon-reload
sudo systemctl cat spica@observer-health.service
```

Expected: Service definition displayed with correct ExecStart

### Step 6: Commit

```bash
cd /home/kloros
git add src/spica/__main__.py
git commit -m "feat(spica): add systemd service entry point

- Create __main__.py CLI for service launching
- Parse --role= argument for service name
- Setup signal handlers (SIGTERM, SIGINT) for graceful shutdown
- Update spica@.service template with correct ExecStart
- Add resource limits (4G RAM, 200% CPU)
- Add security hardening (PrivateNetwork, ProtectSystem)
- Logging to journald with spica-%i identifier"
```

---

## Task 7: Integration Tests

**Goal:** End-to-end tests covering full differentiation lifecycle.

**Files:**
- Create: `/home/kloros/tests/integration/test_spica_lifecycle.py`

### Step 1: Write integration test

```python
import pytest
import json
import socket
import time
from pathlib import Path
from src.spica.service_manager import SPICAServiceManager

@pytest.fixture
def integration_setup(tmp_path):
    socket_path = tmp_path / "integration.sock"
    registry_path = tmp_path / "registry.json"
    recipe_path = tmp_path / "recipe.yaml"

    recipe_yaml = """
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: integration-test
  version: "1.0"
spec:
  target_capability: observer
  specialization: test-integration
  prompt_config:
    system_prompt: "Integration test observer"
  pipeline:
    - cell: test_cell
      config:
        test: true
  safety:
    max_tokens: 8192
    kl_drift_persona: 0.5
  resources:
    memory: "2Gi"
    cpu: "1.0"
"""
    recipe_path.write_text(recipe_yaml)

    manager = SPICAServiceManager(
        role="integration-test",
        socket_path=str(socket_path),
        registry_path=registry_path
    )

    manager.start()
    time.sleep(0.1)

    yield {
        "manager": manager,
        "socket_path": socket_path,
        "registry_path": registry_path,
        "recipe_path": recipe_path
    }

    manager.stop()

def rpc_call(socket_path, method, params):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": f"test-{int(time.time() * 1000)}"
    }

    client.sendall(json.dumps(request).encode() + b"\n")
    response = client.recv(4096)
    data = json.loads(response.decode())

    client.close()
    return data

def test_full_differentiation_lifecycle(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    status = rpc_call(socket_path, "query_state", {})
    assert status["result"]["state"] == "pluripotent"

    result = rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})
    assert result["result"]["success"] is True
    assert result["result"]["state"] == "integrated"

    status = rpc_call(socket_path, "query_state", {})
    assert status["result"]["state"] == "integrated"
    assert status["result"]["recipe"] == "integration-test"

    registry_entry = manager.registry.query("observer", "test-integration")
    assert registry_entry is not None
    assert registry_entry["provider"] == "integration-test"
    assert registry_entry["state"] == "INTEGRATED"

def test_reprogram_lifecycle(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})
    assert manager.lifecycle.current_state.value == "integrated"

    result = rpc_call(socket_path, "reprogram", {})
    assert result["result"]["success"] is True
    assert result["result"]["state"] == "pluripotent"

    registry_entry = manager.registry.query("observer", "test-integration")
    assert registry_entry is None

def test_multiple_heartbeats(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})

    first = manager.registry.query("observer", "test-integration")
    time.sleep(0.1)

    manager.registry.heartbeat("integration-test")
    second = manager.registry.query("observer", "test-integration")

    assert second["last_heartbeat"] > first["last_heartbeat"]
```

### Step 2: Run integration tests

```bash
/home/kloros/.venv/bin/pytest tests/integration/test_spica_lifecycle.py -v -s
```

Expected: PASS (3/3 tests)

### Step 3: Commit

```bash
cd /home/kloros
git add tests/integration/test_spica_lifecycle.py
git commit -m "test(spica): add end-to-end integration tests

- Test full differentiation lifecycle (PLURIPOTENT -> INTEGRATED)
- Test RPC communication (query_state, differentiate, reprogram)
- Test registry integration (register/deregister)
- Test reprogram lifecycle (INTEGRATED -> PLURIPOTENT)
- Test heartbeat mechanism
- All tests use tmp_path fixtures for isolation"
```

---

## Task 8: Service Activation & Deployment

**Goal:** Unmask services, create initial DRs, deploy first SPICA instances.

**Files:**
- Create: `/etc/kloros/recipes/spica/observer-gpu.yaml`
- Create: `/etc/kloros/recipes/spica/ranker-default.yaml`
- Modify: Systemd service units (unmask)

### Step 1: Create additional DR files

```bash
sudo tee /etc/kloros/recipes/spica/observer-gpu.yaml > /dev/null << 'EOF'
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: observer-gpu
  version: "1.0"
  description: "GPU telemetry observer"
spec:
  target_capability: observer
  specialization: gpu-monitoring

  prompt_config:
    system_prompt: |
      You are a GPU telemetry observer for ASTRAEA.
      Monitor GPU utilization, memory, temperature, power draw.
      Alert on: thermal throttling, memory pressure, utilization anomalies.

  pipeline:
    - cell: gpu_monitor
      config:
        thresholds:
          temperature: 85
          utilization: 95
          memory: 90
        window_seconds: 60

  safety:
    max_tokens: 8192
    kl_drift_persona: 0.5
    kl_drift_task: 1.0
    timeout_seconds: 60

  resources:
    memory: "2Gi"
    cpu: "1.0"
EOF

sudo tee /etc/kloros/recipes/spica/ranker-default.yaml > /dev/null << 'EOF'
apiVersion: spica.kloros/v1
kind: DifferentiationRecipe
metadata:
  name: ranker-default
  version: "1.0"
  description: "Multi-objective ranking cell"
spec:
  target_capability: ranker
  specialization: multi-objective

  prompt_config:
    system_prompt: |
      You are a multi-objective ranker for candidate solutions.
      Balance multiple criteria: performance, efficiency, novelty, safety.
      Use Pareto dominance and crowding distance.

  pipeline:
    - cell: pareto_ranker
      config:
        objectives: ["fitness", "novelty", "efficiency"]
        weights: [0.5, 0.3, 0.2]

  safety:
    max_tokens: 16384
    kl_drift_persona: 0.5
    kl_drift_task: 1.0
    timeout_seconds: 120

  resources:
    memory: "3Gi"
    cpu: "1.5"
EOF

sudo chmod 644 /etc/kloros/recipes/spica/*.yaml
```

### Step 2: Test DR loading

```bash
/home/kloros/.venv/bin/python3 -c "
from pathlib import Path
from src.spica.differentiation import load_recipe

recipes = [
    '/etc/kloros/recipes/spica/observer-health.yaml',
    '/etc/kloros/recipes/spica/observer-gpu.yaml',
    '/etc/kloros/recipes/spica/ranker-default.yaml'
]

for recipe_path in recipes:
    try:
        recipe = load_recipe(Path(recipe_path))
        print(f'✓ {recipe.metadata[\"name\"]} loaded successfully')
    except Exception as e:
        print(f'✗ {recipe_path} failed: {e}')
"
```

Expected: All 3 recipes load successfully

### Step 3: Unmask service units (staged deployment)

```bash
sudo systemctl unmask spica@observer-health.service
sudo systemctl unmask spica@observer-gpu.service
sudo systemctl unmask spica@ranker-default.service

sudo systemctl daemon-reload
```

### Step 4: Start first SPICA service (observer-health)

```bash
sudo systemctl start spica@observer-health.service

sleep 2

sudo systemctl status spica@observer-health.service
journalctl -u spica@observer-health.service -n 20 --no-pager
```

Expected: Service running, socket created, no errors in logs

### Step 5: Test RPC communication with running service

```bash
/home/kloros/.venv/bin/python3 << 'EOF'
import json
import socket

def rpc_call(socket_path, method, params):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(socket_path)

    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": "test-001"
    }

    client.sendall(json.dumps(request).encode() + b"\n")
    response = client.recv(4096)
    client.close()

    return json.loads(response.decode())

socket_path = "/run/spica/spica-observer-health.sock"

status = rpc_call(socket_path, "query_state", {})
print("Status:", json.dumps(status, indent=2))

result = rpc_call(socket_path, "differentiate", {
    "recipe_path": "/etc/kloros/recipes/spica/observer-health.yaml"
})
print("Differentiation:", json.dumps(result, indent=2))

status_after = rpc_call(socket_path, "query_state", {})
print("Status after:", json.dumps(status_after, indent=2))
EOF
```

Expected: State transitions PLURIPOTENT → INTEGRATED, no errors

### Step 6: Verify capability registry

```bash
cat /var/lib/kloros/spica_registry.json | jq .
```

Expected: observer/health-monitoring entry with spica-observer-health provider

### Step 7: Enable services for auto-start

```bash
sudo systemctl enable spica@observer-health.service
sudo systemctl enable spica@observer-gpu.service
sudo systemctl enable spica@ranker-default.service
```

### Step 8: Start remaining services

```bash
sudo systemctl start spica@observer-gpu.service
sudo systemctl start spica@ranker-default.service

sleep 2

sudo systemctl status 'spica@*'
```

Expected: All 3 services running

### Step 9: Differentiate all services

```bash
for service in observer-health observer-gpu ranker-default; do
    recipe_name=$(echo $service | sed 's/@/-/')
    socket_path="/run/spica/spica-$service.sock"
    recipe_path="/etc/kloros/recipes/spica/$recipe_name.yaml"

    echo "Differentiating $service..."

    /home/kloros/.venv/bin/python3 << EOF
import json
import socket

def rpc_call(sock_path, method, params):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(sock_path)
    request = {"jsonrpc": "2.0", "method": method, "params": params, "id": "deploy"}
    client.sendall(json.dumps(request).encode() + b"\n")
    response = client.recv(4096)
    client.close()
    return json.loads(response.decode())

result = rpc_call("$socket_path", "differentiate", {"recipe_path": "$recipe_path"})
print(json.dumps(result, indent=2))
EOF
done
```

Expected: All services differentiate successfully, registry updated

### Step 10: Final verification

```bash
echo "=== Service Status ==="
sudo systemctl status 'spica@*' --no-pager

echo -e "\n=== Registry Contents ==="
cat /var/lib/kloros/spica_registry.json | jq .

echo -e "\n=== Socket Files ==="
ls -la /run/spica/

echo -e "\n=== Recent Logs ==="
journalctl -u 'spica@*' --since "5 minutes ago" --no-pager | tail -30
```

Expected: All services INTEGRATED, registry has 3 entries, sockets exist

### Step 11: Document deployment

```bash
tee /home/kloros/docs/SPICA_PHASE3_DEPLOYMENT.md > /dev/null << 'EOF'
# SPICA Phase 3 Deployment Complete

**Date:** $(date +%Y-%m-%d)
**Status:** Persistent services operational

## Deployed Services

| Service | Capability | Specialization | Status |
|---------|------------|----------------|--------|
| spica@observer-health | observer | health-monitoring | ✅ INTEGRATED |
| spica@observer-gpu | observer | gpu-monitoring | ✅ INTEGRATED |
| spica@ranker-default | ranker | multi-objective | ✅ INTEGRATED |

## Verification Commands

```bash
sudo systemctl status 'spica@*'

cat /var/lib/kloros/spica_registry.json | jq .

ls -la /run/spica/

journalctl -u 'spica@*' --since "1 hour ago"
```

## Next Steps

1. Create additional differentiation recipes for:
   - spica-guard@safety.service
   - spica-adapter@kloros.service
   - (3 more roles TBD)

2. Integrate with orchestrator (capability-driven task dispatch)

3. Monitor via Prometheus (extend Phase 2 metrics for persistent services)

4. Phase 4 planning: C2C Level 3, prompt_graph mutations
EOF

chmod 644 /home/kloros/docs/SPICA_PHASE3_DEPLOYMENT.md
```

### Step 12: Commit

```bash
cd /home/kloros
git add /etc/kloros/recipes/spica/*.yaml
git add docs/SPICA_PHASE3_DEPLOYMENT.md
git commit -m "deploy(spica): activate Phase 3 persistent services

- Create 3 differentiation recipes (observer-health, observer-gpu, ranker-default)
- Unmask and start spica@*.service units
- Differentiate all services to INTEGRATED state
- Verify capability registry (3 entries)
- Enable services for auto-start
- Document deployment status and verification steps

Phase 3 Status: COMPLETE ✅"
```

---

## Post-Implementation Verification

### Health Check Script

Create `/home/kloros/scripts/spica-health-check.sh`:

```bash
#!/bin/bash
set -e

echo "=== SPICA Phase 3 Health Check ==="
echo

echo "1. Service Status:"
sudo systemctl is-active spica@observer-health.service
sudo systemctl is-active spica@observer-gpu.service
sudo systemctl is-active spica@ranker-default.service

echo -e "\n2. Socket Files:"
ls -la /run/spica/ | grep -E "^srw"

echo -e "\n3. Registry Entries:"
jq '.capabilities | to_entries | length' /var/lib/kloros/spica_registry.json

echo -e "\n4. Service States:"
for service in observer-health observer-gpu ranker-default; do
    socket="/run/spica/spica-$service.sock"
    python3 << EOF
import json, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("$socket")
req = {"jsonrpc": "2.0", "method": "query_state", "params": {}, "id": "health"}
s.sendall(json.dumps(req).encode() + b"\n")
resp = json.loads(s.recv(4096).decode())
print(f"$service: {resp['result']['state']}")
s.close()
EOF
done

echo -e "\n✅ Phase 3 health check complete"
```

```bash
chmod +x /home/kloros/scripts/spica-health-check.sh
/home/kloros/scripts/spica-health-check.sh
```

Expected: All services active, sockets exist, all states INTEGRATED

---

## Rollback Plan

If deployment fails, rollback with:

```bash
sudo systemctl stop 'spica@*'

sudo systemctl mask spica@observer-health.service
sudo systemctl mask spica@observer-gpu.service
sudo systemctl mask spica@ranker-default.service

sudo systemctl daemon-reload

rm -f /run/spica/spica-*.sock

cp /var/lib/kloros/spica_registry.json /var/lib/kloros/spica_registry.json.backup
echo '{"capabilities": {}}' | sudo tee /var/lib/kloros/spica_registry.json
```

---

## Testing Strategy

**Unit Tests (per task):**
- State machine transitions
- DR validation
- RPC protocol
- Registry operations
- Service manager lifecycle

**Integration Tests (Task 7):**
- Full differentiation cycle
- RPC communication
- Registry integration
- Reprogram workflow

**System Tests (Task 8):**
- Service startup
- Socket communication
- Multi-service coordination
- Capability registry updates

**Acceptance Criteria:**
- All 3 services running (observer-health, observer-gpu, ranker-default)
- All services in INTEGRATED state
- Registry has 3 valid entries
- RPC calls succeed for all services
- No errors in journalctl logs
- Health check script passes

---

## Dependencies

**Python Packages:**
```bash
/home/kloros/.venv/bin/pip install pyyaml
```

**System Requirements:**
- systemd 245+
- Unix domain socket support
- /run/spica/ directory (mode 700, owner kloros)
- /var/lib/kloros/ directory (mode 755, owner kloros)
- /etc/kloros/recipes/spica/ directory (mode 755)

---

## Timeline

| Task | Estimated Time | Dependencies |
|------|----------------|--------------|
| 1. State Machine | 2-3 days | None |
| 2. DR Schema | 2-3 days | None |
| 3. RPC Server | 3-4 days | None |
| 4. Registry | 2-3 days | None |
| 5. Service Manager | 3-4 days | Tasks 1-4 |
| 6. Systemd Entry | 1-2 days | Task 5 |
| 7. Integration Tests | 2-3 days | Tasks 1-6 |
| 8. Deployment | 1-2 days | Tasks 1-7 |

**Total: 16-24 days (2-4 weeks)**

---

## Reference Documentation

- SPICA Architecture Spec v1.1.1: `/home/claude_temp/SPICA_ARCHITECTURE_SPEC_v1.1.1.md`
- SPICA Operational Guide v1.0: (provided separately)
- Phase 2 Complete: `/home/claude_temp/PHASE2_COMPLETE.txt`
- ResourceGovernor: `/home/kloros/src/governance/resource_governor.py`
- Tournament Mode (active): `/home/kloros/src/dream/config_tuning/spica_spawner.py`

---

## Notes

- Tournament mode (Phases 0-2) remains active and unchanged
- Persistent services run alongside tournament clones
- ResourceGovernor limits apply only to tournament spawns, not persistent services
- Phase 3 adds new capabilities without disrupting existing functionality
- Phase 4 (C2C Level 3, prompt_graph) deferred to future implementation
