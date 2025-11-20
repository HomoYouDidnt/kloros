#!/usr/bin/env python3
"""
Test if the CURRENT proxy on ports 5556/5557 works with zmq.proxy()
"""

import zmq
import time
import random
import sys

def main():
    print("=== Testing CURRENT Proxy (zmq.proxy() version) ===\n")

    ctx = zmq.Context.instance()

    # Create unique topic to avoid interference
    test_topic = f"TEST_PROXY_{random.randint(10000, 99999)}"

    # Subscriber
    print(f"[1] Creating subscriber for topic: {test_topic}")
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    sub.setsockopt(zmq.SUBSCRIBE, test_topic.encode())
    print("   ✓ Subscriber connected and subscribed")

    # Wait for subscription to propagate
    print("\n[2] Waiting 3 seconds for subscription to propagate...")
    time.sleep(3)

    # Publisher
    print("\n[3] Creating publisher")
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5556")
    print("   ✓ Publisher connected")

    # Wait for publisher to connect
    print("\n[4] Waiting 1 second for publisher connection...")
    time.sleep(1)

    # Send test messages
    print(f"\n[5] Sending 3 messages to topic '{test_topic}'")
    for i in range(3):
        msg = f"test_message_{i+1}"
        pub.send_multipart([test_topic.encode(), msg.encode()])
        print(f"   ✓ Sent: {msg}")
        time.sleep(0.1)

    # Try to receive
    print("\n[6] Attempting to receive messages (10 second timeout)...")
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
                print(f"   ✅ Received: topic='{topic.decode()}', payload='{payload.decode()}'")
            except zmq.Again:
                pass

        if received >= 3:
            break

    # Results
    print(f"\n{'='*60}")
    if received >= 3:
        print(f"✅ SUCCESS: Received all {received} messages!")
        print("The proxy is working correctly with zmq.proxy()")
        return 0
    elif received > 0:
        print(f"⚠️  PARTIAL: Received {received}/3 messages")
        print("Some messages are getting through but not all")
        return 1
    else:
        print(f"❌ FAILURE: Received 0 messages")
        print("The proxy is NOT delivering messages to subscribers")
        return 1

if __name__ == "__main__":
    sys.exit(main())
