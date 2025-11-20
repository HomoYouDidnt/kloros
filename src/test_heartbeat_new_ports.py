#!/usr/bin/env python3
"""
Test HEARTBEAT messages on new ports to verify proxy is working with production services.
"""

import zmq
import time

def main():
    print("=== Testing HEARTBEAT on New Ports (5558/5559) ===\n")

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)

    print("Connecting to tcp://127.0.0.1:5559...")
    sub.connect("tcp://127.0.0.1:5559")
    print("✓ Connected")

    print("Subscribing to 'HEARTBEAT'...")
    sub.setsockopt(zmq.SUBSCRIBE, b"HEARTBEAT")
    print("✓ Subscribed")

    print("\nWaiting 3 seconds for subscription...")
    time.sleep(3)

    print("\nListening for HEARTBEAT messages (10 second timeout)...")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    received = 0
    start = time.time()

    while time.time() - start < 10:
        socks = dict(poller.poll(timeout=1000))
        if sub in socks:
            try:
                topic, payload = sub.recv_multipart(zmq.NOBLOCK)
                received += 1
                if received <= 3:
                    print(f"✓ [{received}] Received HEARTBEAT (payload_len={len(payload)})")
                elif received == 4:
                    print(f"... (suppressing further output)")
            except zmq.Again:
                pass

        if received >= 10:
            break

    print(f"\n{'='*60}")
    if received > 0:
        print(f"✅ SUCCESS: Received {received} HEARTBEAT messages!")
        print("The proxy is working with production services on new ports.")
        return 0
    else:
        print(f"❌ FAILURE: Received 0 HEARTBEAT messages")
        print("Production services may not be publishing HEARTBEAT on new ports.")
        return 1

if __name__ == "__main__":
    exit(main())
