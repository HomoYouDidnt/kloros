#!/usr/bin/env python3
"""Standalone KLoROS Chat Interface - No Voice Dependencies"""

import sys
import os
from pathlib import Path

# Add both project root and src directory to path (required for imports)
project_root = Path('/home/kloros')
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

def load_environment():
    """Load KLoROS environment without voice imports."""
    env_file = '/home/kloros/.kloros_env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

class StandaloneKLoROS:
    """Standalone KLoROS for chat without voice dependencies."""

    def __init__(self):
        load_environment()

        # Initialize core components only
        self.conversation_history = []
        self.reason_backend = None
        self.memory_enhanced = None
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_0")
        self.reason_backend_name = "local_rag"  # Fix backend type detection

        # Stub attributes for tool compatibility (text mode - no audio)
        self.audio_backend = None
        self.audio_backend_name = "none"
        self.stt_backend = None
        self.stt_backend_name = "none"
        self.tts_backend = None
        self.tts_backend_name = "none"
        self.speaker_backend = None
        self.speaker_backend_name = "none"
        self.sample_rate = None
        self.audio_device_index = None
        self.input_gain = None

        # Initialize reasoning backend
        self._init_reasoning()

        # Initialize memory if available
        self._init_memory()

        # Initialize consciousness system (single source of truth)
        from src.cognition.consciousness.integration import integrate_consciousness
        integrate_consciousness(self, cooldown=5.0, max_expressions=10)

    def _init_reasoning(self):
        """Initialize reasoning backend."""
        try:
            from src.cognition.reasoning.local_rag_backend import LocalRagBackend
            self.reason_backend = LocalRagBackend()
            print("[chat] Reasoning backend initialized")
        except Exception as e:
            print(f"[chat] Reasoning backend failed: {e}")

    def _init_memory(self):
        """Initialize memory system."""
        try:
            if os.getenv('KLR_ENABLE_MEMORY', '0') == '1':
                from src.kloros_memory.integration import create_memory_enhanced_kloros
                self.memory_enhanced = create_memory_enhanced_kloros(self)
                print("[chat] Memory system initialized")

                # Check if we need to create episodes from existing events
                if self.memory_enhanced and self.memory_enhanced.enable_memory:
                    stats = self.memory_enhanced.get_memory_stats()
                    total_events = stats.get('total_events', 0)
                    total_episodes = stats.get('total_episodes', 0)

                    # If we have many events but no episodes, create them
                    if total_events > 100 and total_episodes == 0:
                        print(f"[chat] Found {total_events} events but no episodes")
                        print(f"[chat] Creating episodes from historical events...")
                        try:
                            # Use auto_episode_detection to create episodes from all events
                            episodes_created = self.memory_enhanced.episode_condenser.auto_episode_detection()
                            print(f"[chat] ✅ Created {episodes_created} episodes")

                            # Now condense the newly created episodes
                            if episodes_created > 0:
                                print(f"[chat] Condensing episodes (this may take a moment)...")
                                episodes_condensed = self.memory_enhanced.episode_condenser.process_uncondensed_episodes(limit=50)
                                print(f"[chat] ✅ Condensed {episodes_condensed} episodes")

                        except Exception as e:
                            print(f"[chat] Episode creation/condensation failed: {e}")
                            import traceback
                            traceback.print_exc()

        except Exception as e:
            print(f"[chat] Memory initialization failed: {e}")


    def chat(self, message):
        """Process chat message through reasoning system with memory context."""
        if not self.reason_backend:
            return "❌ Reasoning system not available"

        try:
            # Update consciousness system
            from src.cognition.consciousness.integration import process_event, update_consciousness_signals

            process_event(self, "user_input", metadata={'message': message})
            update_consciousness_signals(self, user_interaction=True, confidence=0.7)

            # Log to memory if available
            if self.memory_enhanced and hasattr(self.memory_enhanced, 'memory_logger'):
                self.memory_enhanced.memory_logger.log_user_input(
                    transcript=message, confidence=0.95
                )

            # ENHANCEMENT: Retrieve relevant memory context before processing
            memory_context_str = ""
            if self.memory_enhanced and self.memory_enhanced.enable_memory:
                try:
                    # Retrieve relevant episodes and events
                    context_result = self.memory_enhanced._retrieve_context(message)

                    if context_result:
                        # Format context for inclusion in prompt
                        memory_context_str = self.memory_enhanced._format_context_for_prompt(context_result)

                        if memory_context_str:
                            # Log successful context retrieval
                            events_count = len(context_result.events)
                            summaries_count = len(context_result.summaries)
                            print(f"[memory] Retrieved {events_count} events, {summaries_count} summaries")

                            # Prepend memory context to the user message
                            # The reasoning backend will see this enriched context
                            memory_context_str = f"\n\nRelevant context from past conversations:\n{memory_context_str}\n"
                except Exception as e:
                    print(f"[memory] Context retrieval failed: {e}")

            # Process through reasoning with tool integration
            # If memory context was retrieved, the reasoning backend's RAG system
            # will have access to it through the enriched query
            import inspect
            sig = inspect.signature(self.reason_backend.reply)

            # Create enriched message with memory context
            enriched_message = message
            if memory_context_str:
                enriched_message = memory_context_str + "\n" + message

            if 'kloros_instance' in sig.parameters:
                result = self.reason_backend.reply(enriched_message, kloros_instance=self)
            else:
                result = self.reason_backend.reply(enriched_message)

            response = result.reply_text

            # Process consciousness and add grounded expression if policy changed
            from src.cognition.consciousness.integration import process_consciousness_and_express
            response = process_consciousness_and_express(
                self,
                response=response,
                success=True,
                confidence=0.8,
                retries=0
            )

            # Log response to memory
            if self.memory_enhanced and hasattr(self.memory_enhanced, 'memory_logger'):
                self.memory_enhanced.memory_logger.log_llm_response(
                    response=response, model='qwen2.5:14b-instruct-q4_0'
                )

            return response

        except Exception as e:
            # Update consciousness: error occurred
            from src.cognition.consciousness.integration import process_event, update_consciousness_signals
            process_event(self, "error_detected", metadata={'error': str(e)})
            update_consciousness_signals(self, success=False, exception=True)

            return f"❌ Chat processing failed: {e}"

    def handle_conversation(self):
        """Handle conversation - placeholder for memory integration compatibility."""
        # This method exists for memory integration compatibility
        # In standalone chat mode, conversations are handled via direct chat() calls
        pass

    def listen_for_wake_word(self):
        """Listen for wake word - placeholder for memory integration compatibility."""
        # This method exists for memory integration compatibility
        # In standalone chat mode, there is no wake word detection needed
        pass

    def get_component_status(self) -> dict:
        """Return status of available components in text mode."""
        return {
            "mode": "text_only",
            "audio_backend": {"initialized": False, "reason": "Text mode - no audio"},
            "stt_backend": {"initialized": False, "reason": "Text mode - no STT"},
            "tts_backend": {"initialized": False, "reason": "Text mode - no TTS"},
            "reasoning_backend": {
                "name": self.reason_backend_name,
                "initialized": self.reason_backend is not None,
            },
            "memory": {
                "enabled": self.memory_enhanced is not None,
            }
        }

    def generate_full_diagnostic(self) -> str:
        """Generate diagnostic report for text-only mode."""
        status = self.get_component_status()
        output = "✅ KLoROS Text Mode Diagnostic\n"
        output += "=" * 50 + "\n"
        output += f"Mode: {status['mode']}\n"
        output += f"Reasoning: {status['reasoning_backend']['name']} - "
        output += f"{'✅ OK' if status['reasoning_backend']['initialized'] else '❌ Failed'}\n"
        output += f"Memory: {'✅ Enabled' if status['memory']['enabled'] else '⚠️ Disabled'}\n"
        output += "\nAudio/STT/TTS: Not available in text mode\n"
        return output

    def get_audio_diagnostics(self) -> str:
        """Return audio diagnostics - not available in text mode."""
        return "⚠️ Audio diagnostics not available in text-only mode"

    def get_memory_diagnostics(self) -> str:
        """Return memory system diagnostics."""
        if not self.memory_enhanced:
            return "❌ Memory system not initialized (KLR_ENABLE_MEMORY may be disabled)"

        try:
            # Get memory stats
            stats = self.memory_enhanced.get_memory_stats()

            output = "✅ MEMORY SYSTEM STATUS\n"
            output += "=" * 50 + "\n"
            output += f"Status: Enabled and operational\n"
            output += f"Total Events: {stats.get('total_events', 0)}\n"
            output += f"Total Episodes: {stats.get('total_episodes', 0)}\n"
            output += f"Database: {stats.get('db_path', 'Unknown')}\n"
            output += f"Database Size: {stats.get('db_size_bytes', 0) / 1024:.1f} KB\n"

            # Get recent activity
            recent_events = stats.get('recent_event_count', 0)
            if recent_events > 0:
                output += f"Recent Activity: {recent_events} events in last hour\n"

            return output

        except Exception as e:
            return f"⚠️ Memory system initialized but stats retrieval failed: {e}"

    def get_affective_diagnostics(self) -> str:
        """Return affective system diagnostics (consciousness substrate)."""
        from src.cognition.consciousness.integration import get_consciousness_diagnostics
        return get_consciousness_diagnostics(self)

def main():
    print("\n" + "="*60)
    print("KLoROS Standalone Chat Interface")
    print("="*60)
    print("✅ No voice dependencies - pure reasoning system")
    print("🧠 Full tool execution and memory capabilities")
    print("💬 Conversational AI system administration")
    print("Type 'exit' to quit.")
    print("="*60 + "\n")

    try:
        kloros = StandaloneKLoROS()

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print("\nKLoROS: Session terminated.")
                    break

                response = kloros.chat(user_input)
                print(f"\nKLoROS: {response}\n")

            except KeyboardInterrupt:
                print("\n\nKLoROS: Session interrupted.")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"\nError: {e}\n")

    except Exception as e:
        print(f"Failed to initialize KLoROS: {e}")

if __name__ == "__main__":
    main()
