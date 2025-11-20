#!/usr/bin/env python3
"""
Minimal ZMQ proxy test to isolate the issue.
"""

import zmq
import threading
import time

def run_mini_proxy():
    """Minimal XPUB/XSUB proxy"""
    ctx = zmq.Context.instance()

    xsub = ctx.socket(zmq.XSUB)
    xpub = ctx.socket(zmq.XPUB)

    xsub.bind("tcp://127.0.0.1:15556")
    xpub.bind("tcp://127.0.0.1:15557")

    print("[mini-proxy] Started on ports 15556/15557")

    try:
        zmq.proxy(xsub, xpub)
    except KeyboardInterrupt:
        pass


def test_with_mini_proxy():
    """Test pub/sub through mini proxy"""
    time.sleep(0.5)  # Let proxy start

    ctx = zmq.Context.instance()

    # Subscriber
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:15557")
    sub.setsockopt(zmq.SUBSCRIBE, b"test")
    print("[test] Subscriber connected")
    time.sleep(1)

    # Publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:15556")
    print("[test] Publisher connected")
    time.sleep(1)

    # Send message
    pub.send_multipart([b"test.topic", b"test payload"])
    pub.send_multipart([b"test.topic", b"test payload"])  # Double-tap
    print("[test] Messages sent")

    # Try to receive
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    socks = dict(poller.poll(timeout=3000))
    if sub in socks:
        topic, payload = sub.recv_multipart()
        print(f"[test] ✅ SUCCESS: Received topic='{topic.decode()}', payload='{payload.decode()}'")
        return True
    else:
        print("[test] ❌ FAILURE: No message received")
        return False


def main():
    print("=== Minimal Proxy Test ===\n")

    # Start proxy in background thread
    proxy_thread = threading.Thread(target=run_mini_proxy, daemon=True)
    proxy_thread.start()

    # Run test
    result = test_with_mini_proxy()

    print(f"\nResult: {'PASS' if result else 'FAIL'}")
    print("\nIf this test PASSES, the issue is with the production proxy configuration.")
    print("If this test FAILS, the issue is with ZMQ itself or system configuration.")

    return 0 if result else 1


if __name__ == "__main__":
    exit(main())
