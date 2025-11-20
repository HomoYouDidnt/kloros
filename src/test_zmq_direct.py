#!/usr/bin/env python3
"""
Direct ZMQ test bypassing all ChemBus wrappers.
"""

import zmq
import time
import json

def main():
    ctx = zmq.Context.instance()

    # Publisher - connect to XSUB
    pub = ctx.socket(zmq.PUB)
    pub.connect("tcp://127.0.0.1:5556")
    print("Publisher connected to XSUB tcp://127.0.0.1:5556")
    time.sleep(0.5)  # Give ZMQ time to connect

    # Subscriber - connect to XPUB
    sub = ctx.socket(zmq.SUB)
    sub.connect("tcp://127.0.0.1:5557")
    sub.setsockopt(zmq.SUBSCRIBE, b"test.topic")
    print("Subscriber connected to XPUB tcp://127.0.0.1:5557, subscribed to 'test.topic'")
    time.sleep(0.5)  # Give subscription time to propagate

    # Send test message
    topic = "test.topic"
    payload = json.dumps({"test": "data"}).encode("utf-8")
    pub.send_multipart([topic.encode("utf-8"), payload])
    print(f"Sent message with topic '{topic}'")

    # Wait for message with timeout
    print("Waiting for message...")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    socks = dict(poller.poll(timeout=3000))  # 3 second timeout

    if sub in socks:
        rec_topic, rec_payload = sub.recv_multipart()
        print(f"✓ Received: topic='{rec_topic.decode()}', payload={rec_payload.decode()}")
        return 0
    else:
        print("✗ No message received within timeout")
        return 1


if __name__ == "__main__":
    exit(main())
