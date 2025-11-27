#!/usr/bin/env python3
"""
Test with a persistent publisher that stays alive.
"""

import zmq
import time
import json

def main():
    print("=== Persistent Publisher Test ===")

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)

    print("Connecting to tcp://127.0.0.1:5556...")
    pub.connect("tcp://127.0.0.1:5556")
    print("✓ Connected")

    print("Waiting 3 seconds for connection to stabilize...")
    time.sleep(3)

    # Send multiple messages with delays
    topic = b"persistent.test"
    for i in range(5):
        payload = json.dumps({"test": f"message_{i}"}).encode()
        pub.send_multipart([topic, payload])
        print(f"✓ Sent message #{i+1}")
        time.sleep(1)  # Wait between messages

    print("\nKeeping publisher alive for 10 more seconds...")
    print("Check proxy logs:")
    print("  sudo journalctl -u kloros-chem-proxy.service -f --no-pager | grep persistent")
    time.sleep(10)

    pub.close()
    print("✓ Publisher closed")


if __name__ == "__main__":
    main()
