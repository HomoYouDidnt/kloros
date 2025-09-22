#!/usr/bin/env python3
"""
Comprehensive test script for KLoROS speaker recognition system.
"""

import os
import sys
import traceback

# Add project root to path
sys.path.insert(0, '.')

def test_speaker_backend():
    """Test speaker backend functionality."""
    print("=== Testing Speaker Backend ===")

    try:
        from src.speaker.base import create_speaker_backend

        # Test mock backend
        print("Testing mock backend creation...")
        backend = create_speaker_backend('mock')
        print("[OK] Mock backend created")

        # Test user listing
        users = backend.list_users()
        print(f"[OK] Pre-populated users: {users}")

        # Test enrollment
        print("Testing user enrollment...")
        success = backend.enroll_user('testuser', [b'audio_sample'] * 5, 48000)
        print(f"[OK] Enrollment success: {success}")

        # Test identification
        print("Testing speaker identification...")
        result = backend.identify_speaker(b'audio_sample', 48000)
        print(f"[OK] Identification: user={result.user_id}, confidence={result.confidence:.2f}")

        # Test deletion
        print("Testing user deletion...")
        deleted = backend.delete_user('testuser')
        print(f"[OK] Deletion success: {deleted}")

        return True

    except Exception as e:
        print(f"[FAIL] Backend test failed: {e}")
        traceback.print_exc()
        return False

def test_enrollment_utilities():
    """Test enrollment utility functions."""
    print("\n=== Testing Enrollment Utilities ===")

    try:
        from src.speaker.enrollment import (
            parse_spelled_name, verify_name_spelling,
            format_enrollment_sentences, ENROLLMENT_SENTENCES
        )

        # Test name parsing
        print("Testing name parsing...")
        test_cases = [
            ("A-L-I-C-E", "Alice"),
            ("j o h n", "John"),
            ("K-A-T-H-E-R-I-N-E", "Katherine")
        ]

        for input_name, expected in test_cases:
            result = parse_spelled_name(input_name)
            if result == expected:
                print(f"[OK] '{input_name}' -> '{result}'")
            else:
                print(f"[FAIL] '{input_name}' -> '{result}' (expected '{expected}')")
                return False

        # Test name verification
        print("Testing name verification...")
        verified = verify_name_spelling("Catherine", "K-A-T-H-E-R-I-N-E")
        if verified == "Katherine":
            print(f"[OK] Name verification: Catherine -> Katherine")
        else:
            print(f"[FAIL] Name verification failed: got '{verified}'")
            return False

        # Test enrollment sentences
        print("Testing enrollment sentences...")
        sentences = format_enrollment_sentences("Alice")
        if len(sentences) == len(ENROLLMENT_SENTENCES):
            print(f"[OK] Generated {len(sentences)} enrollment sentences")
            for i, sentence in enumerate(sentences, 1):
                print(f"  {i}. {sentence}")
        else:
            print(f"[FAIL] Wrong number of sentences: {len(sentences)}")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] Enrollment utilities test failed: {e}")
        traceback.print_exc()
        return False

def test_kloros_integration():
    """Test KLoROS voice integration with speaker recognition."""
    print("\n=== Testing KLoROS Integration ===")

    try:
        # Set environment for testing
        os.environ['KLR_ENABLE_SPEAKER_ID'] = '1'
        os.environ['KLR_SPEAKER_BACKEND'] = 'mock'

        from src.kloros_voice import KLoROS

        print("Creating KLoROS instance...")
        kloros = KLoROS()

        # Check initialization
        if kloros.enable_speaker_id and kloros.speaker_backend:
            print("[OK] Speaker recognition initialized")
        else:
            print("[FAIL] Speaker recognition not initialized")
            return False

        # Test command handling
        print("Testing command handling...")

        # List users
        response = kloros._handle_enrollment_commands('list users')
        if "alice, bob, charlie" in response:
            print("[OK] List users command")
        else:
            print(f"[FAIL] List users failed: {response}")
            return False

        # Start enrollment
        response = kloros._handle_enrollment_commands('enroll me')
        if "voice profile" in response and "name" in response:
            print("[OK] Enrollment start command")
        else:
            print(f"[FAIL] Enrollment start failed: {response}")
            return False

        # Test enrollment flow
        print("Testing enrollment flow...")

        # Provide name
        response = kloros._handle_enrollment_commands('Alice')
        if "spell" in response:
            print("[OK] Name step completed")
        else:
            print(f"[FAIL] Name step failed: {response}")
            return False

        # Provide spelling
        response = kloros._handle_enrollment_commands('A-L-I-C-E')
        if "sentence" in response and "Alice" in response:
            print("[OK] Name verification completed")
        else:
            print(f"[FAIL] Name verification failed: {response}")
            return False

        # Simulate recording sentences
        for i in range(5):  # 5 enrollment sentences
            response = kloros._handle_enrollment_commands(f'sentence {i+1}')
            if i < 4:  # First 4 should ask for next sentence
                if "sentence" in response.lower():
                    print(f"[OK] Sentence {i+1} recorded")
                else:
                    print(f"[FAIL] Sentence {i+1} failed: {response}")
                    return False
            else:  # Last one should complete enrollment
                if "learned" in response or "voice" in response:
                    print("[OK] Enrollment completed")
                else:
                    print(f"[FAIL] Enrollment completion failed: {response}")
                    return False

        # Test cancellation
        kloros._handle_enrollment_commands('enroll me')  # Start again
        response = kloros._handle_enrollment_commands('cancel')
        if "cancelled" in response:
            print("[OK] Enrollment cancellation")
        else:
            print(f"[FAIL] Cancellation failed: {response}")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] KLoROS integration test failed: {e}")
        traceback.print_exc()
        return False

def test_speaker_identification():
    """Test speaker identification in the main voice loop."""
    print("\n=== Testing Speaker Identification ===")

    try:
        os.environ['KLR_ENABLE_SPEAKER_ID'] = '1'
        os.environ['KLR_SPEAKER_BACKEND'] = 'mock'

        from src.kloros_voice import KLoROS
        kloros = KLoROS()

        # Simulate audio identification
        print("Testing speaker identification...")

        # Mock audio bytes for testing
        test_audio = b'mock_audio_for_alice' * 1000
        kloros._last_audio_bytes = test_audio

        if kloros.speaker_backend:
            result = kloros.speaker_backend.identify_speaker(test_audio, kloros.sample_rate)
            print(f"[OK] Identification result: {result.user_id} (confidence: {result.confidence:.2f})")

            # Test with unknown speaker
            unknown_audio = b'completely_different_audio' * 1000
            result = kloros.speaker_backend.identify_speaker(unknown_audio, kloros.sample_rate)
            print(f"[OK] Unknown speaker result: {result.user_id} (confidence: {result.confidence:.2f})")

            return True
        else:
            print("[FAIL] Speaker backend not available")
            return False

    except Exception as e:
        print(f"[FAIL] Speaker identification test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("KLoROS Speaker Recognition System Test Suite")
    print("=" * 50)

    test_results = [
        test_speaker_backend(),
        test_enrollment_utilities(),
        test_kloros_integration(),
        test_speaker_identification()
    ]

    print("\n" + "=" * 50)
    print("Test Results:")

    passed = sum(test_results)
    total = len(test_results)

    test_names = [
        "Speaker Backend",
        "Enrollment Utilities",
        "KLoROS Integration",
        "Speaker Identification"
    ]

    for i, (name, result) in enumerate(zip(test_names, test_results)):
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All tests passed! Speaker recognition system is working correctly.")
        return True
    else:
        print(f"\n[ERROR] {total - passed} tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)