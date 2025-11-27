#!/usr/bin/env python3
"""
Switch KLoROS LLM backend between Ollama and llama.cpp.

This tool helps operators transition services from Ollama to llama.cpp
by updating environment variables and validating service health.
"""

import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check_backend_health(backend: str) -> bool:
    """Check if specified backend is healthy."""
    from src.cognition.reasoning.llm_router import LLMRouter, LLMMode

    router = LLMRouter(backend=backend)
    is_healthy, error = router.check_service_health(LLMMode.LIVE)

    if not is_healthy:
        print(f"  ✗ {backend} backend: {error}")
        return False

    print(f"  ✓ {backend} backend: healthy")
    return True


def list_backends():
    """List available backends and their status."""
    print("Available LLM Backends:")
    print()

    print("1. Ollama (current)")
    print("   Services:")
    print("     - ollama-live (port 11434)")
    print("     - ollama-think (port 11435)")
    print("   Status:")
    check_backend_health("ollama")
    print()

    print("2. llama.cpp (migration target)")
    print("   Services:")
    print("     - llama-live (port 8080)")
    print("     - llama-code (port 8081)")
    print("   Status:")
    check_backend_health("llama")
    print()


def test_backend(backend: str, mode: str = "live"):
    """Test backend with a sample query."""
    from src.cognition.reasoning.base import create_reasoning_backend

    print(f"Testing {backend} backend (mode={mode})...")

    try:
        reasoner = create_reasoning_backend(backend, mode=mode)
        response = reasoner.generate("Say 'OK' if you can hear me.")

        print(f"  ✓ Response: {response[:50]}...")
        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Switch KLoROS LLM backend between Ollama and llama.cpp"
    )
    parser.add_argument(
        "action",
        choices=["list", "test", "check"],
        help="Action to perform"
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "llama"],
        help="Backend to test (required for test/check action)"
    )
    parser.add_argument(
        "--mode",
        choices=["live", "think", "deep", "code"],
        default="live",
        help="LLM mode to test (default: live)"
    )

    args = parser.parse_args()

    if args.action == "list":
        list_backends()

    elif args.action == "test":
        if not args.backend:
            print("Error: --backend required for test action")
            sys.exit(1)

        success = test_backend(args.backend, args.mode)
        sys.exit(0 if success else 1)

    elif args.action == "check":
        if not args.backend:
            print("Error: --backend required for check action")
            sys.exit(1)

        success = check_backend_health(args.backend)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
