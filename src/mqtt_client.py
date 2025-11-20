"""MQTT event publisher for KLoROS E2E testing."""
import json
import os
from typing import Any, Optional

import paho.mqtt.client as mqtt


class KLoROSMQTTClient:
    """
    Publishes KLoROS events to MQTT broker for E2E test observation.

    Events published:
    - kloros/turn/started: When user turn begins
    - kloros/turn/completed: When system response completes
    - kloros/tool/called: When introspection tool is called
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        enabled: bool = True
    ):
        """
        Initialize MQTT client.

        Args:
            broker: MQTT broker hostname
            port: MQTT broker port
            enabled: Whether MQTT publishing is enabled (default: check KLR_MQTT_ENABLED env)
        """
        # Check environment variable to enable/disable
        env_enabled = os.getenv("KLR_MQTT_ENABLED", "0")
        self.enabled = enabled and env_enabled in ("1", "true", "True")

        if not self.enabled:
            self.client = None
            return

        self.broker = broker
        self.port = port

        try:
            self.client = mqtt.Client()
            self.client.connect(broker, port, keepalive=60)
            self.client.loop_start()
            print(f"[mqtt] Connected to {broker}:{port}")
        except Exception as e:
            print(f"[mqtt] Failed to connect: {e}")
            self.client = None
            self.enabled = False

    def publish_event(self, topic: str, payload: dict[str, Any]) -> None:
        """
        Publish event to MQTT broker.

        Args:
            topic: MQTT topic (e.g., "kloros/turn/completed")
            payload: Event payload as dict
        """
        if not self.enabled or self.client is None:
            return

        try:
            message = json.dumps(payload)
            result = self.client.publish(topic, message, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[mqtt] Failed to publish to {topic}: {result.rc}")
        except Exception as e:
            print(f"[mqtt] Publish error: {e}")

    def publish_turn_started(self, user_text: str) -> None:
        """Publish turn_started event."""
        self.publish_event("kloros/turn/started", {
            "user_text": user_text[:200],  # Truncate for safety
            "timestamp": self._timestamp()
        })

    def publish_turn_completed(
        self,
        user_text: str,
        response_text: str,
        latency_ms: int,
        tool_calls: int = 0
    ) -> None:
        """Publish turn_completed event."""
        self.publish_event("kloros/turn/completed", {
            "user_text": user_text[:200],
            "response_text": response_text[:500],
            "latency_ms": latency_ms,
            "tool_calls": tool_calls,
            "timestamp": self._timestamp()
        })

    def publish_tool_called(self, tool_name: str, success: bool) -> None:
        """Publish tool_called event."""
        self.publish_event("kloros/tool/called", {
            "tool_name": tool_name,
            "success": success,
            "timestamp": self._timestamp()
        })

    def _timestamp(self) -> str:
        """Get ISO8601 timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("[mqtt] Disconnected")
