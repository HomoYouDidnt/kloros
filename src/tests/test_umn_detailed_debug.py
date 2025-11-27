#!/usr/bin/env python3
"""
Detailed UMN debugging with step-by-step verification.
"""

import zmq
import time
import json
import threading

def test_basic_zmq():
    """Test 1: Basic ZMQ XPUB/XSUB without UMN wrapper"""
    print("\n=== TEST 1: Basic ZMQ XPUB/XSUB ===")

    ctx = zmq.Context.instance()

    # Subscriber first
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    topic = b"debug.test"
    sub.setsockopt(zmq.SUBSCRIBE, topic)
    print(f"✓ Subscriber connected and subscribed to '{topic.decode()}'")

    # Wait for subscription to propagate
    time.sleep(2)
    print("✓ Waited 2 seconds for subscription propagation")

    # Publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5556")
    print("✓ Publisher connected")

    # Wait for connection
    time.sleep(1)
    print("✓ Waited 1 second for publisher connection")

    # Send message
    payload = json.dumps({"test": "data"}).encode()
    pub.send_multipart([topic, payload])
    print(f"✓ Sent message with topic '{topic.decode()}'")

    # Send second time (slow-joiner protection)
    time.sleep(0.1)
    pub.send_multipart([topic, payload])
    print("✓ Sent duplicate message (slow-joiner protection)")

    # Try to receive with timeout
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    print("⏳ Waiting for message (5 second timeout)...")
    socks = dict(poller.poll(timeout=5000))

    if sub in socks:
        rec_topic, rec_payload = sub.recv_multipart()
        print(f"✅ SUCCESS: Received topic='{rec_topic.decode()}', payload={rec_payload.decode()}")
        return True
    else:
        print("❌ FAILURE: No message received")
        return False


def test_subscription_visibility():
    """Test 2: Check if proxy sees subscription"""
    print("\n=== TEST 2: Subscription Visibility ===")
    print("Creating subscriber and checking proxy logs...")

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    sub.setsockopt(zmq.SUBSCRIBE, b"visibility.test")
    print("✓ Subscribed to 'visibility.test'")

    time.sleep(2)
    print("⏳ Check proxy logs for: SUB 'visibility.test'")
    print("   Run: sudo journalctl -u kloros-umn-proxy.service -n 20 --no-pager | grep visibility")

    input("\nPress Enter after checking proxy logs...")
    sub.close()
    return None


def test_heartbeat_subscription():
    """Test 3: Subscribe to known-working HEARTBEAT topic"""
    print("\n=== TEST 3: Subscribe to HEARTBEAT (known working) ===")

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    sub.setsockopt(zmq.SUBSCRIBE, b"HEARTBEAT")
    print("✓ Subscribed to 'HEARTBEAT'")

    time.sleep(1)

    print("⏳ Waiting for HEARTBEAT messages (10 second timeout)...")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    received = 0
    start = time.time()
    while time.time() - start < 10 and received < 3:
        socks = dict(poller.poll(timeout=1000))
        if sub in socks:
            topic, payload = sub.recv_multipart()
            received += 1
            print(f"✓ Received HEARTBEAT #{received}")

    if received > 0:
        print(f"✅ SUCCESS: Received {received} HEARTBEAT messages")
        return True
    else:
        print("❌ FAILURE: No HEARTBEAT messages received")
        return False


def test_subscription_thread():
    """Test 4: Verify subscription thread is running"""
    print("\n=== TEST 4: Subscription Thread Test ===")

    received_messages = []
    thread_active = threading.Event()

    def receiver_thread():
        ctx = zmq.Context.instance()
        sub = ctx.socket(zmq.SUB)
        sub.connect("tcp://127.0.0.1:5557")
        sub.setsockopt(zmq.SUBSCRIBE, b"thread.test")
        print("✓ [Thread] Subscribed to 'thread.test'")

        thread_active.set()

        poller = zmq.Poller()
        poller.register(sub, zmq.POLLIN)

        timeout_count = 0
        while timeout_count < 10:  # Run for 10 seconds
            socks = dict(poller.poll(timeout=1000))
            if sub in socks:
                topic, payload = sub.recv_multipart()
                msg = {"topic": topic.decode(), "payload": payload.decode()}
                received_messages.append(msg)
                print(f"✓ [Thread] Received: {msg}")
            else:
                timeout_count += 1

        sub.close()
        print("✓ [Thread] Exiting")

    # Start receiver thread
    thread = threading.Thread(target=receiver_thread, daemon=True)
    thread.start()

    # Wait for thread to initialize
    if not thread_active.wait(timeout=3):
        print("❌ Thread failed to initialize")
        return False

    time.sleep(2)  # Wait for subscription to propagate

    # Send messages
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5556")
    time.sleep(1)

    topic = b"thread.test"
    payload = json.dumps({"test": "message"}).encode()

    for i in range(3):
        pub.send_multipart([topic, payload])
        print(f"✓ Sent message #{i+1}")
        time.sleep(0.5)

    # Wait for messages
    time.sleep(2)

    if received_messages:
        print(f"✅ SUCCESS: Received {len(received_messages)} messages in thread")
        return True
    else:
        print("❌ FAILURE: No messages received in thread")
        return False


def test_proxy_forwarding():
    """Test 5: Monitor proxy directly during message send"""
    print("\n=== TEST 5: Proxy Forwarding Monitor ===")
    print("This test will send a message and you should check proxy logs.")

    ctx = zmq.Context.instance()

    # Create subscriber first
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    sub.setsockopt(zmq.SUBSCRIBE, b"forward.test")
    print("✓ Subscriber ready for 'forward.test'")

    time.sleep(3)
    print("✓ Waited 3 seconds for subscription")

    # Create publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5556")
    time.sleep(2)
    print("✓ Publisher ready")

    # Send message
    payload = json.dumps({"test": "forward"}).encode()
    pub.send_multipart([b"forward.test", payload])
    pub.send_multipart([b"forward.test", payload])  # Double-tap
    print("✓ Sent messages")

    print("\n⏳ Check proxy logs NOW:")
    print("   sudo journalctl -u kloros-umn-proxy.service -n 50 --no-pager | grep -E '(forward|XSUB socket)'")

    # Try to receive
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    socks = dict(poller.poll(timeout=3000))

    if sub in socks:
        print("✅ Message received!")
        return True
    else:
        print("❌ Message NOT received")
        return False


def main():
    print("="*60)
    print("UMN Detailed Debugging Suite")
    print("="*60)

    results = {}

    # Run tests
    results['basic_zmq'] = test_basic_zmq()

    test_subscription_visibility()

    results['heartbeat'] = test_heartbeat_subscription()

    results['thread'] = test_subscription_thread()

    results['forwarding'] = test_proxy_forwarding()

    # Summary
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    for test, result in results.items():
        if result is None:
            continue
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test:20s} {status}")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()
