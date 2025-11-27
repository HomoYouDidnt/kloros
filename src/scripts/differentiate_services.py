#!/usr/bin/env python3
import socket
import json
import sys
from pathlib import Path

def rpc_call(socket_path: str, method: str, params: dict):
    """Send JSON-RPC 2.0 request over Unix domain socket"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(socket_path)

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }

        sock.sendall(json.dumps(request).encode() + b'\n')
        response = json.loads(sock.recv(4096).decode())
        sock.close()
        return response
    except Exception as e:
        return {"error": str(e)}

def main():
    print("Step 4: Triggering Differentiation (The Morphogenesis!)\n" + "="*60)

    services = [
        ("observer-health", "/etc/kloros/recipes/spica/observer-health.yaml"),
        ("observer-gpu", "/etc/kloros/recipes/spica/observer-gpu.yaml"),
        ("ranker-default", "/etc/kloros/recipes/spica/ranker-default.yaml")
    ]

    all_success = True

    for role, recipe_path in services:
        socket_path = f"/run/spica/spica-{role}.sock"

        print(f"Differentiating {role}...")
        result = rpc_call(socket_path, "differentiate", {"recipe_path": recipe_path})

        if "result" in result:
            r = result["result"]
            if r.get("success"):
                print(f"✓ {role}: {r['capability']} / {r['specialization']}")
                print(f"  State: {r['state']}")
            else:
                print(f"✗ {role}: {r.get('error', 'Unknown error')}")
                all_success = False
        elif "error" in result:
            print(f"✗ {role}: {result['error']}")
            all_success = False
        else:
            print(f"✗ {role}: Unexpected response: {result}")
            all_success = False

        print()

    if all_success:
        print("All services differentiated successfully!")
        return 0
    else:
        print("Some services failed to differentiate")
        return 1

if __name__ == "__main__":
    sys.exit(main())
