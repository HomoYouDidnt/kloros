#!/home/kloros/.venv/bin/python3
"""Text-based chat interface for KLoROS - runs alongside voice service."""

import sys
sys.path.insert(0, '/home/kloros')

from src.kloros_voice import load_kloros_environment, KLoROS

# Load environment
load_kloros_environment()

# Initialize KLoROS with lightweight configuration (no audio/TTS conflicts)
print("Initializing KLoROS text interface...")

class TextKLoROS(KLoROS):
    """
    Text-only KLoROS interface - inherits full system stack with audio disabled.

    Architecture:
      - Calls parent KLoROS.__init__() for complete system initialization
      - Disables audio via environment flags before parent initialization
      - Inherits ALL cognitive systems: consciousness, meta-cognition, self-healing, etc.
      - Provides feature parity with voice interface except audio backends
    """

    def __init__(self):
        import os

        print("[text] Initializing TextKLoROS with full system inheritance...")

        os.environ["KLR_ENABLE_TTS"] = "0"
        os.environ["KLR_ENABLE_STT"] = "0"
        os.environ["KLR_ENABLE_AUDIO"] = "0"
        os.environ["KLR_ENABLE_SPEAKER_ID"] = "0"

        self.operator_id = "text_user"

        super().__init__()

        assert self.audio_backend is None, "Audio backend must be None in text mode"
        assert self.tts_backend is None, "TTS backend must be None in text mode"
        assert self.stt_backend is None, "STT backend must be None in text mode"

        print("[text] ✓ Full KLoROS initialized in text-only mode")
        print(f"[text] ✓ Capability registry: {len(getattr(self.capability_registry, 'capabilities', [])) if self.capability_registry else 0} capabilities")
        print(f"[text] ✓ MCP integration: {'active' if self.mcp else 'inactive'}")
        print(f"[text] ✓ Self-healing: {'active' if self.heal_bus else 'inactive'}")
        print(f"[text] ✓ Consciousness: {'integrated' if hasattr(self, '_consciousness_integrated') else 'not integrated'}")

if __name__ == '__main__':
    try:
        kloros = TextKLoROS()

        print("\n" + "="*60)
        print("KLoROS Text Chat Interface")
        print("="*60)
        print("Full KLoROS system routing with text-only interface")
        print()
        print("Active Systems:")
        print(f"  Reasoning Backend: {kloros.reason_backend_name}")
        print(f"  Memory Enhanced: {'✓' if kloros.memory_enhanced else '✗'}")
        print(f"  Tool Registry: {'✓' if hasattr(kloros, 'tool_registry') and kloros.tool_registry else '✗'}")
        print(f"  Capability Registry: {'✓' if kloros.capability_registry else '✗'} ({len(getattr(kloros.capability_registry, 'capabilities', [])) if kloros.capability_registry else 0} capabilities)")
        print(f"  MCP Integration: {'✓' if kloros.mcp else '✗'}")
        print(f"  Consciousness: {'✓' if hasattr(kloros, '_consciousness_integrated') else '✗'}")
        print(f"  Self-Healing: {'✓' if kloros.heal_bus else '✗'}")
        print(f"  RAG System: {'✓' if kloros.rag else '✗'}")
        print(f"  C2C Communication: {'✓' if kloros.c2c_manager else '✗'}")
        print()
        print("Voice service is still running in the background")
        print("This chat uses the same reasoning pipeline as voice")
        print("All conversations are logged to episodic memory")
        print()
        print("Type 'exit' or 'quit' to close this interface.")
        print("="*60 + "\n")

    except KeyboardInterrupt:
        print("\n\nInitialization cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL: Failed to initialize TextKLoROS: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\nKLoROS: Closing text interface. Voice service still running.")
                sys.exit(0)

            response = kloros.chat(user_input)
            print(f"\nKLoROS: {response}\n")

        except KeyboardInterrupt:
            print("\n\nKLoROS: Text interface interrupted. Voice service still running.")
            sys.exit(0)
        except EOFError:
            print("\n\nKLoROS: EOF received. Exiting text interface.")
            sys.exit(0)
        except Exception as e:
            print(f"\nError during chat: {e}")
            import traceback
            traceback.print_exc()
            print("Continuing... (type 'exit' to quit)\n")