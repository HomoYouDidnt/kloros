#!/usr/bin/env python3
"""
Subscribe to HEARTBEAT messages to verify basic subscriber functionality.
HEARTBEAT messages are being sent constantly, so if subscriptions work at all,
this should receive messages.
"""

import zmq
import time

def main():
    print("=== HEARTBEAT Subscriber Test ===")
    print("HEARTBEAT messages are sent ~100 times per second")
    print("If subscription works, we should receive messages immediately")
    print()

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)

    print("Connecting to tcp://127.0.0.1:5557...")
    sub.connect("tcp://127.0.0.1:5557")
    print("✓ Connected")

    print("Subscribing to 'HEARTBEAT'...")
    sub.setsockopt(zmq.SUBSCRIBE, b"HEARTBEAT")
    print("✓ Subscribed")

    print("\nWaiting 3 seconds for subscription to propagate...")
    time.sleep(3)

    print("\nListening for messages (15 second timeout)...")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    received = 0
    start = time.time()

    while time.time() - start < 15:
        socks = dict(poller.poll(timeout=1000))
        if sub in socks:
            try:
                topic, payload = sub.recv_multipart(zmq.NOBLOCK)
                received += 1
                if received <= 5:  # Only print first 5
                    print(f"✓ [{received}] Received: topic='{topic.decode()}', payload_len={len(payload)}")
                elif received == 6:
                    print(f"... (suppressing further output)")
            except zmq.Again:
                pass

        if received >= 10:
            break

    print(f"\n{'✅ SUCCESS' if received > 0 else '❌ FAILURE'}: Received {received} messages in {time.time()-start:.1f} seconds")

    if received == 0:
        print("\nThis indicates subscribers are NOT receiving messages from the proxy!")
        print("The proxy is forwarding messages, but they're not reaching subscribers.")
        return 1
    else:
        print("\nSubscribers CAN receive messages!")
        print("The issue is likely with how test messages are being published.")
        return 0


if __name__ == "__main__":
    exit(main())
