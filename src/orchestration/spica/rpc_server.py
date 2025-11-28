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
        self.methods_lock = threading.Lock()
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.worker_threads = []

    def register_method(self, name: str, handler: Callable):
        with self.methods_lock:
            self.methods[name] = handler
        logger.info(f"Registered RPC method: {name}")

    def start(self):
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(str(self.socket_path))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)
        self.socket_path.chmod(0o600)

        self.running = True
        self.thread = threading.Thread(target=self._accept_loop, daemon=False)
        self.thread.start()

        logger.info(f"RPC server started on {self.socket_path}")

    def stop(self):
        self.running = False

        if self.server_socket:
            self.server_socket.close()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        for worker in self.worker_threads:
            if worker.is_alive():
                worker.join(timeout=1.0)

        if self.socket_path.exists():
            self.socket_path.unlink()

        logger.info("RPC server stopped")

    def _accept_loop(self):
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                worker = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=False
                )
                self.worker_threads.append(worker)
                worker.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_client(self, client_socket: socket.socket):
        try:
            data = client_socket.recv(4096)
            if not data:
                return

            try:
                request = json.loads(data.decode())
            except json.JSONDecodeError as e:
                response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32700,
                        "message": f"Parse error: {str(e)}"
                    },
                    "id": None
                }
                client_socket.sendall(json.dumps(response).encode() + b"\n")
                return

            response = self._process_request(request)
            client_socket.sendall(json.dumps(response).encode() + b"\n")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def _process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request.get("id")

        if request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: jsonrpc field must be '2.0'"
                },
                "id": request_id
            }

        method_name = request.get("method")
        if not isinstance(method_name, str):
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: method must be a string"
                },
                "id": request_id
            }

        params = request.get("params", {})
        if params is not None and not isinstance(params, (dict, list)):
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Invalid params: params must be an object or array"
                },
                "id": request_id
            }

        with self.methods_lock:
            if method_name not in self.methods:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method_name}"
                    },
                    "id": request_id
                }
            handler = self.methods[method_name]

        try:
            result = handler(params)
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
        except RPCError as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": e.code,
                    "message": e.message
                },
                "id": request_id
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                },
                "id": request_id
            }

def rpc_method(server: RPCServer):
    def decorator(func: Callable):
        server.register_method(func.__name__, func)
        return func
    return decorator
