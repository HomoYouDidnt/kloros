"""MQTT event bus monitor for E2E testing."""
import json
import queue
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt


class MQTTEventMonitor:
    """
    Subscribe to MQTT events and buffer them for test assertions.

    Usage:
        monitor = MQTTEventMonitor()
        monitor.start()

        # Wait for specific event
        event = monitor.wait_for_event("kloros/turn/completed", timeout_s=10)
        assert event["tool_calls"] == 1

        monitor.stop()
    """

    def __init__(self, broker: str = "localhost", port: int = 1883):
        """
        Initialize MQTT event monitor.

        Args:
            broker: MQTT broker hostname
            port: MQTT broker port
        """
        self.broker = broker
        self.port = port
        self.client: mqtt.Client | None = None
        self.event_queue: queue.Queue = queue.Queue()
        self.running = False
        self._thread: threading.Thread | None = None

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to broker."""
        if rc == 0:
            print(f"[bus] Connected to MQTT broker at {self.broker}:{self.port}")
            # Subscribe to all KLoROS events
            client.subscribe("kloros/#", qos=1)
            print("[bus] Subscribed to kloros/# topics")
        else:
            print(f"[bus] Failed to connect to MQTT broker: {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback when message received."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            event = {
                "topic": msg.topic,
                "payload": payload,
                "timestamp": time.time()
            }
            self.event_queue.put(event)
            print(f"[bus] Received event: {msg.topic}")
        except Exception as e:
            print(f"[bus] Failed to parse message: {e}")

    def start(self) -> None:
        """Start monitoring MQTT events."""
        if self.running:
            return

        self.running = True
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()

            # Wait for connection to establish
            time.sleep(0.5)
        except Exception as e:
            print(f"[bus] Failed to start: {e}")
            self.running = False
            self.client = None

    def stop(self) -> None:
        """Stop monitoring MQTT events."""
        if not self.running or not self.client:
            return

        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
        self.client = None
        print("[bus] Stopped monitoring")

    def clear_events(self) -> None:
        """Clear all buffered events."""
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                break

    def wait_for_event(
        self,
        topic: str,
        timeout_s: float = 10.0,
        predicate: callable = None
    ) -> dict[str, Any] | None:
        """
        Wait for specific MQTT event.

        Args:
            topic: MQTT topic to wait for (exact match or prefix if ends with '#')
            timeout_s: Maximum time to wait in seconds
            predicate: Optional function to filter events (receives payload, returns bool)

        Returns:
            Event dict with 'topic', 'payload', 'timestamp' keys, or None if timeout
        """
        if not self.running:
            print("[bus] Monitor not running")
            return None

        start_time = time.time()
        topic_prefix = topic.rstrip("#")

        while (time.time() - start_time) < timeout_s:
            try:
                event = self.event_queue.get(timeout=0.1)

                # Check topic match
                if topic.endswith("#"):
                    topic_match = event["topic"].startswith(topic_prefix)
                else:
                    topic_match = event["topic"] == topic

                if topic_match:
                    # Check optional predicate
                    if predicate is None or predicate(event["payload"]):
                        return event
                    else:
                        # Put it back if predicate fails
                        self.event_queue.put(event)
                else:
                    # Put it back if topic doesn't match
                    self.event_queue.put(event)

            except queue.Empty:
                continue

        print(f"[bus] Timeout waiting for event: {topic}")
        return None

    def get_all_events(self) -> list[dict[str, Any]]:
        """Get all buffered events."""
        events = []
        while not self.event_queue.empty():
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events


# Global monitor instance for tests
_monitor: MQTTEventMonitor | None = None


def get_monitor() -> MQTTEventMonitor:
    """Get or create global MQTT monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = MQTTEventMonitor()
    return _monitor


def start_monitor() -> None:
    """Start global MQTT monitor."""
    monitor = get_monitor()
    if not monitor.running:
        monitor.start()


def stop_monitor() -> None:
    """Stop global MQTT monitor."""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None
