#!/usr/bin/env python3
"""
UMN Channel-Aware Proxy

Provides differentiated signal pathways inspired by neurotransmitter systems:
- REFLEX: ROUTER/DEALER for acknowledged delivery (glutamatergic)
- AFFECT: PUB/SUB for fire-and-forget state changes (dopaminergic)
- TROPHIC: PUSH/PULL for batched work distribution (hormonal)
- LEGACY: Standard PUB/SUB for backward compatibility

This proxy runs alongside the legacy proxy during migration.
"""

from __future__ import annotations
import json
import logging
import os
import signal
import sys
import time
from threading import Thread, Event
from typing import Optional

logger = logging.getLogger(__name__)

_ZMQ_AVAILABLE = False
try:
    import zmq
    _ZMQ_AVAILABLE = True
except ImportError:
    logger.error("ZMQ not available - channel proxy requires pyzmq")
    sys.exit(1)

LEGACY_XSUB = os.getenv("KLR_UMN_XSUB", "tcp://127.0.0.1:5558")
LEGACY_XPUB = os.getenv("KLR_UMN_XPUB", "tcp://127.0.0.1:5559")

REFLEX_ROUTER = os.getenv("KLR_UMN_REFLEX_ENDPOINT", "tcp://127.0.0.1:5560")
AFFECT_XSUB = os.getenv("KLR_UMN_AFFECT_XSUB", "tcp://127.0.0.1:5561")
AFFECT_XPUB = os.getenv("KLR_UMN_AFFECT_XPUB", "tcp://127.0.0.1:5562")
TROPHIC_PULL = os.getenv("KLR_UMN_TROPHIC_PULL", "tcp://127.0.0.1:5563")
TROPHIC_PUSH = os.getenv("KLR_UMN_TROPHIC_PUSH", "tcp://127.0.0.1:5564")

REFLEX_TIMEOUT_MS = int(os.getenv("KLR_UMN_REFLEX_TIMEOUT_MS", "5000"))
AFFECT_HWM = int(os.getenv("KLR_UMN_AFFECT_HWM", "100"))
TROPHIC_HWM = int(os.getenv("KLR_UMN_TROPHIC_HWM", "10000"))
LEGACY_HWM = int(os.getenv("KLR_UMN_LEGACY_HWM", "1000"))


class ChannelMetrics:
    """Per-channel metrics for observability."""

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.messages_forwarded = 0
        self.messages_dropped = 0
        self.messages_failed = 0
        self.ack_count = 0
        self.nack_count = 0
        self.timeout_count = 0
        self.start_time = time.time()

    def to_dict(self) -> dict:
        return {
            "channel": self.channel_name,
            "messages_forwarded": self.messages_forwarded,
            "messages_dropped": self.messages_dropped,
            "messages_failed": self.messages_failed,
            "ack_count": self.ack_count,
            "nack_count": self.nack_count,
            "timeout_count": self.timeout_count,
            "uptime_s": time.time() - self.start_time,
        }


class ChannelProxy:
    """
    Multi-channel UMN proxy with differentiated delivery semantics.

    Maintains backward compatibility with legacy proxy while adding
    specialized channels for different signal characteristics.
    """

    def __init__(self, include_legacy: bool = False):
        self.ctx = zmq.Context.instance()
        self._shutdown = Event()
        self._include_legacy = include_legacy

        self.metrics = {
            "reflex": ChannelMetrics("reflex"),
            "affect": ChannelMetrics("affect"),
            "trophic": ChannelMetrics("trophic"),
        }

        if self._include_legacy:
            self.metrics["legacy"] = ChannelMetrics("legacy")
            self._init_legacy()

        self._init_reflex()
        self._init_affect()
        self._init_trophic()

        logger.info(f"ChannelProxy initialized (legacy={include_legacy})")

    def _init_legacy(self):
        """Initialize legacy PUB/SUB for backward compatibility."""
        self.legacy_xsub = self.ctx.socket(zmq.XSUB)
        self.legacy_xpub = self.ctx.socket(zmq.XPUB)

        self.legacy_xsub.setsockopt(zmq.RCVHWM, LEGACY_HWM)
        self.legacy_xpub.setsockopt(zmq.SNDHWM, LEGACY_HWM)

        self.legacy_xsub.bind(LEGACY_XSUB)
        self.legacy_xpub.bind(LEGACY_XPUB)

        logger.info(f"Legacy channel: XSUB={LEGACY_XSUB} XPUB={LEGACY_XPUB} HWM={LEGACY_HWM}")

    def _init_reflex(self):
        """Initialize REFLEX ROUTER for acknowledged delivery."""
        self.reflex_router = self.ctx.socket(zmq.ROUTER)
        self.reflex_router.setsockopt(zmq.ROUTER_MANDATORY, 1)
        self.reflex_router.setsockopt(zmq.RCVHWM, 100)
        self.reflex_router.bind(REFLEX_ROUTER)

        self._reflex_consumers: dict[bytes, float] = {}

        logger.info(f"Reflex channel: ROUTER={REFLEX_ROUTER}")

    def _init_affect(self):
        """Initialize AFFECT PUB/SUB for fire-and-forget."""
        self.affect_xsub = self.ctx.socket(zmq.XSUB)
        self.affect_xpub = self.ctx.socket(zmq.XPUB)

        self.affect_xsub.setsockopt(zmq.RCVHWM, AFFECT_HWM)
        self.affect_xpub.setsockopt(zmq.SNDHWM, AFFECT_HWM)

        self.affect_xsub.bind(AFFECT_XSUB)
        self.affect_xpub.bind(AFFECT_XPUB)

        logger.info(f"Affect channel: XSUB={AFFECT_XSUB} XPUB={AFFECT_XPUB} HWM={AFFECT_HWM}")

    def _init_trophic(self):
        """Initialize TROPHIC PUSH/PULL for work distribution."""
        self.trophic_pull = self.ctx.socket(zmq.PULL)
        self.trophic_push = self.ctx.socket(zmq.PUSH)

        self.trophic_pull.setsockopt(zmq.RCVHWM, TROPHIC_HWM)
        self.trophic_push.setsockopt(zmq.SNDHWM, TROPHIC_HWM)

        self.trophic_pull.bind(TROPHIC_PULL)
        self.trophic_push.bind(TROPHIC_PUSH)

        logger.info(f"Trophic channel: PULL={TROPHIC_PULL} PUSH={TROPHIC_PUSH} HWM={TROPHIC_HWM}")

    def run(self):
        """Run the multi-channel proxy."""
        threads = [
            Thread(target=self._proxy_affect, name="affect-proxy", daemon=True),
            Thread(target=self._forward_trophic, name="trophic-forwarder", daemon=True),
            Thread(target=self._handle_reflex, name="reflex-handler", daemon=True),
            Thread(target=self._log_metrics, name="metrics-logger", daemon=True),
        ]

        if self._include_legacy:
            threads.insert(0, Thread(target=self._proxy_legacy, name="legacy-proxy", daemon=True))

        for t in threads:
            t.start()
            logger.info(f"Started thread: {t.name}")

        logger.info("ChannelProxy running - all channel threads started")

        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(timeout=1.0)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self._shutdown.set()
            logger.info("ChannelProxy shutting down")
            self._cleanup()

    def _proxy_legacy(self):
        """Forward legacy pub/sub traffic using zmq.proxy()."""
        try:
            zmq.proxy(self.legacy_xsub, self.legacy_xpub)
        except zmq.ZMQError as e:
            if not self._shutdown.is_set():
                logger.error(f"Legacy proxy error: {e}")

    def _proxy_affect(self):
        """Forward affect pub/sub traffic using zmq.proxy()."""
        try:
            zmq.proxy(self.affect_xsub, self.affect_xpub)
        except zmq.ZMQError as e:
            if not self._shutdown.is_set():
                logger.error(f"Affect proxy error: {e}")

    def _forward_trophic(self):
        """Forward trophic work distribution traffic."""
        poller = zmq.Poller()
        poller.register(self.trophic_pull, zmq.POLLIN)

        while not self._shutdown.is_set():
            try:
                socks = dict(poller.poll(timeout=1000))
                if self.trophic_pull in socks:
                    msg = self.trophic_pull.recv()
                    self.trophic_push.send(msg)
                    self.metrics["trophic"].messages_forwarded += 1
            except zmq.ZMQError as e:
                if not self._shutdown.is_set():
                    logger.error(f"Trophic forward error: {e}")
                    time.sleep(0.1)

    def _handle_reflex(self):
        """
        Handle REFLEX channel with acknowledgments.

        REFLEX uses ROUTER/DEALER pattern for acknowledged delivery.
        - Publishers connect as DEALER, send messages
        - Proxy receives via ROUTER, sends ACK/NACK
        - For MVP, proxy acknowledges immediately (consumer routing in future)
        """
        poller = zmq.Poller()
        poller.register(self.reflex_router, zmq.POLLIN)

        while not self._shutdown.is_set():
            try:
                socks = dict(poller.poll(timeout=1000))
                if self.reflex_router not in socks:
                    continue

                frames = self.reflex_router.recv_multipart()
                if len(frames) < 3:
                    continue

                sender_id = frames[0]
                message = frames[2]

                try:
                    msg_data = json.loads(message.decode("utf-8"))
                    signal_name = msg_data.get("signal", "unknown")
                    incident_id = msg_data.get("incident_id")

                    ack = json.dumps({
                        "ack": True,
                        "signal": signal_name,
                        "incident_id": incident_id,
                        "ts": time.time(),
                    })
                    self.reflex_router.send_multipart([sender_id, b"", ack.encode("utf-8")])
                    self.metrics["reflex"].ack_count += 1
                    self.metrics["reflex"].messages_forwarded += 1

                    logger.debug(f"REFLEX ACK: signal={signal_name} incident_id={incident_id}")

                except json.JSONDecodeError as e:
                    nack = json.dumps({
                        "ack": False,
                        "error": f"JSON decode error: {e}",
                        "ts": time.time(),
                    })
                    self.reflex_router.send_multipart([sender_id, b"", nack.encode("utf-8")])
                    self.metrics["reflex"].nack_count += 1
                    logger.warning(f"REFLEX NACK: JSON decode error")

                except Exception as e:
                    nack = json.dumps({
                        "ack": False,
                        "error": str(e),
                        "ts": time.time(),
                    })
                    self.reflex_router.send_multipart([sender_id, b"", nack.encode("utf-8")])
                    self.metrics["reflex"].nack_count += 1
                    logger.error(f"REFLEX NACK: {e}")

            except zmq.ZMQError as e:
                if not self._shutdown.is_set():
                    logger.error(f"Reflex handler error: {e}")
                    time.sleep(0.1)

    def _log_metrics(self):
        """Periodically log channel metrics."""
        while not self._shutdown.is_set():
            self._shutdown.wait(timeout=60.0)
            if self._shutdown.is_set():
                break

            for name, m in self.metrics.items():
                logger.info(
                    f"umn.channel_metrics channel={name} "
                    f"forwarded={m.messages_forwarded} "
                    f"dropped={m.messages_dropped} "
                    f"failed={m.messages_failed} "
                    f"acks={m.ack_count} nacks={m.nack_count}"
                )

    def _cleanup(self):
        """Clean up ZMQ sockets."""
        sockets = [
            self.reflex_router,
            self.affect_xsub, self.affect_xpub,
            self.trophic_pull, self.trophic_push,
        ]
        if self._include_legacy:
            sockets.extend([self.legacy_xsub, self.legacy_xpub])
        for sock in sockets:
            try:
                sock.close(linger=0)
            except Exception:
                pass

    def shutdown(self):
        """Signal shutdown."""
        self._shutdown.set()


def main():
    """CLI entry point for channel proxy."""
    import argparse

    parser = argparse.ArgumentParser(description="UMN Channel-Aware Proxy")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    proxy = ChannelProxy()

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        proxy.shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    proxy.run()


if __name__ == "__main__":
    main()
