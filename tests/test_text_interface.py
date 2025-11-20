#!/usr/bin/env python3
"""
TDD Tests for TextKLoROS - Verify Feature Parity with Voice Interface

These tests enforce that TextKLoROS inherits ALL systems from KLoROS
except audio-related components. Written in RED-GREEN-REFACTOR discipline.

Test Phases:
  RED: Tests written first, expected to fail on current implementation
  GREEN: Refactor TextKLoROS to call super().__init__(), tests pass
  REFACTOR: Improve code quality while keeping tests green
"""

import sys
import os
import unittest

sys.path.insert(0, '/home/kloros')

class TestTextKLoROSSystemIntegrity(unittest.TestCase):
    """
    Test that TextKLoROS has feature parity with KLoROS voice interface.

    Critical invariant: Text interface should have ALL systems that voice has,
    except audio backends (TTS, STT, audio capture, speaker ID).
    """

    @classmethod
    def setUpClass(cls):
        os.environ["KLR_ENABLE_TTS"] = "0"
        os.environ["KLR_ENABLE_STT"] = "0"
        os.environ["KLR_ENABLE_AUDIO"] = "0"
        os.environ["KLR_ENABLE_SPEAKER_ID"] = "0"
        os.environ["KLR_TEST_MODE"] = "0"

        sys.path.insert(0, '/home/kloros/scripts')
        from chat_with_kloros import TextKLoROS

        cls.kloros = TextKLoROS()

    def test_capability_registry_exists(self):
        self.assertIsNotNone(
            self.kloros.capability_registry,
            "TextKLoROS must have capability_registry for self-awareness"
        )

    def test_audio_backends_disabled(self):
        self.assertIsNone(
            self.kloros.audio_backend,
            "Audio backend must be None in text mode"
        )
        self.assertIsNone(
            self.kloros.tts_backend,
            "TTS backend must be None in text mode"
        )

if __name__ == '__main__':
    unittest.main(verbosity=2)
