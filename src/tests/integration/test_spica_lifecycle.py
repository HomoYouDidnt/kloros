import pytest
import json
import socket
import time
import threading
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

def test_registry_integration(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    result = rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})
    assert result["result"]["success"] is True

    registry_entry = manager.registry.query("observer", "test-integration")
    assert registry_entry is not None
    assert registry_entry["provider"] == "integration-test"
    assert registry_entry["state"] == "INTEGRATED"
    assert registry_entry["socket"] == str(socket_path)
    assert registry_entry["version"] == "1.0"
    assert "last_heartbeat" in registry_entry

    all_capabilities = manager.registry.list_all()
    assert "observer" in all_capabilities
    assert "test-integration" in all_capabilities["observer"]

def test_reprogram_lifecycle(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})
    assert manager.lifecycle.current_state.value == "integrated"

    registry_entry = manager.registry.query("observer", "test-integration")
    assert registry_entry is not None

    result = rpc_call(socket_path, "reprogram", {})
    assert result["result"]["success"] is True
    assert result["result"]["state"] == "pluripotent"

    registry_entry_after = manager.registry.query("observer", "test-integration")
    assert registry_entry_after is None

    status = rpc_call(socket_path, "query_state", {})
    assert status["result"]["state"] == "pluripotent"
    assert status["result"]["recipe"] is None

def test_multiple_heartbeats(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})

    first = manager.registry.query("observer", "test-integration")
    first_heartbeat = first["last_heartbeat"]

    time.sleep(0.1)

    manager.registry.heartbeat("integration-test")
    second = manager.registry.query("observer", "test-integration")
    second_heartbeat = second["last_heartbeat"]

    assert second_heartbeat > first_heartbeat

    time.sleep(0.1)

    manager.registry.heartbeat("integration-test")
    third = manager.registry.query("observer", "test-integration")
    third_heartbeat = third["last_heartbeat"]

    assert third_heartbeat > second_heartbeat

def test_rpc_protocol_compliance(integration_setup):
    socket_path = integration_setup["socket_path"]

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "query_state",
        "params": {},
        "id": "protocol-test-1"
    }

    client.sendall(json.dumps(request).encode() + b"\n")
    response = client.recv(4096)
    data = json.loads(response.decode())

    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert data["id"] == "protocol-test-1"

    client.close()

def test_rpc_protocol_missing_jsonrpc_field(integration_setup):
    socket_path = integration_setup["socket_path"]

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "method": "query_state",
        "params": {},
        "id": "protocol-test-2"
    }

    client.sendall(json.dumps(request).encode() + b"\n")
    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32600
    assert "jsonrpc" in data["error"]["message"].lower()

    client.close()

def test_concurrent_rpc_requests(integration_setup):
    socket_path = integration_setup["socket_path"]

    results = []
    errors = []

    def make_status_request(request_id):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(socket_path))

            request = {
                "jsonrpc": "2.0",
                "method": "query_state",
                "params": {},
                "id": f"concurrent-{request_id}"
            }

            client.sendall(json.dumps(request).encode() + b"\n")
            response = client.recv(4096)
            data = json.loads(response.decode())
            results.append(data)

            client.close()
        except Exception as e:
            errors.append(str(e))

    threads = []
    for i in range(20):
        t = threading.Thread(target=make_status_request, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 20

    for result in results:
        assert "result" in result
        assert result["result"]["state"] in ["pluripotent", "integrated"]

def test_invalid_json_handling(integration_setup):
    socket_path = integration_setup["socket_path"]

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    client.sendall(b"{this is not valid json}\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32700
    assert "parse" in data["error"]["message"].lower()

    client.close()

def test_state_transitions_complete_cycle(integration_setup):
    socket_path = integration_setup["socket_path"]
    recipe_path = integration_setup["recipe_path"]
    manager = integration_setup["manager"]

    from src.spica.lifecycle import LifecycleState

    assert manager.lifecycle.current_state == LifecycleState.PLURIPOTENT

    result = rpc_call(socket_path, "differentiate", {"recipe_path": str(recipe_path)})
    assert result["result"]["success"] is True
    assert manager.lifecycle.current_state == LifecycleState.INTEGRATED

    history = manager.lifecycle.history
    assert len(history) >= 5

    states_in_order = [h.to_state for h in history[1:]]
    assert LifecycleState.PRIMED in states_in_order
    assert LifecycleState.DIFFERENTIATING in states_in_order
    assert LifecycleState.SPECIALIZED in states_in_order
    assert LifecycleState.INTEGRATED in states_in_order

    result = rpc_call(socket_path, "reprogram", {})
    assert result["result"]["success"] is True
    assert manager.lifecycle.current_state == LifecycleState.PLURIPOTENT

    final_event = manager.lifecycle.history[-1]
    assert final_event.event == "reprogram"
