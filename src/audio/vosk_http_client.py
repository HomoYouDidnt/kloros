"""
HTTP client for persistent Vosk recognition service
Replaces the separated process architecture with HTTP calls
"""

import base64
import json
import time
from typing import Optional, Dict, Any, Callable
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout


class VoskHTTPClient:
    """Client for persistent Vosk HTTP service"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30  # 30 second timeout for requests

    def health_check(self) -> Dict[str, Any]:
        """Check if Vosk service is healthy"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def is_ready(self) -> bool:
        """Check if service is ready for recognition"""
        health = self.health_check()
        return health.get("status") == "healthy" and health.get("model_loaded", False)

    def recognize_audio(self, audio_data: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """Send audio data for recognition"""
        try:
            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')

            # Prepare request
            request_data = {
                "audio": audio_b64,
                "sample_rate": sample_rate
            }

            # Send request
            response = self.session.post(
                f"{self.base_url}/recognize",
                json=request_data,
                timeout=30
            )
            response.raise_for_status()

            return response.json()

        except ConnectionError:
            return {"error": "Cannot connect to Vosk service"}
        except Timeout:
            return {"error": "Recognition request timed out"}
        except RequestException as e:
            return {"error": f"HTTP request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Recognition failed: {str(e)}"}


class VoskHTTPProcessor:
    """
    Drop-in replacement for VoskProcess that uses HTTP service
    Compatible with existing KLoROS audio architecture
    """

    def __init__(self,
                 on_wake_detected: Callable[[str], None] = None,
                 on_recognition_result: Callable[[str], None] = None,
                 wake_phrases: list = None):

        self.on_wake_detected = on_wake_detected or (lambda x: None)
        self.on_recognition_result = on_recognition_result or (lambda x: None)
        self.wake_phrases = wake_phrases or ["kloros"]

        self.client = VoskHTTPClient()
        self.running = False

    def start(self) -> bool:
        """Start the processor (just check service availability)"""
        if not self.client.is_ready():
            print("[vosk-http] ERROR: Vosk service not ready")
            return False

        print("[vosk-http] Connected to Vosk service")
        self.running = True
        return True

    def stop(self):
        """Stop the processor"""
        self.running = False
        print("[vosk-http] Disconnected from Vosk service")

    def process_audio_chunk(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
        """Process audio chunk and return recognized text"""
        if not self.running:
            return None

        result = self.client.recognize_audio(audio_data, sample_rate)

        if "error" in result:
            print(f"[vosk-http] Recognition error: {result['error']}")
            return None

        text = result.get("text", "").strip()
        confidence = result.get("confidence", 0.0)

        if text:
            # Check for wake phrases
            text_lower = text.lower()
            for wake_phrase in self.wake_phrases:
                if wake_phrase.lower() in text_lower:
                    print(f"[vosk-http] Wake phrase detected: {text}")
                    self.on_wake_detected(text)
                    return text

            # Regular recognition result
            if confidence > 0.3:  # Basic confidence threshold
                print(f"[vosk-http] Recognized: {text} (confidence: {confidence:.2f})")
                self.on_recognition_result(text)
                return text

        return None

    def is_healthy(self) -> bool:
        """Check if processor is healthy"""
        return self.running and self.client.is_ready()


def test_vosk_http_client():
    """Simple test function"""
    client = VoskHTTPClient()

    print("Testing Vosk HTTP client...")

    # Health check
    health = client.health_check()
    print(f"Health: {health}")

    if client.is_ready():
        print("✓ Vosk service is ready")

        # Test with dummy audio data (silence)
        dummy_audio = b'\x00' * 1024  # 1KB of silence
        result = client.recognize_audio(dummy_audio)
        print(f"Test recognition result: {result}")
    else:
        print("✗ Vosk service not ready")


if __name__ == "__main__":
    test_vosk_http_client()
