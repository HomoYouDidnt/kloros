#!/usr/bin/env python3
"""
Test with exact same configuration as production proxy to isolate the issue.
"""

import zmq
import threading
import time

def run_configured_proxy():
    """Proxy with exact production config"""
    ctx = zmq.Context.instance()

    xsub = ctx.socket(zmq.XSUB)
    xpub = ctx.socket(zmq.XPUB)

    # EXACT SAME CONFIG AS PRODUCTION
    for s in (xsub, xpub):
        s.setsockopt(zmq.SNDHWM, 1000)
        s.setsockopt(zmq.RCVHWM, 1000)

    xpub.setsockopt(zmq.XPUB_VERBOSE, 1)

    xsub.bind("tcp://127.0.0.1:15556")
    xpub.bind("tcp://127.0.0.1:15557")

    # Enable monitoring like production
    xpub_monitor = xpub.get_monitor_socket()
    xsub_monitor = xsub.get_monitor_socket()

    print("[test-proxy] Started with production config")

    try:
        zmq.proxy(xsub, xpub)
    except KeyboardInterrupt:
        pass


def test_with_config():
    """Test pub/sub through configured proxy"""
    time.sleep(0.5)

    ctx = zmq.Context.instance()

    # Subscriber
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:15557")
    sub.setsockopt(zmq.SUBSCRIBE, b"test")
    print("[test] Subscriber connected and subscribed")
    time.sleep(2)  # Wait for subscription

    # Publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:15556")
    print("[test] Publisher connected")
    time.sleep(1)

    # Send messages
    for i in range(3):
        pub.send_multipart([b"test.topic", b"payload"])
        print(f"[test] Sent message #{i+1}")
        time.sleep(0.2)

    # Try to receive
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    received = 0
    start = time.time()
    while time.time() - start < 3:
        socks = dict(poller.poll(timeout=500))
        if sub in socks:
            topic, payload = sub.recv_multipart()
            received += 1
            print(f"[test] ✅ Received message #{received}")

    if received > 0:
        print(f"\n✅ SUCCESS: Received {received} messages")
        return True
    else:
        print("\n❌ FAILURE: No messages received")
        return False


def main():
    print("=== Testing Production Proxy Configuration ===\n")

    # Start proxy
    proxy_thread = threading.Thread(target=run_configured_proxy, daemon=True)
    proxy_thread.start()

    # Run test
    result = test_with_config()

    return 0 if result else 1


if __name__ == "__main__":
    exit(main())
