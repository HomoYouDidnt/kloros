#!/usr/bin/env python3
"""Test command understanding and processing - USER RUNS THIS"""
import sys
sys.path.insert(0, '/home/kloros')

print("=" * 60)
print("KLoROS Command Processing Test")
print("=" * 60)
print()
print("This test checks if KLoROS can understand and execute commands")
print("in text-only mode (no voice required).")
print()

test_commands = [
    "Check recent errors",
    "What's your current TTS model?",
    "List the last 5 episodes",
    "Show system status",
    "What models are you using?"
]

try:
    # Try to import reasoning backend
    from src.reasoning.local_rag_backend import LocalRagBackend

    print("✅ Reasoning backend loaded")
    print()

    # Initialize backend
    rag = LocalRagBackend()

    if rag.rag_instance is None:
        print("❌ RAG instance not initialized")
        print()
    else:
        print(f"✅ RAG initialized with {len(rag.rag_instance.metadata)} documents")
        print()

    # Test each command
    print("🧪 Testing Commands:")
    print("=" * 60)
    print()

    for i, command in enumerate(test_commands, 1):
        print(f"Test {i}/{len(test_commands)}: {command}")
        print("-" * 60)

        try:
            result = rag.reply(command)

            # Check if it tried to use a tool
            if "TOOL:" in result.reply_text or "Tool executed:" in str(result.sources):
                tool_attempted = True
                print("   🔧 Tool execution attempted")
            else:
                tool_attempted = False
                print("   💬 Conversational response (no tool)")

            # Check for errors
            if "failed" in result.reply_text.lower() or "error" in result.reply_text.lower():
                print(f"   ❌ Error in response")
            else:
                print(f"   ✅ Response generated")

            # Show preview
            preview = result.reply_text[:100].replace('\n', ' ')
            print(f"   📝 Preview: {preview}...")

        except Exception as e:
            print(f"   ❌ Command failed: {e}")

        print()

    print("=" * 60)
    print("Test Summary:")
    print("=" * 60)
    print()
    print("If you see 'No module named sounddevice' errors:")
    print("  → Install: pip install sounddevice")
    print()
    print("If commands work but return empty/generic responses:")
    print("  → Memory system may need fixing (see context retrieval test)")
    print()
    print("If tool executions fail:")
    print("  → Check tool_availability_matrix.md for details")
    print()

except ImportError as e:
    print(f"❌ Import error: {e}")
    print()
    print("Make sure you're running in the KLoROS venv:")
    print("  source /home/kloros/venv/bin/activate")
    print()
except Exception as e:
    print(f"❌ Test setup failed: {e}")
    import traceback
    traceback.print_exc()
