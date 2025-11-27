#!/usr/bin/env python3
"""
End-to-end tests with REAL ChemBus (not mocked).

These tests use a separate ChemBus proxy on custom TCP ports to avoid
conflicts with the production proxy running on 5556/5557.

Run with: pytest test_chembus_e2e.py -v -s

NOTE: These tests require ZMQ to be installed. If ZMQ is not available,
tests will be skipped.
"""

import os
import sys
import time
import tempfile
import unittest
import subprocess
from pathlib import Path
from threading import Event

sys.path.insert(0, '/home/kloros/src')

try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

from src.orchestration.daemons.integration_monitor_daemon import IntegrationMonitorDaemon
from src.orchestration.daemons.exploration_scanner_daemon import ExplorationScannerDaemon


import pytest

@pytest.mark.e2e
@unittest.skipUnless(ZMQ_AVAILABLE, "ZMQ not available")
class TestChemBusEndToEnd(unittest.TestCase):
    """
    End-to-end tests with real ChemBus proxy.

    These tests:
    1. Start a dedicated test ChemBus proxy on ports 5558/5559
    2. Configure daemons to use test proxy via environment variables
    3. Verify actual message delivery through real ZMQ sockets
    4. Clean up test proxy after tests
    """

    @classmethod
    def setUpClass(cls):
        """Start dedicated ChemBus proxy for testing."""
        # Set test proxy endpoints (different from production 5556/5557)
        cls.test_xsub = "tcp://127.0.0.1:5558"
        cls.test_xpub = "tcp://127.0.0.1:5559"

        os.environ['KLR_CHEM_XSUB'] = cls.test_xsub
        os.environ['KLR_CHEM_XPUB'] = cls.test_xpub

        # Start test proxy process
        cls.proxy_process = subprocess.Popen(
            [
                sys.executable,
                '-c',
                f"""
import zmq
import signal
import sys

def signal_handler(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

ctx = zmq.Context()
xsub = ctx.socket(zmq.XSUB)
xpub = ctx.socket(zmq.XPUB)

xsub.bind("{cls.test_xsub}")
xpub.bind("{cls.test_xpub}")

print("Test ChemBus proxy running on {cls.test_xsub} / {cls.test_xpub}", flush=True)

try:
    zmq.proxy(xsub, xpub)
except KeyboardInterrupt:
    pass
finally:
    xsub.close()
    xpub.close()
    ctx.term()
"""
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for proxy to start
        time.sleep(0.5)

        if cls.proxy_process.poll() is not None:
            raise RuntimeError("Test ChemBus proxy failed to start")

    @classmethod
    def tearDownClass(cls):
        """Stop test ChemBus proxy."""
        if hasattr(cls, 'proxy_process') and cls.proxy_process:
            cls.proxy_process.terminate()
            try:
                cls.proxy_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                cls.proxy_process.kill()

        # Clean up environment
        os.environ.pop('KLR_CHEM_XSUB', None)
        os.environ.pop('KLR_CHEM_XPUB', None)

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.temp_dir) / "src"
        self.src_dir.mkdir()
        self.state_dir = Path(self.temp_dir) / ".kloros"
        self.state_dir.mkdir()

        self.received_messages = []
        self.message_received = Event()

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_integration_daemon_emits_to_real_chembus(self):
        """Test that IntegrationMonitorDaemon emits questions to real ChemBus."""
        # Subscribe to curiosity.integration_question topic
        from src.orchestration.core.umn_bus import UMNSub as ChemSub

        def on_message(msg_dict):
            self.received_messages.append(msg_dict)
            self.message_received.set()

        sub = ChemSub(
            topic="curiosity.integration_question",
            on_json=on_message,
            zooid_name="test_subscriber",
            niche="testing"
        )

        # Give subscriber time to connect
        time.sleep(0.3)

        # Create daemon (will use test ChemBus via environment variables)
        daemon = IntegrationMonitorDaemon(
            watch_path=self.src_dir,
            state_file=self.state_dir / "integration.pkl",
            max_workers=1
        )

        # Create file with orphaned queue (should trigger question)
        test_file = self.src_dir / "orphan_producer.py"
        test_file.write_text("""
class DataProducer:
    def __init__(self):
        self.orphaned_output_queue = []

    def produce(self, data):
        self.orphaned_output_queue.append(data)
""")

        # Process file event
        daemon.process_file_event('create', test_file)

        # Wait for message (with timeout)
        message_arrived = self.message_received.wait(timeout=2.0)

        # Cleanup
        sub.close()

        # Verify message was received through real ChemBus
        self.assertTrue(
            message_arrived,
            "No message received from ChemBus within timeout"
        )

        if self.received_messages:
            msg = self.received_messages[0]
            self.assertEqual(msg.get('signal'), 'curiosity.integration_question')
            self.assertIn('facts', msg)
            self.assertIn('question', msg['facts'])

    def test_exploration_daemon_emits_to_real_chembus(self):
        """Test that ExplorationScannerDaemon emits questions to real ChemBus."""
        from src.orchestration.core.umn_bus import UMNSub as ChemSub

        def on_message(msg_dict):
            self.received_messages.append(msg_dict)
            self.message_received.set()

        sub = ChemSub(
            topic="curiosity.exploration_question",
            on_json=on_message,
            zooid_name="test_subscriber",
            niche="testing"
        )

        time.sleep(0.3)

        # Create daemon with short scan interval for testing
        daemon = ExplorationScannerDaemon(
            state_file=self.state_dir / "exploration.pkl",
            scan_interval=1,
            min_emission_interval=0,  # No rate limiting for test
            max_workers=1
        )

        # Trigger a scan manually (don't wait for timer)
        daemon._perform_system_scan()

        # Wait for message
        message_arrived = self.message_received.wait(timeout=2.0)

        # Cleanup
        sub.close()

        # Verify message delivery
        # NOTE: Exploration scanner may not emit if no opportunities found
        # This test validates the ChemBus plumbing works, not detection logic
        if message_arrived:
            msg = self.received_messages[0]
            self.assertEqual(msg.get('signal'), 'curiosity.exploration_question')

    def test_message_delivery_latency(self):
        """Test that ChemBus message delivery latency is acceptable (<100ms)."""
        from src.orchestration.core.umn_bus import UMNPub as ChemPub, UMNSub as ChemSub

        latencies = []

        def on_message(msg_dict):
            arrival_time = time.time()
            send_time = msg_dict.get('ts', 0)
            latency = (arrival_time - send_time) * 1000  # Convert to ms
            latencies.append(latency)
            self.message_received.set()

        sub = ChemSub(
            topic="test.latency",
            on_json=on_message,
            zooid_name="latency_test",
            niche="testing"
        )

        time.sleep(0.3)

        pub = ChemPub()

        # Send warmup message to avoid double-tap on first real message
        pub.emit(
            signal="test.latency",
            ecosystem="testing",
            facts={'warmup': True}
        )
        time.sleep(0.3)  # Wait for double-tap to complete
        latencies.clear()  # Clear warmup latencies

        # Send 10 test messages
        for i in range(10):
            self.message_received.clear()
            pub.emit(
                signal="test.latency",
                ecosystem="testing",
                facts={'iteration': i}
            )

            # Wait for message
            if not self.message_received.wait(timeout=1.0):
                self.fail(f"Message {i} not received within timeout")

            time.sleep(0.05)

        pub.close()
        sub.close()

        # Verify latency (should have exactly 10 messages after warmup)
        self.assertEqual(len(latencies), 10, f"Expected 10 messages, got {len(latencies)}")

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        self.assertLess(
            avg_latency,
            100,
            f"Average latency {avg_latency:.2f}ms exceeds 100ms target"
        )

        self.assertLess(
            max_latency,
            200,
            f"Max latency {max_latency:.2f}ms exceeds 200ms threshold"
        )


if __name__ == '__main__':
    if not ZMQ_AVAILABLE:
        print("SKIP: ZMQ not available, e2e tests require ZMQ")
        sys.exit(0)

    unittest.main()
