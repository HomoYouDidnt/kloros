#!/usr/bin/env python3
"""
Test raw ZMQ publishing to verify basic connectivity.
"""

import zmq
import time
import json

def main():
    print("=== Raw ZMQ Publisher Test ===")

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)

    print("Connecting to tcp://127.0.0.1:5556...")
    pub.connect("tcp://127.0.0.1:5556")
    print("✓ Connected")

    time.sleep(1)
    print("✓ Waited 1 second for connection")

    # Send a simple message
    topic = b"test.raw.zmq"
    payload = json.dumps({"test": "raw_zmq"}).encode()

    print(f"Sending message with topic '{topic.decode()}'...")
    pub.send_multipart([topic, payload])
    print("✓ Sent first message")

    time.sleep(0.1)
    pub.send_multipart([topic, payload])
    print("✓ Sent second message (slow-joiner protection)")

    print()
    print("Check proxy logs:")
    print("  sudo journalctl -u kloros-chem-proxy.service -n 20 --no-pager | grep 'test.raw'")

    pub.close()
    print("✓ Publisher closed")


if __name__ == "__main__":
    main()
