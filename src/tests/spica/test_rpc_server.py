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

def test_rpc_missing_jsonrpc_field(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def test_method(params):
        return {"ok": True}

    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "method": "test_method",
        "params": {},
        "id": "test-missing-jsonrpc"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32600
    assert "jsonrpc" in data["error"]["message"].lower()

    client.close()
    server.stop()

def test_rpc_invalid_json(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))
    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    client.sendall(b"{invalid json}\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32700
    assert "parse" in data["error"]["message"].lower()

    client.close()
    server.stop()

def test_rpc_invalid_method_type(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))
    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": 123,
        "params": {},
        "id": "test-invalid-method-type"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32600
    assert "method" in data["error"]["message"].lower()

    client.close()
    server.stop()

def test_rpc_invalid_params_type(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def test_method(params):
        return {"ok": True}

    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "test_method",
        "params": "invalid",
        "id": "test-invalid-params"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32602

    client.close()
    server.stop()

def test_rpc_concurrent_requests(tmp_path):
    import time
    import threading

    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def slow_method(params):
        time.sleep(0.1)
        return {"result": params.get("value", 0) * 2}

    server.start()

    results = []
    errors = []

    def make_request(value):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(socket_path))

            request = {
                "jsonrpc": "2.0",
                "method": "slow_method",
                "params": {"value": value},
                "id": f"concurrent-{value}"
            }
            client.sendall(json.dumps(request).encode() + b"\n")

            response = client.recv(4096)
            data = json.loads(response.decode())
            results.append(data)

            client.close()
        except Exception as e:
            errors.append(str(e))

    threads = []
    for i in range(10):
        t = threading.Thread(target=make_request, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 10

    for result in results:
        assert "result" in result
        value = int(result["id"].split("-")[1])
        assert result["result"]["result"] == value * 2

    server.stop()

def test_rpc_internal_error_handling(tmp_path):
    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def failing_method(params):
        raise ValueError("Intentional test error")

    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "failing_method",
        "params": {},
        "id": "test-error"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32603
    assert "Intentional test error" in data["error"]["message"]

    client.close()
    server.stop()

def test_rpc_custom_error_handling(tmp_path):
    from src.spica.rpc_server import RPCError

    socket_path = tmp_path / "test.sock"
    server = RPCServer(str(socket_path))

    @rpc_method(server)
    def custom_error_method(params):
        raise RPCError(-32000, "Custom application error")

    server.start()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(socket_path))

    request = {
        "jsonrpc": "2.0",
        "method": "custom_error_method",
        "params": {},
        "id": "test-custom-error"
    }
    client.sendall(json.dumps(request).encode() + b"\n")

    response = client.recv(4096)
    data = json.loads(response.decode())

    assert "error" in data
    assert data["error"]["code"] == -32000
    assert data["error"]["message"] == "Custom application error"

    client.close()
    server.stop()
