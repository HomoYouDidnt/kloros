#!/usr/bin/env python3
# umn_proxy.py — XPUB/XSUB forwarder with verbose sub logging and TCP/IPC env toggles
import os
import sys
import time
from pathlib import Path
import zmq
import zmq.utils.monitor as mon

# Add src to path for maintenance mode import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.orchestration.core.maintenance_mode import wait_for_normal_mode

# TCP endpoints for production (loopback only, no external exposure)
XSUB_ENDPOINT = os.getenv("KLR_UMN_XSUB", "tcp://127.0.0.1:5556")  # publishers CONNECT here
XPUB_ENDPOINT = os.getenv("KLR_UMN_XPUB", "tcp://127.0.0.1:5557")  # subscribers CONNECT here

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

    xsub.bind(XSUB_ENDPOINT)
    xpub.bind(XPUB_ENDPOINT)

    # Optional: monitor sockets for events
    xpub_monitor = xpub.get_monitor_socket()  # logs SUBSCRIBE/UNSUB
    xsub_monitor = xsub.get_monitor_socket()  # logs connects

    poller = zmq.Poller()
    poller.register(xsub, zmq.POLLIN)
    poller.register(xpub, zmq.POLLIN)
    poller.register(xpub_monitor, zmq.POLLIN)
    poller.register(xsub_monitor, zmq.POLLIN)

    print(f"[umn-proxy] XSUB bind @ {XSUB_ENDPOINT}  |  XPUB bind @ {XPUB_ENDPOINT}", flush=True)

    while True:
        # Check maintenance mode before processing
        wait_for_normal_mode()

        for sock, _ in poller.poll(timeout=1000):  # 1 second timeout for maintenance checks
            if sock is xpub_monitor:
                evt = mon.recv_monitor_message(sock)
                ev = evt['event']
                if ev == zmq.EVENT_ACCEPTED or ev == zmq.EVENT_CONNECTED:
                    print(f"[umn-proxy] XPUB peer connected", flush=True)
                elif ev == zmq.EVENT_DISCONNECTED:
                    print(f"[umn-proxy] XPUB peer disconnected", flush=True)
            elif sock is xsub_monitor:
                evt = mon.recv_monitor_message(sock)
                ev = evt['event']
                if ev == zmq.EVENT_ACCEPTED or ev == zmq.EVENT_CONNECTED:
                    print(f"[umn-proxy] XSUB peer connected", flush=True)
                elif ev == zmq.EVENT_DISCONNECTED:
                    print(f"[umn-proxy] XSUB peer disconnected", flush=True)
            elif sock is xpub:
                # Subscription frames start with \x01 (subscribe) or \x00 (unsubscribe) then topic bytes
                data = xpub.recv()
                if data:
                    action = "SUB" if data[0] == 1 else "UNSUB"
                    topic = data[1:].decode('utf-8', errors='ignore')
                    print(f"[umn-proxy] {action} '{topic}'", flush=True)
                    # Forward to XSUB so publishers can (optionally) filter upstream
                    xsub.send(data)
            elif sock is xsub:
                # Forward published multipart messages to subscribers
                print(f"[umn-proxy] XSUB socket has data!", flush=True)
                msg = xsub.recv_multipart()
                # msg[0] must be topic frame; leave as-is
                print(f"[umn-proxy] MSG: topic={msg[0][:50] if msg else b''}, parts={len(msg)}", flush=True)
                xpub.send_multipart(msg)
                print(f"[umn-proxy] MSG forwarded to XPUB", flush=True)

if __name__ == "__main__":
    main()
