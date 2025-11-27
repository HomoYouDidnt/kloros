#!/usr/bin/env python3
# chem_proxy_fixed.py — Fixed XPUB/XSUB forwarder
import os
import sys
import time
from pathlib import Path
import zmq

# Add src to path for maintenance mode import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

# TCP endpoints for production (loopback only, no external exposure)
XSUB_ENDPOINT = os.getenv("KLR_CHEM_XSUB", "tcp://127.0.0.1:5558")  # publishers CONNECT here
XPUB_ENDPOINT = os.getenv("KLR_CHEM_XPUB", "tcp://127.0.0.1:5559")  # subscribers CONNECT here

def main():
    ctx = zmq.Context.instance()

    xsub = ctx.socket(zmq.XSUB)
    xpub = ctx.socket(zmq.XPUB)

    # High water marks so we don't silently drop
    for s in (xsub, xpub):
        s.setsockopt(zmq.SNDHWM, 1000)
        s.setsockopt(zmq.RCVHWM, 1000)

    # See subscription messages (+/- topic)
    xpub.setsockopt(zmq.XPUB_VERBOSE, 1)

    # CRITICAL FIX: Set XPUB_MANUAL mode to control subscription distribution
    # Without this, subscriptions are automatically removed from XPUB when read
    # xpub.setsockopt(zmq.XPUB_MANUAL, 1)  # Commented - let's try without first

    xsub.bind(XSUB_ENDPOINT)
    xpub.bind(XPUB_ENDPOINT)

    print(f"[chem-proxy-fixed] XSUB bind @ {XSUB_ENDPOINT}  |  XPUB bind @ {XPUB_ENDPOINT}", flush=True)
    print(f"[chem-proxy-fixed] Using built-in zmq.proxy() for reliable message delivery", flush=True)

    try:
        # Use the built-in proxy which handles all edge cases correctly
        # This is the same as the minimal proxy that works
        zmq.proxy(xsub, xpub)
    except KeyboardInterrupt:
        print("[chem-proxy-fixed] Shutting down", flush=True)

if __name__ == "__main__":
    main()
