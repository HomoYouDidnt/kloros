#!/usr/bin/env python3
"""
Test proxy on NEW ports 5558/5559
"""

import zmq
import time
import random
import sys

def main():
    print("=== Testing Proxy on NEW Ports (5558/5559) ===\n")

    ctx = zmq.Context.instance()

    # Create unique topic
    test_topic = f"TEST_{random.randint(10000, 99999)}"

    # Subscriber
    print(f"[1] Creating subscriber for topic: {test_topic}")
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5559")  # NEW XPUB PORT
    sub.setsockopt(zmq.SUBSCRIBE, test_topic.encode())
    print("   ✓ Subscriber connected")

    # Wait for subscription
    print("\n[2] Waiting 3 seconds for subscription...")
    time.sleep(3)

    # Publisher
    print("\n[3] Creating publisher")
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5558")  # NEW XSUB PORT
    print("   ✓ Publisher connected")
    time.sleep(1)

    # Send messages
    print(f"\n[4] Sending 3 messages to '{test_topic}'")
    for i in range(3):
        msg = f"message_{i+1}"
        pub.send_multipart([test_topic.encode(), msg.encode()])
        print(f"   ✓ Sent: {msg}")
        time.sleep(0.1)

    # Receive
    print("\n[5] Receiving messages...")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    received = 0
    start = time.time()

    while time.time() - start < 10:
        socks = dict(poller.poll(timeout=1000))
        if sub in socks:
            topic, payload = sub.recv_multipart(zmq.NOBLOCK)
            received += 1
            print(f"   ✅ Received: {payload.decode()}")

        if received >= 3:
            break

    # Results
    print(f"\n{'='*60}")
    if received >= 3:
        print(f"✅ SUCCESS: Received all {received} messages on ports 5558/5559!")
        return 0
    elif received > 0:
        print(f"⚠️  PARTIAL: Received {received}/3 messages")
        return 1
    else:
        print(f"❌ FAILURE: Received 0 messages on NEW ports")
        return 1

if __name__ == "__main__":
    sys.exit(main())
