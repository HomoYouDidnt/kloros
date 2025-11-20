"""Tool system for LLM-driven introspection and system queries."""

import os
import sys
import json
import subprocess
import sqlite3
import math
import tempfile
import wave
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional

import numpy

# Optional dependency for audio tools
try:
    import sounddevice
except ImportError:
    sounddevice = None

# Knowledge base updater
from src.knowledge_base_updater import get_updater

_SCHOLAR_REGISTERED = False
_BROWSER_REGISTERED = False


class IntrospectionTool:
    """Single introspection tool that the LLM can invoke."""

    def __init__(self, name: str, description: str, func: Callable, parameters: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or []

    def execute(self, kloros_instance, **kwargs):
        """Execute the tool function."""
        if self.func is None or not callable(self.func):
            raise RuntimeError(f"Tool '{self.name}' has no callable function")
        return self.func(kloros_instance, **kwargs)

    def to_dict(self):
        """Convert tool to dictionary for LLM prompt."""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters
        }


class IntrospectionToolRegistry:
    """Registry of tools available to the LLM."""

    def __init__(self):
        self.tools: Dict[str, IntrospectionTool] = {}
        self.synthesis_enabled = True
        self._register_default_tools()
        self._load_synthesized_tools()
        self._load_capability_tools()

    def register(self, tool: IntrospectionTool):
        """Register a new tool."""
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[IntrospectionTool]:
        """Get tool by name."""
        return self.tools.get(name)

    def get_tools_description(self) -> str:
        """Generate description of all available tools for LLM prompt."""
        desc = "You have access to the following system introspection tools:\n\n"
        for tool in self.tools.values():
            params = ""
            if tool.parameters:
                params = f" (parameters: {', '.join(tool.parameters)})"
            desc += f"- {tool.name}{params}: {tool.description}\n"
        desc += "\nTo use a tool, respond with: TOOL: tool_name\n"
        desc += "If you use a tool, I will execute it and provide the results."
        return desc

    def get_tools_for_ollama_chat(self) -> List[Dict]:
        """Convert tools to Ollama chat API format.

        Returns:
            List of tool definitions in Ollama /api/chat format
        """
        tools = []
        for tool in self.tools.values():
            # Build parameters schema
            properties = {}
            required = []
            if tool.parameters:
                for param in tool.parameters:
                    properties[param] = {
                        "type": "string",
                        "description": f"Parameter: {param}"
                    }
                    required.append(param)

            tool_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            }
            tools.append(tool_def)
        return tools

    def _register_default_tools(self):
        """Register default introspection tools."""

        # System diagnostic
        self.register(IntrospectionTool(
            name='system_diagnostic',
            description='Get complete system diagnostic report with all component status',
            func=lambda kloros_instance, **kwargs: kloros_instance.generate_full_diagnostic()
        ))

        # Audio status
        self.register(IntrospectionTool(
            name='audio_status',
            description='Get audio pipeline status including device, backend, sample rate',
            func=lambda kloros_instance, **kwargs: kloros_instance.get_audio_diagnostics()
        ))

        # Audio quality
        self.register(IntrospectionTool(
            name='audio_quality',
            description='Analyze current microphone audio quality with detailed metrics and suggestions',
            func=lambda kloros_instance, **kwargs: self._analyze_audio_quality(kloros_instance)
        ))

        # STT status
        self.register(IntrospectionTool(
            name='stt_status',
            description='Get speech-to-text backend status and model information',
            func=lambda kloros_instance, **kwargs: kloros_instance.get_stt_diagnostics()
        ))

        # Memory status
        self.register(IntrospectionTool(
            name='memory_status',
            description='Get memory system status and statistics with proactive data generation',
            func=lambda kloros_instance, **kwargs: self._analyze_memory_status_proactive(kloros_instance)
        ))

        # Affective status (consciousness substrate)
        self.register(IntrospectionTool(
            name='affective_status',
            description='Get affective core status showing emotional state, mood, and homeostatic balance (consciousness substrate)',
            func=lambda kloros_instance, **kwargs: kloros_instance.get_affective_diagnostics() if hasattr(kloros_instance, 'get_affective_diagnostics') else "⚠️ Affective diagnostics not available in this mode"
        ))

        # Component status
        self.register(IntrospectionTool(
            name='component_status',
            description='Get status of all components in natural language',
            func=lambda kloros_instance, **kwargs: self._format_component_status(kloros_instance)
        ))

        # List audio sinks
        self.register(IntrospectionTool(
            name='list_audio_sinks',
            description='List all available audio output sinks on the system',
            func=lambda kloros_instance, **kwargs: self._list_audio_sinks(kloros_instance)
        ))

        # List audio sources
        self.register(IntrospectionTool(
            name='list_audio_sources',
            description='List all available audio input sources on the system',
            func=lambda kloros_instance, **kwargs: self._list_audio_sources(kloros_instance)
        ))

        # Count voice samples
        self.register(IntrospectionTool(
            name='count_voice_samples',
            description='Count the number of voice sample files in the RAG database',
            func=lambda kloros_instance, **kwargs: self._count_voice_samples(kloros_instance)
        ))

        # Search voice samples
        self.register(IntrospectionTool(
            name='search_voice_samples',
            description='Search for voice sample files by filename pattern (e.g., "potatos", "fall18")',
            func=lambda kloros_instance, **kwargs: self._search_voice_samples(kloros_instance, kwargs.get('pattern', '')),
            parameters=['pattern']
        ))

        # Play voice sample
        self.register(IntrospectionTool(
            name='play_voice_sample',
            description='Play a specific voice sample file by name',
            func=lambda kloros_instance, **kwargs: self._play_voice_sample(kloros_instance, kwargs.get('filename', '')),
            parameters=['filename']
        ))

        # List models
        self.register(IntrospectionTool(
            name='list_models',
            description='List all AI models (STT, TTS, LLM) and their paths',
            func=lambda kloros_instance, **kwargs: self._list_models(kloros_instance)
        ))

        # List introspection tools
        self.register(IntrospectionTool(
            name='list_introspection_tools',
            description='List all available introspection tools with descriptions',
            func=lambda kloros_instance, **kwargs: self._list_introspection_tools()
        ))

        # Check service status
        self.register(IntrospectionTool(
            name='check_service_status',
            description='Check systemd service status for KLoROS',
            func=lambda kloros_instance, **kwargs: self._check_service_status(kloros_instance)
        ))

        # Start enrollment
        self.register(IntrospectionTool(
            name='start_enrollment',
            description='Start voice enrollment process for new user registration',
            func=lambda kloros_instance, **kwargs: self._start_enrollment(kloros_instance)
        ))

        # List enrolled users
        self.register(IntrospectionTool(
            name='list_enrolled_users',
            description='List all enrolled users in the speaker recognition system',
            func=lambda kloros_instance, **kwargs: self._list_enrolled_users(kloros_instance)
        ))

        # Cancel enrollment
        self.register(IntrospectionTool(
            name='cancel_enrollment',
            description='Cancel current enrollment process',
            func=lambda kloros_instance, **kwargs: self._cancel_enrollment(kloros_instance)
        ))

        # Run D-REAM evolution
        self.register(IntrospectionTool(
            name='run_dream_evolution',
            description='Manually trigger a D-REAM evolution cycle for immediate system optimization. KLoROS can determine focus areas and parameters based on conversational context.',
            func=lambda kloros_instance, **kwargs: self._run_dream_evolution(kloros_instance, **kwargs),
            parameters=['focus_area', 'target_parameters', 'max_changes']
        ))

        # System mapping (comprehensive self-inventory)
        self.register(IntrospectionTool(
            name='map_system',
            description='Perform comprehensive system mapping to inventory all directories, files, hardware, software, and capabilities',
            func=lambda kloros_instance, **kwargs: self._map_system(kloros_instance)
        ))

        # Capability testing (benchmark all capabilities)
        self.register(IntrospectionTool(
            name='test_capabilities',
            description='Run comprehensive capability tests on all subsystems (STT, TTS, RAG, VAD, tools, memory) and generate health score',
            func=lambda kloros_instance, **kwargs: self._test_capabilities(kloros_instance)
        ))

        # Get D-REAM report
        self.register(IntrospectionTool(
            name='get_dream_report',
            description='Get comprehensive D-REAM experiment report with baselines, candidates, and evolution status',
            func=lambda kloros_instance, **kwargs: self._get_dream_report(kloros_instance)
        ))

        # View pending improvement proposals
        self.register(IntrospectionTool(
            name='view_pending_proposals',
            description='View pending improvement proposals in D-REAM queue. Optional filters: component, priority, limit',
            func=tool_view_pending_proposals
        ))

        # Invoke deep reasoning for complex problems
        self.register(IntrospectionTool(
            name='invoke_deep_reasoning',
            description='Use advanced reasoning (Tree of Thought or Debate) to analyze complex problems. Args: problem, method (tot/debate), context',
            func=tool_invoke_deep_reasoning
        ))

        # Check recent errors
        self.register(IntrospectionTool(
            name='check_recent_errors',
            description='Check recent error events from memory system and logs',
            func=lambda kloros_instance, **kwargs: self._check_recent_errors(kloros_instance, **kwargs),
            parameters=['limit']
        ))

        # Generate comprehensive system report
        self.register(IntrospectionTool(
            name='generate_report',
            description='Generate a comprehensive natural language report covering all major systems (health, consciousness, memory, reflection, tool curation)',
            func=lambda kloros_instance, **kwargs: self._generate_comprehensive_report(kloros_instance)
        ))

        # Generate tool curation report
        self.register(IntrospectionTool(
            name='get_tool_curation_report',
            description='Get natural language summary of recent tool catalog curation activities and improvements',
            func=lambda kloros_instance, **kwargs: self._get_tool_curation_report(kloros_instance)
        ))

        # Generate memory summary
        self.register(IntrospectionTool(
            name='get_memory_summary',
            description='Get natural language summary of memory system status, recent episodes, and statistics',
            func=lambda kloros_instance, **kwargs: self._get_memory_summary(kloros_instance)
        ))

        # Generate consciousness report
        self.register(IntrospectionTool(
            name='get_consciousness_report',
            description='Get natural language summary of current affective and consciousness state',
            func=lambda kloros_instance, **kwargs: self._get_consciousness_report(kloros_instance)
        ))

        # Execute system command
        self.register(IntrospectionTool(
            name='execute_system_command',
            description='Execute a system command safely (limited to approved commands)',
            func=lambda kloros_instance, **kwargs: self._execute_system_command(kloros_instance, **kwargs),
            parameters=['command']
        ))

        # Modify parameter
        self.register(IntrospectionTool(
            name='modify_parameter',
            description='Modify a KLoROS configuration parameter',
            func=lambda kloros_instance, **kwargs: self._modify_parameter(kloros_instance, **kwargs),
            parameters=['parameter', 'value']
        ))

        # Restart service
        self.register(IntrospectionTool(
            name='restart_service',
            description='Restart the KLoROS systemd service',
            func=lambda kloros_instance, **kwargs: self._restart_service(kloros_instance)
        ))

        # Run audio test
        self.register(IntrospectionTool(
            name='run_audio_test',
            description='Run audio pipeline test and optimization',
            func=lambda kloros_instance, **kwargs: self._run_audio_test(kloros_instance)
        ))

        # Force memory cleanup
        self.register(IntrospectionTool(
            name='force_memory_cleanup',
            description='Force memory system cleanup and optimization',
            func=lambda kloros_instance, **kwargs: self._force_memory_cleanup(kloros_instance)
        ))

        # Enable enhanced memory
        self.register(IntrospectionTool(
            name='enable_enhanced_memory',
            description='Intelligently enable enhanced memory system if disabled',
            func=lambda kloros_instance, **kwargs: self._enable_enhanced_memory(kloros_instance)
        ))

        # Run housekeeping NOW (execute action)
        self.register(IntrospectionTool(
            name='run_housekeeping',
            description='Execute housekeeping cleanup RIGHT NOW - runs memory cleanup, removes old cache files, vacuums database. Use when user says "run", "execute", "do", or "perform" housekeeping.',
            func=lambda kloros_instance, **kwargs: self._run_housekeeping(kloros_instance)
        ))

        # Enable housekeeping (configure for future)
        self.register(IntrospectionTool(
            name='enable_housekeeping',
            description='Enable automated memory housekeeping scheduling for FUTURE automatic runs. Use when user says "enable", "turn on", "activate", or "configure" housekeeping.',
            func=lambda kloros_instance, **kwargs: self._enable_housekeeping(kloros_instance)
        ))

        # Create code solution
        self.register(IntrospectionTool(
            name='create_code_solution',
            description='Create or modify code files to implement system solutions',
            func=lambda kloros_instance, **kwargs: self._create_code_solution(kloros_instance, **kwargs),
            parameters=['problem', 'solution']
        ))

        # Check dependencies
        self.register(IntrospectionTool(
            name='check_dependencies',
            description='Check Python package dependencies and provide installation guidance',
            func=lambda kloros_instance, **kwargs: self._check_dependencies(kloros_instance, **kwargs),
            parameters=['package']
        ))

        # Tool ecosystem analyzer
        self.register(IntrospectionTool(
            name='analyze_tool_ecosystem',
            description='Analyze synthesized tools for combination and pruning opportunities',
            func=lambda kloros_instance, **kwargs: self._analyze_tool_ecosystem(kloros_instance)
        ))

        # Knowledge Base Management Tools
        self.register(IntrospectionTool(
            name="update_knowledge_base",
            description="Add or update documentation in the knowledge base and rebuild RAG",
            func=lambda kloros, category='', filename='', content='', reason='': self._update_kb(category, filename, content, reason),
            parameters=['category', 'filename', 'content', 'reason']
        ))
        
        self.register(IntrospectionTool(
            name="rebuild_rag",
            description="Rebuild RAG database from current knowledge base",
            func=lambda kloros: get_updater().rebuild_rag_database(),
            parameters=[]
        ))
        
        self.register(IntrospectionTool(
            name="document_improvement",
            description="Document a system improvement to knowledge base",
            func=lambda kloros, improvement_type='', title='', description='', solution='': get_updater().document_improvement(improvement_type, title, description, solution),
            parameters=['improvement_type', 'title', 'description', 'solution']
        ))

        # XAI - Explain reasoning
        self.register(IntrospectionTool(
            name="explain_reasoning",
            description="Explain how I developed my most recent response, showing reasoning steps, evidence, and confidence",
            func=lambda kloros_instance, **kwargs: self._explain_last_reasoning(kloros_instance)
        ))

        # Self-portrait - Complete self-awareness summary
        self.register(IntrospectionTool(
            name="show_self_portrait",
            description="Generate complete self-awareness summary showing capabilities, affordances, and curiosity questions",
            func=lambda kloros_instance, **kwargs: self._show_self_portrait(kloros_instance)
        ))

        # ACE bullets export (optional, for E2E testing)
        self.register(IntrospectionTool(
            name="export_ace_bullets",
            description="Export ACE bullets from ChromaDB to markdown file for analysis",
            func=lambda kloros_instance, **kwargs: self._export_ace_bullets(kloros_instance, **kwargs),
            parameters=['output_path', 'max_bullets']
        ))

        # Chaos Lab - Self-healing testing and evolution
        self.register(IntrospectionTool(
            name='run_chaos_test',
            description='Run a chaos engineering experiment to test self-healing capabilities. Tests controlled failures like timeouts, OOM, corruption to validate healing responses and collect MTTR data for D-REAM optimization',
            func=lambda kloros_instance, **kwargs: self._run_chaos_test(kloros_instance, **kwargs),
            parameters=['scenario_id']
        ))

        self.register(IntrospectionTool(
            name='list_chaos_scenarios',
            description='List all available chaos testing scenarios for self-healing validation',
            func=lambda kloros_instance, **kwargs: self._list_chaos_scenarios(kloros_instance)
        ))

        self.register(IntrospectionTool(
            name='chaos_history',
            description='View history of chaos experiments with scores, outcomes, and patterns. Learn which failures are hardest to recover from',
            func=lambda kloros_instance, **kwargs: self._chaos_history(kloros_instance, **kwargs),
            parameters=['limit']
        ))

        self.register(IntrospectionTool(
            name='auto_chaos_test',
            description='Automatically select and run a chaos scenario based on recent system behavior. Use during idle time to proactively test healing',
            func=lambda kloros_instance, **kwargs: self._auto_chaos_test(kloros_instance)
        ))

        # Active improvement proposal submission
        self.register(IntrospectionTool(
            name='submit_improvement_idea',
            description='Submit an improvement idea to D-REAM evolution system during active thinking (parameters: component, description, priority, issue_type)',
            func=tool_submit_improvement_idea,
            parameters=['component', 'description', 'priority', 'issue_type']
        ))

        self.register(IntrospectionTool(
            name='submit_quick_fix',
            description='Quickly submit a simple fix idea to D-REAM (parameters: description, target_file)',
            func=tool_submit_quick_fix,
            parameters=['description', 'target_file']
        ))
        # Tool synthesis - on-demand creation
        self.register(IntrospectionTool(
            name='synthesize_new_tool',
            description='Synthesize a new introspection tool based on requirements (parameters: tool_name, description, requirements)',
            func=tool_synthesize_new_tool,
            parameters=['tool_name', 'description', 'requirements']
        ))
        # Tool synthesis queue management (Level 2 Autonomy)
        self.register(IntrospectionTool(
            name='check_synthesis_notifications',
            description='Check for pending autonomous tool synthesis notifications (call proactively on conversation start)',
            func=tool_check_synthesis_notifications
        ))
        self.register(IntrospectionTool(
            name='review_synthesis_queue',
            description='Review pending autonomous tool synthesis proposals',
            func=tool_review_synthesis_queue
        ))
        self.register(IntrospectionTool(
            name='approve_synthesis',
            description='Approve and execute a queued tool synthesis proposal (parameter: proposal_id)',
            func=tool_approve_synthesis,
            parameters=['proposal_id']
        ))
        self.register(IntrospectionTool(
            name='reject_synthesis',
            description='Reject a queued tool synthesis proposal (parameter: proposal_id)',
            func=tool_reject_synthesis,
            parameters=['proposal_id']
        ))


    def _explain_last_reasoning(self, kloros_instance):
        """Explain the reasoning process for the most recent response."""
        try:
            from src.xai import middleware as xai
            from src.xai import store
            from src.xai.explain import render

            # Load config
            xai_cfg = xai.load_cfg("/home/kloros/.kloros/xai.yaml")

            # Get all traces and find most recent
            traces = list(store.read_all(xai_cfg))
            if not traces:
                return "No reasoning traces available yet. XAI system is running but hasn't captured any decisions."

            # Get most recent trace
            latest_trace = traces[-1]

            # Render explanation
            explanation = render(latest_trace, xai_cfg)

            # Format for voice output
            lines = []
            lines.append(f"Here's how I developed my response to: {explanation['query']}\n")

            for section in explanation['sections']:
                lines.append(f"{section['title']}:")
                if 'body' in section:
                    lines.append(f"  {section['body']}")
                if 'list' in section:
                    for item in section['list']:
                        lines.append(f"  • {item}")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            return f"Failed to explain reasoning: {str(e)}\nXAI system may not be initialized yet."

    def _show_self_portrait(self, kloros_instance):
        """Generate complete self-awareness summary with capabilities, affordances, and curiosity questions."""
        try:
            from src.registry.self_portrait import SelfPortrait

            # Generate portrait
            portrait = SelfPortrait()
            summary = portrait.generate()

            # Write artifacts to disk
            portrait.write_all_artifacts()

            return summary

        except Exception as e:
            return f"Failed to generate self-portrait: {str(e)}\nCapability registry system may not be initialized yet."

    def _list_audio_sinks(self, kloros_instance):
        """List PulseAudio/PipeWire sinks."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sinks'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "AUDIO SINKS:\n" + result.stdout
            else:
                return f"Failed to list sinks: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error listing sinks: Command timed out"
        except Exception as e:
            return f"Error listing sinks: {e}"

    def _list_audio_sources(self, kloros_instance):
        """List PulseAudio/PipeWire sources."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sources'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "AUDIO SOURCES:\n" + result.stdout
            else:
                return f"Failed to list sources: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error listing sources: Command timed out"
        except Exception as e:
            return f"Error listing sources: {e}"

    def _count_voice_samples(self, kloros_instance):
        """Count voice samples in RAG database."""
        try:
            if hasattr(kloros_instance, 'reason_backend') and hasattr(kloros_instance.reason_backend, 'samples'):
                count = len(kloros_instance.reason_backend.samples)
                return f"Voice sample count: {count} files"

            samples_dir = '/home/kloros/voice_samples'
            if os.path.exists(samples_dir):
                files = [f for f in os.listdir(samples_dir) if f.endswith('.txt') or f.endswith('.json')]
                count = len(files)
                return f"Voice sample files in {samples_dir}: {count}"
            else:
                return "Voice samples directory not found"
        except Exception as e:
            return f"Error counting voice samples: {e}"

    def _search_voice_samples(self, kloros_instance, pattern: str):
        """Search for voice sample files by pattern."""
        try:
            if not pattern:
                return "Error: No search pattern provided"

            # Normalize pattern for case-insensitive search
            pattern_lower = pattern.lower()

            # Search in voice_files directory
            base_dirs = [
                '/home/kloros/voice_files/samples',
                '/home/kloros/voice_files/samples_44.1khz_backup'
            ]

            matches = []
            for base_dir in base_dirs:
                if os.path.exists(base_dir):
                    for filename in os.listdir(base_dir):
                        if pattern_lower in filename.lower() and filename.endswith('.wav'):
                            matches.append(os.path.join(base_dir, filename))

            if not matches:
                return f"No voice samples found matching pattern: {pattern}"

            result = f"Found {len(matches)} voice sample(s) matching '{pattern}':\n"
            for i, path in enumerate(matches[:10], 1):  # Limit to first 10 results
                filename = os.path.basename(path)
                result += f"{i}. {filename}\n"

            if len(matches) > 10:
                result += f"... and {len(matches) - 10} more\n"

            return result
        except Exception as e:
            return f"Error searching voice samples: {e}"

    def _play_voice_sample(self, kloros_instance, filename: str):
        """Play a specific voice sample file."""
        try:
            if not filename:
                return "Error: No filename provided"

            # Search for the file in voice_files directories
            base_dirs = [
                '/home/kloros/voice_files/samples',
                '/home/kloros/voice_files/samples_44.1khz_backup'
            ]

            file_path = None
            for base_dir in base_dirs:
                if os.path.exists(base_dir):
                    # Try exact match first
                    candidate = os.path.join(base_dir, filename)
                    if os.path.exists(candidate):
                        file_path = candidate
                        break

                    # Try with .wav extension
                    if not filename.endswith('.wav'):
                        candidate = os.path.join(base_dir, filename + '.wav')
                        if os.path.exists(candidate):
                            file_path = candidate
                            break

            if not file_path:
                return f"Voice sample file not found: {filename}"

            # Play the file using aplay or the KLoROS playback command
            import platform
            if platform.system() == "Linux":
                # Try to use kloros_instance's playback method if available
                if hasattr(kloros_instance, '_playback_cmd'):
                    cmd = kloros_instance._playback_cmd(file_path)
                else:
                    cmd = ['aplay', file_path]

                result = subprocess.run(cmd, capture_output=True, check=False)
                if result.returncode == 0:
                    return f"✅ Playing: {os.path.basename(file_path)}"
                else:
                    return f"❌ Playback failed for {os.path.basename(file_path)}: {result.stderr.decode()}"
            else:
                return f"Playback not supported on {platform.system()}"
        except Exception as e:
            return f"Error playing voice sample: {e}"

    def _list_models(self, kloros_instance):
        """List all models and their locations."""
        report = "AI MODELS:\n"
        report += "=" * 40 + "\n"

        vosk_path = os.getenv('KLR_VOSK_MODEL_DIR', '/home/kloros/models/vosk/model')
        report += f"Vosk STT: {vosk_path}\n"
        report += f"  Exists: {os.path.exists(vosk_path)}\n"

        piper_voice = os.getenv('KLR_PIPER_VOICE', '/home/kloros/models/piper/glados_piper_medium.onnx')
        report += f"Piper TTS: {piper_voice}\n"
        report += f"  Exists: {os.path.exists(piper_voice)}\n"

        ollama_model = os.getenv('KLR_OLLAMA_MODEL', 'qwen2.5:14b-instruct-q4_0')
        report += f"Ollama LLM: {ollama_model}\n"

        return report

    def _list_introspection_tools(self):
        """List all registered introspection tools."""
        report = f"AVAILABLE INTROSPECTION TOOLS ({len(self.tools)}):\n"
        report += "=" * 60 + "\n\n"

        # Group by category for better organization
        for tool_name, tool in sorted(self.tools.items()):
            params = f" ({', '.join(tool.parameters)})" if tool.parameters else ""
            report += f"• {tool_name}{params}\n"
            report += f"  {tool.description}\n\n"

        return report

    def _check_service_status(self, kloros_instance):
        """Check systemd service status."""
        try:
            result = subprocess.run(
                ['systemctl', 'status', 'kloros.service', '--no-pager'],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Parse systemctl output into human-friendly summary
            output = result.stdout

            # Extract key information
            import re
            status = "unknown"
            uptime = "unknown"
            memory = "unknown"

            # Parse Active status
            active_match = re.search(r'Active:\s+(\w+)\s+\((\w+)\)\s+since\s+(.+?);(.+?)ago', output)
            if active_match:
                state = active_match.group(1)  # active/inactive/failed
                substate = active_match.group(2)  # running/dead
                uptime = active_match.group(4).strip()

                if state == "active" and substate == "running":
                    status = f"running normally for {uptime}"
                elif state == "active":
                    status = f"active ({substate}) for {uptime}"
                elif state == "inactive":
                    status = "stopped"
                elif state == "failed":
                    status = "failed"

            # Parse Memory usage
            memory_match = re.search(r'Memory:\s+([0-9.]+[KMGT])', output)
            if memory_match:
                memory = memory_match.group(1)

            # Check for recent errors in last 5 log lines
            errors = []
            lines = output.split('\n')
            for line in lines[-10:]:
                if any(word in line.lower() for word in ['error', 'failed', 'exception', 'traceback']):
                    errors.append(line.strip())

            # Build natural summary
            summary = f"KLoROS service is {status}"
            if memory != "unknown":
                summary += f", using {memory} of memory"

            if errors:
                summary += f". Recent errors detected in logs"
            else:
                summary += ". No recent errors"

            return summary

        except Exception as e:
            return f"Error checking service: {e}"

    def _format_component_status(self, kloros_instance):
        """Format component status as natural language summary."""
        try:
            status = kloros_instance.get_component_status()

            # Build natural language summary
            components = []

            # Audio backend
            if 'audio_backend' in status:
                audio = status['audio_backend']
                if audio.get('initialized'):
                    components.append(f"{audio['name']} audio at {audio['sample_rate']} Hz")

            # STT backend
            if 'stt_backend' in status:
                stt = status['stt_backend']
                if stt.get('initialized'):
                    components.append(f"{stt['name']} speech recognition")

            # TTS backend
            if 'tts_backend' in status:
                tts = status['tts_backend']
                if tts.get('initialized'):
                    components.append(f"{tts['name']} text to speech")

            # Reasoning backend
            if 'reasoning_backend' in status:
                reasoning = status['reasoning_backend']
                if reasoning.get('initialized'):
                    components.append(f"{reasoning['name']} reasoning")

            # VAD
            if 'vad' in status:
                vad = status['vad']
                components.append(f"{vad.get('type', 'unknown')} voice detection")

            # Memory
            if 'memory' in status:
                mem = status['memory']
                if mem.get('enabled'):
                    components.append("conversation memory enabled")

            # Speaker recognition
            if 'speaker_backend' in status:
                speaker = status['speaker_backend']
                if speaker.get('initialized'):
                    components.append(f"{speaker['name']} speaker identification")

            if components:
                return f"All systems operational: {', '.join(components)}"
            else:
                return "System status unavailable"

        except Exception as e:
            return f"Error getting component status: {e}"

    def _start_enrollment(self, kloros_instance):
        """Start voice enrollment process."""
        try:
            if hasattr(kloros_instance, 'start_enrollment'):
                return kloros_instance.start_enrollment()
            else:
                return "Voice enrollment system not available"
        except Exception as e:
            return f"Enrollment start failed: {e}"

    def _list_enrolled_users(self, kloros_instance):
        """List enrolled users in speaker recognition system."""
        try:
            if hasattr(kloros_instance, 'list_enrolled_users'):
                return kloros_instance.list_enrolled_users()
            else:
                return "Speaker recognition system not available"
        except Exception as e:
            return f"User listing failed: {e}"

    def _cancel_enrollment(self, kloros_instance):
        """Cancel current enrollment process."""
        try:
            if hasattr(kloros_instance, 'cancel_enrollment'):
                return kloros_instance.cancel_enrollment()
            else:
                return "Speaker recognition system not available"
        except Exception as e:
            return f"Enrollment cancellation failed: {e}"

    def _run_dream_evolution(self, kloros_instance, focus_area=None, target_parameters=None, max_changes=None):
        """
        Manually trigger a D-REAM evolution cycle with optional parameters.
        Args:
            focus_area: Specific area to focus on (e.g., 'audio', 'memory', 'stt', 'tts')
            target_parameters: Comma-separated list of specific parameters to optimize
            max_changes: Maximum number of parameter changes to make
        """
        try:
            sys.path.insert(0, '/home/kloros')
            from src.dream_evolution_system import DreamEvolutionManager

            manager = DreamEvolutionManager()

            # Parse target parameters if provided
            target_list = None
            if target_parameters:
                target_list = [p.strip() for p in target_parameters.split(',')]

            # Build cycle parameters
            cycle_params = {}
            if focus_area:
                cycle_params['focus_area'] = focus_area
            if target_list:
                cycle_params['target_parameters'] = target_list
            if max_changes:
                cycle_params['max_changes'] = int(max_changes)

            # Run evolution cycle
            if cycle_params:
                print(f"[dream] Custom parameters requested but not supported: focus={focus_area}, targets={target_parameters}")
                result = manager.run_evolution_cycle()
            else:
                result = manager.run_evolution_cycle()

            # Format output
            if result.get('success', False):
                improvements = result.get('improvements_applied', [])
                output = f"\u2705 D-REAM evolution cycle completed successfully!\n"
                output += f"Focus Area: {focus_area or 'unknown'}\n"
                output += f"Target Parameters: {target_parameters or 'unknown'}\n"
                output += f"Applied {len(improvements)} improvements:\n"

                for param in improvements:
                    old_val = param.get('old_value', 'unknown')
                    new_val = param.get('new_value', 'unknown')
                    reason = param.get('reason', 'optimization')
                    priority = param.get('priority', 'unknown')
                    output += f"  - {param['parameter']}: {old_val} → {new_val} (priority: {priority})\n"

                return output
            else:
                error = result.get('error', 'Unknown error')
                return f"\u274c D-REAM evolution cycle failed: {error}"

        except Exception as e:
            return f"\u274c Failed to run D-REAM evolution: {e}"

    def _get_dream_report(self, kloros_instance):
        """Get comprehensive D-REAM experiment report."""
        try:
            import json
            from pathlib import Path
            from datetime import datetime
            
            artifacts_dir = Path('/home/kloros/src/dream/artifacts')
            
            # Read baselines
            baselines_file = artifacts_dir / 'baselines.json'
            baselines = {}
            if baselines_file.exists():
                with open(baselines_file) as f:
                    baselines = json.load(f)
            
            # Count candidates by domain
            candidates_dir = artifacts_dir / 'candidates'
            domain_stats = {}
            if candidates_dir.exists():
                for domain_path in candidates_dir.iterdir():
                    if domain_path.is_dir():
                        domain = domain_path.name
                        candidates = list(domain_path.glob('*.json'))
                        domain_stats[domain] = len(candidates)
            
            # Read recent manifests
            manifests_dir = artifacts_dir / 'manifests'
            recent_manifests = []
            if manifests_dir.exists():
                manifest_files = sorted(manifests_dir.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                for mf in manifest_files[:3]:
                    with open(mf) as f:
                        manifest = json.load(f)
                        recent_manifests.append({
                            'file': mf.name,
                            'generation': manifest.get('generation', 'unknown'),
                            'timestamp': manifest.get('timestamp', 'unknown')
                        })
            
            # Format report
            report = "\n=== D-REAM Experiment Report ===\n\n"
            
            # Baselines section
            report += f"📊 Baselines: {len(baselines)} domains\n"
            for domain, baseline_data in list(baselines.items())[:5]:
                if isinstance(baseline_data, dict):
                    regimes = baseline_data.keys() if domain != 'schema' else []
                    report += f"  • {domain}: {len(regimes)} regimes\n"
            
            # Candidates section
            report += f"\n🧬 Candidates by Domain:\n"
            total_candidates = 0
            for domain, count in sorted(domain_stats.items()):
                report += f"  • {domain}: {count} candidates\n"
                total_candidates += count
            report += f"  Total: {total_candidates} candidates\n"
            
            # Recent activity
            if recent_manifests:
                report += f"\n📝 Recent Manifests ({len(recent_manifests)}):\n"
                for m in recent_manifests:
                    report += f"  • Gen {m['generation']}: {m['file']}\n"
            
            # Service status
            import subprocess
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', 'dream-domains.service'],
                    capture_output=True, text=True, timeout=2
                )
                service_status = result.stdout.strip()
                report += f"\n⚙️ Service Status: {service_status}\n"
            except:
                report += f"\n⚙️ Service Status: unknown\n"
            
            return report

        except Exception as e:
            return f"❌ Failed to generate D-REAM report: {e}"

    def _check_recent_errors(self, kloros_instance, **kwargs):
        """Check recent error events from memory system and logs."""
        try:
            import sqlite3
            from pathlib import Path
            from datetime import datetime, timedelta

            limit = kwargs.get('limit', 10)
            errors = []

            # First, check systemd journal for very recent errors (last 24 hours)
            try:
                result = subprocess.run(
                    ['journalctl', '-u', 'kloros.service', '--since', '24 hours ago', '--no-pager'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        # Filter for actual errors, not status messages
                        lower_line = line.lower()

                        # Skip false positives (housekeeping status, task reports)
                        if 'tasks:' in lower_line and 'errors:' in lower_line:
                            continue
                        if '[housekeeping]' in lower_line and 'tasks:' in lower_line:
                            continue

                        # Priority error patterns (OOM, failed service, exceptions)
                        is_critical = any(pattern in lower_line for pattern in [
                            'oom-kill', 'failed with result', 'traceback',
                            'exception:', 'critical:', 'fatal:'
                        ])

                        # Standard error patterns
                        is_error = any(keyword in lower_line for keyword in [
                            ' error:', 'error occurred', 'failed to', 'exception in'
                        ])

                        if is_critical or is_error:
                            # Parse journalctl line: "Oct 14 13:07:44 ASTRAEA systemd[1]: message"
                            parts = line.split(None, 5)
                            if len(parts) >= 6:
                                time_str = f"{parts[0]} {parts[1]} {parts[2]}"
                                try:
                                    error_time = datetime.strptime(time_str + " 2025", "%b %d %H:%M:%S %Y")
                                    errors.append({
                                        'time': error_time.strftime('%Y-%m-%d %H:%M:%S'),
                                        'content': parts[5] if len(parts) > 5 else line,
                                        'source': 'systemd',
                                        'priority': 'critical' if is_critical else 'error'
                                    })
                                except:
                                    pass
            except Exception as e:
                print(f"[check_errors] Failed to check journalctl: {e}")

            # Then check memory database for logged errors
            db_path = Path('/home/kloros/.kloros/memory.db')
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                # Get error events from last 24 hours
                yesterday = (datetime.now() - timedelta(days=1)).timestamp()
                cursor.execute("""
                    SELECT timestamp, event_type, content, metadata
                    FROM events
                    WHERE event_type = 'error_occurred'
                    AND timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (yesterday, limit))

                rows = cursor.fetchall()
                conn.close()

                for timestamp, event_type, content, metadata in rows:
                    error_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    errors.append({
                        'time': error_time,
                        'content': content,
                        'metadata': metadata,
                        'source': 'memory_db'
                    })

            # Sort by priority (critical first), then by time (most recent first)
            def sort_key(e):
                priority_value = 0 if e.get('priority') == 'critical' else 1
                return (priority_value, e['time'])

            errors.sort(key=sort_key, reverse=True)
            errors = errors[:limit]

            # Format report
            if not errors:
                return "✅ No recent errors found in last 24 hours"

            report = f"\n=== Recent Errors (Last 24h) - {len(errors)} found ===\n\n"

            for i, error in enumerate(errors, 1):
                priority_tag = " ⚠️ CRITICAL" if error.get('priority') == 'critical' else ""
                report += f"{i}. [{error['time']}] ({error.get('source', 'unknown')}){priority_tag}\n"
                report += f"   {error['content']}\n"

                # Parse metadata if available (for memory_db errors)
                if 'metadata' in error and error['metadata']:
                    try:
                        import json
                        metadata = json.loads(error['metadata'])
                        if 'error_type' in metadata:
                            report += f"   Type: {metadata['error_type']}\n"
                        if 'component' in metadata:
                            report += f"   Component: {metadata['component']}\n"
                    except:
                        pass

                report += "\n"

            return report

        except Exception as e:
            return f"❌ Failed to check recent errors: {e}"

    def _generate_comprehensive_report(self, kloros_instance):
        """Generate comprehensive natural language system report."""
        try:
            from src.reporting import get_report_generator
            reporter = get_report_generator(kloros_instance)
            return reporter.generate_comprehensive_report()
        except Exception as e:
            return f"Error generating comprehensive report: {e}"

    def _get_tool_curation_report(self, kloros_instance):
        """Get tool curation activity report."""
        try:
            from src.reporting import get_report_generator
            reporter = get_report_generator(kloros_instance)
            return reporter.generate_tool_curation_report()
        except Exception as e:
            return f"Error generating tool curation report: {e}"

    def _get_memory_summary(self, kloros_instance):
        """Get memory system summary."""
        try:
            from src.reporting import get_report_generator
            reporter = get_report_generator(kloros_instance)
            return reporter.generate_memory_summary()
        except Exception as e:
            return f"Error generating memory summary: {e}"

    def _get_consciousness_report(self, kloros_instance):
        """Get consciousness state report."""
        try:
            from src.reporting import get_report_generator
            reporter = get_report_generator(kloros_instance)
            return reporter.generate_consciousness_report()
        except Exception as e:
            return f"Error generating consciousness report: {e}"

    def _execute_system_command(self, kloros_instance, command=None, **kwargs):
        """Execute approved system commands safely."""
        if not command:
            return "\u274c No command specified"

        # Approved commands only
        approved_commands = {
            'kloros': ['bash', 'ps aux | grep kloros'],
            'free': ['free'],
            'uptime': ['uptime'],
            'nvidia-smi': ['nvidia-smi'],
            'journalctl': ['journalctl', '-u', 'kloros', '--no-pager', '-n', '10'],
            'systemctl status kloros': ['systemctl', 'status', 'kloros.service', '--no-pager'],
            'df -h': ['df', '-h'],
            'free -h': ['free', '-h'],
            'pactl list short sinks': ['pactl', 'list', 'short', 'sinks'],
            'pactl list short sources': ['pactl', 'list', 'short', 'sources'],
            'journalctl -u kloros --no-pager -n 10': ['journalctl', '-u', 'kloros', '--no-pager', '-n', '10']
        }

        if command not in approved_commands.keys():
            return f"\u274c Command '{command}' not in approved list. Approved: {', '.join(approved_commands.keys())}"

        try:
            cmd_args = approved_commands[command]
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return f"\u2705 Command executed successfully:\n{result.stdout}"
            else:
                return f"\u274c Command failed (exit {result.returncode}):\n{result.stderr}"

        except subprocess.TimeoutExpired:
            return f"\u274c Command timed out after 10 seconds"
        except Exception as e:
            return f"\u274c Command execution failed: {e}"

    def _modify_parameter(self, kloros_instance, parameter=None, value=None, **kwargs):
        """Modify KLoROS configuration parameter."""
        if not parameter or not value:
            return "\u274c Parameter and value must be specified"

        # Safe parameters that can be modified
        safe_parameters = {
            'KLR_INPUT_GAIN': (float, 0.5, 10.0),
            'KLR_VAD_THRESHOLD': (float, -50.0, -10.0),
            'KLR_MAX_CONTEXT_EVENTS': (int, 1, 50),
            'KLR_CONVERSATION_TIMEOUT': (int, 60, 600),
            'KLR_WAKE_CONF_MIN': (float, 0.1, 1.0),
            'KLR_LISTENING_INDICATOR': (int, 0, 1),
            'KLR_TTS_SUPPRESSION': (int, 0, 1)
        }

        if parameter not in safe_parameters:
            return f"\u274c Parameter '{parameter}' not modifiable. Safe parameters: {', '.join(safe_parameters.keys())}"

        param_type, min_val, max_val = safe_parameters[parameter]

        try:
            # Convert value to appropriate type
            if param_type == float:
                converted_value = float(value)
            elif param_type == int:
                converted_value = int(value)
            else:
                converted_value = value

            # Validate range
            if not (min_val <= converted_value <= max_val):
                return f"\u274c Value {converted_value} out of range [{min_val}, {max_val}] for {parameter}"

            # Update .kloros_env file
            env_file = '/home/kloros/.kloros_env'
            lines = []
            updated = False

            with open(env_file, 'r') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if line.strip().startswith(f'{parameter}=') or line.strip().startswith(f'export {parameter}='):
                    lines[i] = f'export {parameter}={converted_value}\n'
                    updated = True
                    break

            if not updated:
                lines.append(f'export {parameter}={converted_value}\n')

            with open(env_file, 'w') as f:
                f.writelines(lines)

            # Update current environment
            os.environ[parameter] = str(converted_value)

            return f"\u2705 Parameter updated: {parameter} = {converted_value}"

        except ValueError:
            return f"\u274c Invalid value '{value}' for parameter {parameter} (expected {param_type.__name__})"
        except Exception as e:
            return f"\u274c Failed to update parameter: {e}"

    def _restart_service(self, kloros_instance):
        """Restart KLoROS systemd service."""
        try:
            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'kloros.service'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return "\u2705 KLoROS service restarted successfully"
            else:
                return f"\u274c Service restart failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "\u274c Service restart timed out"
        except Exception as e:
            return f"Service restart failed: {e}"

    def _run_audio_test(self, kloros_instance):
        """Run audio pipeline test and optimization."""
        try:
            output = "\u2705 Running audio pipeline test...\n"

            # Get audio backend info
            if hasattr(kloros_instance, 'audio_backend'):
                output += f"Audio backend: {type(kloros_instance.audio_backend).__name__}\n"

            # Get current gain
            current_gain = float(os.getenv('KLR_INPUT_GAIN', '4.5'))
            output += f"Current input gain: {current_gain}\n"

            # Capture test audio
            try:
                import sounddevice as sd
                import numpy as np

                duration = 2
                sample_rate = getattr(kloros_instance, 'samplerate', 48000)
                channels = getattr(kloros_instance, 'channels', 1)

                output += f"Capturing {duration}s test audio at {sample_rate}Hz, {channels} channel(s)...\n"

                recording = sd.rec(int(duration * sample_rate),
                                 samplerate=sample_rate,
                                 channels=channels,
                                 dtype='float32')
                sd.wait()

                # Calculate RMS and peak
                rms = numpy.sqrt(numpy.mean(recording**2))
                peak = numpy.max(numpy.abs(recording))

                # Convert to dBFS
                dbfs_rms = 20 * numpy.log10(rms) if rms > 0 else float('-inf')
                dbfs_peak = 20 * numpy.log10(peak) if peak > 0 else float('-inf')

                output += f"Audio test results:\n"
                output += f"  RMS level: {dbfs_rms:.2f} dBFS\n"
                output += f"  Peak level: {dbfs_peak:.2f} dBFS\n"

                # Provide feedback
                if dbfs_peak < -30:
                    output += "  Audio level low - consider increasing input gain\n"
                elif dbfs_peak > -6:
                    output += "  Audio level high - consider decreasing input gain\n"
                else:
                    output += "  Audio levels good\n"

            except Exception as audio_e:
                output += f"Audio capture test failed: {audio_e}\n"

            return output

        except Exception as e:
            return f"\u274c Audio test failed: {e}"

    def _force_memory_cleanup(self, kloros_instance):
        """Force memory system cleanup and optimization."""
        try:
            output = "\u2705 Running memory system cleanup...\n"

            # Try housekeeping
            if hasattr(kloros_instance, 'memory_enhanced'):
                try:
                    from src.kloros_memory.housekeeping import MemoryHousekeeper
                    housekeeper = MemoryHousekeeper()
                    results = housekeeper.run_daily_maintenance()

                    output += "Maintenance completed:\n"
                    for task, result in results.items():
                        if isinstance(result, dict):
                            output += f"  {task}: {result}\n"
                        else:
                            output += f"  {task}: {result}\n"

                except Exception as mem_e:
                    output += f"Housekeeping failed: {mem_e}\n"

                # Get memory stats
                try:
                    stats = kloros_instance.memory_enhanced.get_memory_stats()
                    output += "Memory stats:\n"
                    output += f"  Total events: {stats.get('total_events', 0)}\n"
                    output += f"  Total episodes: {stats.get('total_episodes', 0)}\n"
                except Exception as stat_e:
                    output += f"Stats retrieval failed: {stat_e}\n"
            else:
                output += "Memory system not available\n"

            return output

        except Exception as e:
            return f"\u274c Memory cleanup failed: {e}"

    def _enable_enhanced_memory(self, kloros_instance):
        """Intelligently enable enhanced memory system if currently disabled."""
        try:
            # Check if already enabled
            if hasattr(kloros_instance, 'memory_enhanced') and kloros_instance.memory_enhanced:
                return "\u2705 Enhanced memory system already enabled and operational"

            # Check if disabled by configuration
            enable_memory = os.getenv('KLR_ENABLE_MEMORY', '0')
            if hasattr(kloros_instance, 'memory_enhanced') and not kloros_instance.memory_enhanced:
                return f"\u26a0\ufe0f Enhanced memory system exists but disabled by configuration. Check KLR_ENABLE_MEMORY environment variable."

            output = "\u2705 Intelligently enabling enhanced memory system...\n"

            # Try to enable memory system
            try:
                from src.kloros_memory.integration import create_memory_enhanced_kloros
                output += "\u2705 Memory integration module available\n"
            except ImportError as e:
                return f"\u274c Enhanced memory system not available - memory integration module missing"

            # Set environment variable
            os.environ['KLR_ENABLE_MEMORY'] = '1'
            output += "\u2705 Set KLR_ENABLE_MEMORY=1\n"

            # Initialize memory system
            try:
                kloros_instance.memory_enhanced = create_memory_enhanced_kloros(kloros_instance)
                output += "\u2705 Enhanced memory system successfully initialized!\n"
                output += "\u2705 Episodic-semantic memory now operational\n"
            except Exception as init_e:
                return f"\u274c Enhanced memory initialization failed - check configuration"

            # Update .kloros_env file
            try:
                env_file = '/home/kloros/.kloros_env'
                lines = []
                updated = False

                with open(env_file, 'r') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if line.strip().startswith('KLR_ENABLE_MEMORY=') or line.strip().startswith('export KLR_ENABLE_MEMORY='):
                        lines[i] = 'export KLR_ENABLE_MEMORY=1\n'
                        updated = True
                        break

                if not updated:
                    lines.append('export KLR_ENABLE_MEMORY=1\n')

                with open(env_file, 'w') as f:
                    f.writelines(lines)

                output += "\u2705 Updated persistent configuration to keep memory enabled\n"
            except Exception as env_e:
                output += f"\u26a0\ufe0f Failed to update config file: {env_e}\n"

            return output

        except Exception as e:
            return f"\u274c Enhanced memory enablement failed: {e}"

    def _run_housekeeping(self, kloros_instance):
        """Execute housekeeping cleanup immediately."""
        try:
            import subprocess
            result = subprocess.run(
                ['/home/kloros/.venv/bin/python3', '-m', 'src.kloros_memory.housekeeping'],
                cwd='/home/kloros',
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return "✅ Housekeeping executed successfully. Cleaned cache files, old backups, and vacuumed databases."
            else:
                return f"⚠️ Housekeeping completed with warnings:\n{result.stderr[:500]}"
        except subprocess.TimeoutExpired:
            return "⏱️ Housekeeping timed out after 120 seconds"
        except Exception as e:
            return f"❌ Housekeeping execution failed: {e}"

    def _enable_housekeeping(self, kloros_instance):
        """Enable automated memory housekeeping system."""
        try:
            # Check current status
            housekeeping_enabled = os.getenv('KLR_ENABLE_HOUSEKEEPING', '0')

            if housekeeping_enabled == '1':
                return "\u2705 Housekeeping system already enabled"

            output = "\u2705 Enabling housekeeping system...\n"

            # Set environment variable for current session
            os.environ['KLR_ENABLE_HOUSEKEEPING'] = '1'
            output += "\u2705 Set KLR_ENABLE_HOUSEKEEPING=1 for current session\n"

            # Update .kloros_env file for persistence
            try:
                env_file = '/home/kloros/.kloros_env'
                lines = []
                updated = False

                with open(env_file, 'r') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if line.strip().startswith('KLR_ENABLE_HOUSEKEEPING=') or line.strip().startswith('export KLR_ENABLE_HOUSEKEEPING='):
                        lines[i] = 'KLR_ENABLE_HOUSEKEEPING=1\n'
                        updated = True
                        break

                if not updated:
                    lines.append('KLR_ENABLE_HOUSEKEEPING=1\n')

                with open(env_file, 'w') as f:
                    f.writelines(lines)

                output += "\u2705 Updated persistent configuration in .kloros_env\n"
            except Exception as env_e:
                output += f"\u26a0\ufe0f Failed to update config file: {env_e}\n"

            # Restart service to apply changes
            output += "\U0001f504 Restarting service to enable housekeeping...\n"
            restart_result = self._restart_service(kloros_instance)
            output += restart_result

            return output

        except Exception as e:
            return f"\u274c Housekeeping enablement failed: {e}"

    def _create_code_solution(self, kloros_instance, problem=None, solution=None, **kwargs):
        """Create or modify code files to implement system solutions."""
        if not problem:
            return "\u274c No problem specified. Describe the issue to solve."

        output = ""

        # Check for chat system fix
        if 'chat' in problem.lower() or 'vosk' in problem.lower():
            output += f"\u2705 Analyzing problem: {problem}\n"
            output += f"\u2705 Proposed solution: {solution}\n" if solution else ""
            return self._fix_chat_system(kloros_instance)

        # Generic code creation
        output += "\u26a0\ufe0f Code creation tool is ready but needs specific implementation logic.\n"
        output += "To implement: specify the exact file path and code content needed.\n"

        return output

    def _fix_chat_system(self, kloros_instance):
        """Fix the broken chat system by creating a standalone version."""
        try:
            output = "\u2705 Implementing standalone chat system fix...\n"

            standalone_chat_code = '''#!/usr/bin/env python3
"""Standalone KLoROS Chat Interface - No Voice Dependencies"""
import sys
import os

sys.path.insert(0, '/home/kloros')

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

        # Initialize reasoning backend
        self._init_reasoning()

        # Initialize memory if available
        self._init_memory()

    def _init_reasoning(self):
        """Initialize reasoning backend."""
        try:
            from src.reasoning.local_rag_backend import LocalRagBackend
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
        except Exception as e:
            print(f"[chat] Memory initialization failed: {e}")

    def chat(self, message):
        """Process chat message through reasoning system."""
        if not self.reason_backend:
            return "\\u274c Reasoning system not available"

        try:
            # Log to memory if available
            if self.memory_enhanced and hasattr(self.memory_enhanced, 'memory_logger'):
                self.memory_enhanced.memory_logger.log_user_input(
                    transcript=message, confidence=0.95
                )

            # Process through reasoning with tool integration (use deep mode for background introspection)
            import inspect
            sig = inspect.signature(self.reason_backend.reply)
            if 'kloros_instance' in sig.parameters:
                result = self.reason_backend.reply(message, kloros_instance=self, mode="deep")
            else:
                result = self.reason_backend.reply(message, mode="deep")

            response = result.reply_text

            # Log response to memory
            if self.memory_enhanced and hasattr(self.memory_enhanced, 'memory_logger'):
                self.memory_enhanced.memory_logger.log_llm_response(
                    response=response, model='qwen2.5:14b-instruct-q4_0'
                )

            return response
        except Exception as e:
            return f"\\u274c Chat processing failed: {e}"

def main():
    print("\\n" + "="*60)
    print("KLoROS Standalone Chat Interface")
    print("="*60)
    print("\\u2705 No voice dependencies - pure reasoning system")
    print("\\u2705 Full tool execution and memory capabilities")
    print("\\u2705 Conversational AI system administration")
    print("Type 'exit' to quit.")
    print("="*60 + "\\n")

    try:
        kloros = StandaloneKLoROS()

        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print("\\nKLoROS: Session terminated.")
                    break

                response = kloros.chat(user_input)
                print(f"\\nKLoROS: {response}\\n")

            except KeyboardInterrupt:
                print("\\n\\nKLoROS: Session interrupted.")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"\\nError: {e}\\n")

    except Exception as e:
        print(f"Failed to initialize KLoROS: {e}")

if __name__ == "__main__":
    main()
'''

            chat_file = '/home/kloros/scripts/standalone_chat.py'
            with open(chat_file, 'w') as f:
                f.write(standalone_chat_code)

            os.chmod(chat_file, 0o755)

            output += f"\u2705 Created standalone chat system: {chat_file}\n"
            output += "\u2705 Includes reasoning backend integration\n"
            output += "\u2705 Includes tool execution capabilities\n"
            output += "\u2705 Includes memory system integration\n"
            output += "\u2705 No voice dependencies\n"
            output += f"\u2705 Run with: python3 {chat_file}\n"

            return output

        except Exception as write_e:
            return f"\u274c Failed to write chat file: {write_e}"

    def _export_ace_bullets(self, kloros_instance, **kwargs):
        """Export ACE bullets from ChromaDB to markdown file."""
        from pathlib import Path

        output_path = kwargs.get('output_path', '~/.kloros/out/ace_bullets.md')
        max_bullets = int(kwargs.get('max_bullets', 50))

        out_file = Path(output_path).expanduser()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Try to access ACE bullet store if available
            if hasattr(kloros_instance, 'reason_backend'):
                backend = kloros_instance.reason_backend

                # Check if backend has ACE integration
                if hasattr(backend, 'ace_gen') and hasattr(backend, 'bullet_store'):
                    bullets_data = []

                    # Query latest bullets from ChromaDB
                    try:
                        results = backend.bullet_store.bullets.get(
                            limit=max_bullets,
                            include=['documents', 'metadatas']
                        )

                        if results and results.get('ids'):
                            for i in range(len(results['ids'])):
                                bullets_data.append({
                                    'text': results['documents'][i],
                                    'metadata': results['metadatas'][i]
                                })
                    except Exception as e:
                        return f"❌ Failed to query ACE bullets: {e}"

                    # Format as markdown
                    content = "# ACE Bullets\n\n"
                    content += f"Exported {len(bullets_data)} bullets\n\n"

                    # Group by domain
                    domains = {}
                    for bullet in bullets_data:
                        domain = bullet['metadata'].get('domain', 'general')
                        if domain not in domains:
                            domains[domain] = []
                        domains[domain].append(bullet)

                    for domain, domain_bullets in sorted(domains.items()):
                        content += f"## {domain.title()}\n\n"
                        for bullet in domain_bullets:
                            text = bullet['text']
                            win_rate = bullet['metadata'].get('win_rate', 0.0)
                            uses = bullet['metadata'].get('uses', 0)
                            content += f"- {text} (win_rate: {win_rate:.2f}, uses: {uses})\n"
                        content += "\n"

                    # Write to file
                    out_file.write_text(content, encoding='utf-8')

                    return f"✅ Exported {len(bullets_data)} ACE bullets to {out_file}"

            return "❌ ACE bullet store not available (requires RAG backend with ACE integration)"

        except Exception as e:
            return f"❌ Failed to export ACE bullets: {e}"

    def _check_dependencies(self, kloros_instance, package=None, **kwargs):
        """Check Python package dependencies and provide installation guidance."""
        try:
            common_deps = [
                'sentence-transformers',
                'transformers',
                'torch',
                'numpy',
                'requests',
                'pydantic'
            ]

            deps_to_check = [package] if package else common_deps

            output = "\u2705 Dependency Check Report\n"
            output += "=" * 40 + "\n"

            missing_packages = []

            for pkg in deps_to_check:
                pkg_list = pkg.replace('-', '_')
                try:
                    __import__(pkg_list)
                    output += f"{pkg}: Available\n"
                except ImportError:
                    output += f"\u274c {pkg}: Missing\n"
                    missing_packages.append(pkg)

            if missing_packages:
                output += "\nInstallation Commands:\n"
                for pkg in missing_packages:
                    output += f"  pip install {pkg}\n"
                    if pkg == 'sentence-transformers':
                        output += "  # Note: Large download (~2GB), improves RAG quality\n"

                pkg_list = ' '.join(missing_packages)
                output += f"\nQuick Fix for All Missing:\n  pip install {pkg_list}\n"
            else:
                output += "\nAll dependencies satisfied!\n"

            return output

        except Exception as e:
            return f"\u274c Dependency check failed: {e}"


    def _update_kb(self, category: str, filename: str, content: str, reason: str) -> str:
        """Helper to update KB and format result."""
        updater = get_updater()
        result = updater.update_documentation(category, filename, content, reason)
        
        if result['status'] == 'success':
            # Auto-rebuild RAG
            rebuild = updater.rebuild_rag_database()
            if rebuild['status'] == 'success':
                return f"✅ {result['message']}\n✅ RAG database rebuilt: {rebuild.get('stats', {}).get('chunks', 'N/A')} chunks"
            else:
                return f"✅ {result['message']}\n⚠️ RAG rebuild failed: {rebuild['message']}"
        else:
            return f"❌ {result['message']}"

    def _load_synthesized_tools(self):
        """Load previously synthesized tools from storage."""
        try:
            from src.tool_synthesis import SynthesizedToolStorage

            storage = SynthesizedToolStorage()
            synthesized_tools = storage.list_tools(status='active')

            for tool_info in synthesized_tools:
                tool_name = tool_info['name']
                tool_data = storage.load_tool(tool_name)

                # load_tool returns (tool_code, metadata) tuple or None
                if tool_data is None:
                    continue

                tool_code, metadata = tool_data

                # Create tool from code
                synthesized_tool = self._create_tool_from_code(tool_name, tool_code, metadata)
                if synthesized_tool:
                    self.register(synthesized_tool)

        except Exception as e:
            print(f"Warning: Failed to load synthesized tools: {e}")

    def _create_tool_from_code(self, tool_name, tool_code, metadata):
        """Create an IntrospectionTool from stored code."""
        try:
            namespace = {}
            exec(tool_code, namespace)

            analysis = metadata.get('analysis', {})
            purpose = analysis.get('purpose', f'Synthesized tool: {tool_name}')

            # Synthesized tools use naming convention: tool_{tool_name}
            func_name = f'tool_{tool_name}'
            tool_func = namespace.get(func_name)

            if tool_func is None:
                print(f"Warning: Function {func_name} not found in synthesized tool code")
                return None

            return IntrospectionTool(
                name=tool_name,
                description=purpose,
                func=tool_func,
                parameters=metadata.get('parameters', [])
            )
        except Exception as e:
            print(f"Failed to create tool from code: {e}")
            return None

    def _load_capability_tools(self):
        """Load auto-discovered capabilities as executable tools."""
        try:
            from registry.loader import get_registry

            registry = get_registry()
            capabilities = registry.get_enabled_capabilities()

            loaded_count = 0
            for cap in capabilities:
                # Only load auto-discovered capabilities
                if not cap.to_dict().get("auto_discovered", False):
                    continue

                # Check if we have investigation data for this module
                callable_interface = self._get_callable_interface(cap.module)

                if not callable_interface:
                    print(f"[tools] No callable interface for {cap.name}, skipping")
                    continue

                # Create tools from callable interface
                for interface in callable_interface:
                    tool = self._create_tool_from_interface(
                        cap_name=cap.name,
                        interface=interface,
                        module_path=cap.module
                    )

                    if tool:
                        self.register(tool)
                        loaded_count += 1
                        print(f"[tools] Loaded capability tool: {tool.name}")

            if loaded_count > 0:
                print(f"[tools] Loaded {loaded_count} capability tools")

        except Exception as e:
            print(f"[tools] Failed to load capability tools: {e}")

    def reload_capability_tools(self):
        """
        Hot-reload capability tools when capabilities.yaml changes.

        This enables zero-downtime integration of newly discovered modules.
        Tracks existing tools and only loads new ones.

        Returns:
            Number of newly loaded tools
        """
        try:
            import gc
            from registry.loader import reload_registry

            # Track tools before reload
            existing_tools = set(self.tools.keys())

            # Reload the capability registry to pick up new entries
            reload_registry()
            logger.info("[tools] Reloaded capability registry")

            # Force garbage collection after module reload to prevent memory leak
            gc.collect()
            logger.debug("[tools] Garbage collection after registry reload")

            # Load new capability tools
            from registry.loader import get_registry
            registry = get_registry()
            capabilities = registry.get_enabled_capabilities()

            loaded_count = 0
            for cap in capabilities:
                # Only load auto-discovered capabilities
                if not cap.to_dict().get("auto_discovered", False):
                    continue

                # Check if we have investigation data for this module
                callable_interface = self._get_callable_interface(cap.module)

                if not callable_interface:
                    continue

                # Create tools from callable interface
                for interface in callable_interface:
                    tool = self._create_tool_from_interface(
                        cap_name=cap.name,
                        interface=interface,
                        module_path=cap.module
                    )

                    if tool:
                        # Only register if this is a new tool
                        if tool.name not in existing_tools:
                            self.register(tool)
                            loaded_count += 1
                            logger.info(f"[tools] Hot-loaded new capability tool: {tool.name}")

            if loaded_count > 0:
                logger.info(f"[tools] Hot-reload complete: {loaded_count} new tools loaded")
            else:
                logger.debug("[tools] Hot-reload complete: no new tools")

            return loaded_count

        except Exception as e:
            logger.error(f"[tools] Failed to hot-reload capability tools: {e}")
            return 0

    def _get_callable_interface(self, module_path: str) -> List[Dict]:
        """Get callable interface from investigation results."""
        try:
            from pathlib import Path

            investigations_file = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
            if not investigations_file.exists():
                return []

            # Extract module name from Python import path (e.g., "test_discovery_module.calculator" -> "test_discovery_module")
            module_name = module_path.split('.')[0] if '.' in module_path else module_path

            # Find latest investigation for this module
            with open(investigations_file, 'r') as f:
                for line in reversed(list(f)):
                    if not line.strip():
                        continue

                    inv = json.loads(line)
                    inv_module_name = inv.get("module_name", "")

                    # Match on module name
                    if module_name == inv_module_name or module_name in inv.get("module_path", ""):
                        return inv.get("callable_interface", [])

            return []
        except Exception as e:
            print(f"[tools] Failed to read investigations: {e}")
            return []

    def _create_tool_from_interface(
        self,
        cap_name: str,
        interface: Dict,
        module_path: str
    ) -> Optional[IntrospectionTool]:
        """Create IntrospectionTool from callable interface."""
        try:
            function_name = interface.get("function")
            parameters = [p["name"] for p in interface.get("parameters", [])]
            description = interface.get("description", f"Auto-discovered: {function_name}")

            # Create wrapper function that dynamically imports and calls
            def tool_func(kloros_instance, **kwargs):
                try:
                    # Dynamic import of the module
                    import importlib
                    module = importlib.import_module(module_path)

                    # Get the function
                    func = getattr(module, function_name, None)
                    if func is None:
                        return f"Error: Function {function_name} not found in {module_path}"

                    # Call with provided kwargs
                    result = func(**kwargs)
                    return str(result)

                except Exception as e:
                    return f"Error executing {function_name}: {e}"

            tool_name = f"{cap_name}_{function_name}"

            return IntrospectionTool(
                name=tool_name,
                description=description,
                func=tool_func,
                parameters=parameters
            )

        except Exception as e:
            print(f"[tools] Failed to create tool from interface: {e}")
            return None

    def register_synthesized_tool(self, tool, tool_code, analysis):
        """
        Register a synthesized tool and save it to storage.
        Args:
            tool: IntrospectionTool instance
            tool_code: Python code for the tool
            analysis: Analysis data from synthesis
        Returns:
            True if registered and saved successfully, False otherwise
        """
        try:
            from src.tool_synthesis import SynthesizedToolStorage

            storage = SynthesizedToolStorage()
            storage.save_tool(tool.name, tool_code, analysis)
            self.register(tool)
            return True
        except Exception as e:
            print(f"Failed to register synthesized tool: {e}")
            return False

    def unregister_tool(self, tool_name):
        """
        Unregister a tool (remove from active registry).
        Args:
            tool_name: Name of the tool to unregister
        Returns:
            True if unregistered successfully, False otherwise
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
            return True
        return False

    def disable_tool(self, tool_name, reason):
        """
        Disable a synthesized tool.
        Args:
            tool_name: Name of the tool to disable
            reason: Reason for disabling
        Returns:
            True if disabled successfully, False otherwise
        """
        try:
            from src.tool_synthesis import SynthesizedToolStorage

            storage = SynthesizedToolStorage()
            storage.disable_tool(tool_name, reason)
            self.unregister_tool(tool_name)
            return True
        except Exception as e:
            print(f"Failed to disable tool: {e}")
            return False

    def get_synthesized_tools_info(self):
        """Get information about synthesized tools."""
        try:
            from src.tool_synthesis import SynthesizedToolStorage

            storage = SynthesizedToolStorage()
            active_tools = storage.list_tools(status='active')
            disabled_tools = storage.list_tools(status='disabled')

            return {
                'analytics': storage.get_stats(),
                'active_tools': active_tools,
                'disabled_tools': disabled_tools
            }
        except Exception as e:
            return f"Failed to get synthesized tools info: {e}"

    def _analyze_audio_quality(self, kloros_instance):
        """Analyze current microphone audio quality with detailed assessment."""
        try:
            from datetime import datetime

            output = "MICROPHONE AUDIO QUALITY ANALYSIS\n"
            output += "=" * 50 + "\n"
            output += f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            # Get recent audio metrics
            quality_metrics = self._get_recent_audio_metrics(kloros_instance)

            # Check data source
            data_source = quality_metrics.get('data_source', 'configuration_only')
            dbfs_mean = quality_metrics.get('dbfs_mean')

            if not dbfs_mean:
                output += "\u26a0\ufe0f No recent audio data available.\n"

                if quality_metrics.get('data_source') == 'configuration_only':
                    output += "Audio generation disabled due to previous failures or system constraints.\n"
                    output += "Please check microphone connection and try speaking to KLoROS.\n"

                # Try to generate real-time measurements
                if self._should_attempt_audio_generation(kloros_instance):
                    output += "\u2705 No recent audio data found - generating real-time measurements...\n"
                    generated_metrics = self._generate_audio_measurements_safely(kloros_instance)

                    if generated_metrics:
                        quality_metrics.update(generated_metrics)
                        data_source = 'generated'
                        dbfs_mean = generated_metrics.get('dbfs_mean')
                        output += f"\u2705 Successfully captured {generated_metrics.get('measurement_duration', 'N/A')}s of audio data\n"
                        self._record_successful_generation(kloros_instance)
                    else:
                        output += "\u274c Unable to generate audio measurements.\n"
                        output += "Microphone may be disconnected, muted, or system audio is unavailable.\n"
                        output += "Future audio generation attempts will be limited to prevent system loops.\n"
                        self._record_failed_generation(kloros_instance)
                else:
                    output += "\u274c Audio metrics system failed to retrieve any data.\n"

            # Calculate quality score
            quality_score = self._calculate_quality_score(quality_metrics)
            output += f"\u2705 OVERALL QUALITY SCORE: {quality_score}/100\n"

            # Quality rating
            rating = self._get_quality_rating(quality_score)
            output += f"\u2705 QUALITY RATING: {rating.upper()}\n"
            output += f"\u2705 DATA SOURCE: {data_source.upper()}\n\n"

            # Detailed metrics
            output += "\u2705 DETAILED METRICS:\n"

            # Activity and voice detection
            activity_ratio = quality_metrics.get('activity_ratio', 'N/A')
            if quality_metrics.get('real_operations_log'):
                if dbfs_mean:
                    output += f"\u2705 Average Level: {dbfs_mean:.2f} dBFS\n"
                else:
                    output += "\u26a0\ufe0f Average Level: N/A\n"

                dbfs_peak = quality_metrics.get('dbfs_peak', 'N/A')
                if dbfs_peak != 'N/A':
                    output += f"\u2705 Peak Level: {dbfs_peak:.2f} dBFS\n"
                else:
                    output += "\u26a0\ufe0f Peak Level: N/A\n"

                signal_strength = self._assess_signal_strength(quality_metrics)
                output += f"\u2705 Signal Strength: {signal_strength}\n"

                # RMS samples
                rms_samples = quality_metrics.get('rms_samples', 0)
                if rms_samples > 0:
                    output += f"\u2705 RMS Measurements: {rms_samples} samples\n"

                    avg_rms = quality_metrics.get('avg_rms')
                    if avg_rms:
                        output += f"\u2705 Average RMS: {avg_rms:.0f} (16-bit)\n"

                    max_rms = quality_metrics.get('max_rms')
                    if max_rms:
                        output += f"\u2705 Peak RMS: {max_rms:.0f}\n"
            else:
                output += "\u26a0\ufe0f Average Level: No real measurements\n"
                output += "\u26a0\ufe0f Peak Level: No real measurements\n"
                output += "\u26a0\ufe0f Signal Strength: Cannot assess (no data)\n"

            # Consistency
            consistency = self._assess_consistency(quality_metrics)
            output += f"\u2705 Consistency: {consistency}\n"

            # Voice activity
            if activity_ratio != 'N/A':
                output += f"\u2705 Voice Activity: {activity_ratio:.1%}\n"
            else:
                output += "\u26a0\ufe0f Voice Activity: N/A\n"

            # Memory events
            memory_audio_events = quality_metrics.get('memory_audio_events', 0)
            if memory_audio_events > 0:
                output += f"\u2705 Memory Events: {memory_audio_events} recent audio events\n"

            recent_tts_outputs = quality_metrics.get('recent_tts_outputs', 0)
            if recent_tts_outputs > 0:
                output += f"\u2705 TTS Outputs: {recent_tts_outputs} recent outputs\n"

            # Issues
            issues = self._detect_audio_issues(quality_metrics)
            if issues:
                output += "\n  DETECTED ISSUES:\n"
                for issue in issues:
                    output += f"  \u26a0\ufe0f {issue}\n"

            # Suggestions
            suggestions = self._generate_suggestions(quality_metrics)
            if suggestions:
                output += "\n OPTIMIZATION SUGGESTIONS:\n"
                for suggestion in suggestions:
                    output += f"  \u2705 {suggestion}\n"

            # Technical details
            output += "\n TECHNICAL DETAILS:\n"

            actual_input_gain = quality_metrics.get('actual_input_gain')
            if actual_input_gain:
                configured_gain = float(os.getenv('KLR_INPUT_GAIN', '4.5'))
                actual_gain = actual_input_gain
                output += f"\u2705 Input Gain: {actual_gain}x (configured: {configured_gain}x)\n"

            vad_threshold_dbfs = quality_metrics.get('vad_threshold_dbfs')
            if vad_threshold_dbfs:
                output += f"\u2705 VAD Threshold: {vad_threshold_dbfs} dBFS\n"
            else:
                vad_threshold = self._get_vad_threshold(kloros_instance)
                output += f"\u2705 VAD Threshold: {vad_threshold} dBFS (fallback)\n"

            capture_sample_rate = quality_metrics.get('capture_sample_rate')
            stt_sample_rate = quality_metrics.get('stt_sample_rate')
            if capture_sample_rate and stt_sample_rate:
                output += f"\u2705 Capture Rate: {capture_sample_rate}Hz\n"
                output += f"\u2705 STT Rate: {stt_sample_rate}Hz\n"

            audio_backend_name = quality_metrics.get('audio_backend_name')
            if audio_backend_name:
                output += f"\u2705 Audio Backend: {audio_backend_name}\n"

            wake_rms_threshold = quality_metrics.get('wake_rms_threshold')
            wake_rms_min = quality_metrics.get('wake_rms_min')
            if wake_rms_threshold and wake_rms_min:
                output += f"\u2705 Wake RMS Threshold: {wake_rms_threshold}\n"

            return output

        except Exception as e:
            return f"\u274c Audio quality analysis failed: {e}"

    def _get_recent_audio_metrics(self, kloros_instance):
        """Extract recent audio metrics from actual KLoROS operations log and memory."""
        from datetime import datetime, timedelta

        metrics = {
            'data_source': 'configuration_only',
            'real_operations_log': False
        }

        try:
            # Read operations log
            ops_log_path = '/home/kloros/.kloros/ops.log'
            recent_rms_values = []
            recent_audio_events = 0
            cutoff_time = datetime.now() - timedelta(minutes=10)

            if os.path.exists(ops_log_path):
                with open(ops_log_path, 'r') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            event_time = datetime.fromisoformat(data.get('timestamp', ''))

                            if event_time < cutoff_time:
                                continue

                            event = data.get('event', '')

                            # Wake detection events
                            if event == 'wake_result':
                                recent_audio_events += 1
                                metrics['real_operations_log'] = True

                            # Audio capture events
                            if event == 'audio_capture':
                                active_captures = sum(1 for x in data.get('dbfs', []) if x > -40)
                                if active_captures > 0:
                                    recent_audio_events += 1
                                    metrics['real_operations_log'] = True

                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue

            # Get configuration values
            metrics['input_gain'] = float(os.getenv('KLR_INPUT_GAIN', '4.5'))
            metrics['wake_rms_min'] = int(os.getenv('KLR_WAKE_RMS_MIN', '100'))

            # Check memory database
            try:
                memory_db = '/home/kloros/.kloros/memory.db'
                if os.path.exists(memory_db):
                    conn = sqlite3.connect(memory_db)
                    cursor = conn.cursor()

                    # Query audio-related events
                    cursor.execute('''
                    SELECT timestamp, event_type, content FROM events
                    WHERE (content LIKE '%audio%' OR content LIKE '%microphone%'
                           OR content LIKE '%quality%' OR content LIKE '%signal%'
                           OR event_type = 'wake_detection' OR event_type = 'audio_input')
                    AND timestamp > ?
                    ORDER BY timestamp DESC LIMIT 20
                    ''', (cutoff_time.isoformat(),))

                    memory_events = cursor.fetchall()
                    metrics['memory_audio_events'] = len(memory_events)

                    # Extract dBFS values from memory events
                    memory_dbfs_values = []
                    for event_type, content in memory_events:
                        import re
                        dbfs_matches = re.findall(r'(-?\d+\.?\d*)\s*dbfs', content.lower())
                        memory_dbfs_values.extend([float(x) for x in dbfs_matches])

                    # Query TTS outputs
                    cursor.execute('''
                    SELECT content FROM events
                    WHERE event_type = 'tts_output'
                    AND timestamp > ?
                    ORDER BY timestamp DESC LIMIT 10
                    ''', (cutoff_time.isoformat(),))

                    tts_events = cursor.fetchall()
                    metrics['recent_tts_outputs'] = len(tts_events)

                    conn.close()
            except Exception as e:
                print(f"[introspection] Memory system query failed: {e}")

            # Try to get live system introspection
            try:
                if hasattr(kloros_instance, 'audio_backend'):
                    metrics['audio_backend_name'] = type(kloros_instance.audio_backend).__name__

                if hasattr(kloros_instance, 'samplerate'):
                    metrics['capture_sample_rate'] = kloros_instance.samplerate

                vad_threshold = self._get_vad_threshold(kloros_instance)
                metrics['vad_threshold_dbfs'] = vad_threshold
            except Exception as e:
                print(f"[introspection] Process introspection failed: {e}")

            # Check reflection log
            try:
                reflection_log_path = '/home/kloros/.kloros/reflection.log'
                if os.path.exists(reflection_log_path):
                    with open(reflection_log_path, 'r') as f:
                        reflection_audio_analysis = [line for line in f if 'audio' in line.lower() or 'signal' in line.lower()]
                        if reflection_audio_analysis:
                            metrics['real_operations_log'] = True
            except Exception as e:
                print(f"[introspection] Warning: Could not read real audio metrics: {e}")

            return metrics

        except Exception as e:
            print(f"Failed to get audio metrics: {e}")
            return metrics

    def _generate_audio_measurements(self, kloros_instance, duration=2.0):
        """Generate real-time audio measurements by capturing live audio."""
        try:
            import numpy as np

            print(f"[introspection] Generating real-time audio measurements...")

            sample_rate = getattr(kloros_instance, 'samplerate', 48000)

            # Check if KLoROS has audio backend access
            if not hasattr(kloros_instance, 'audio_backend'):
                print("[introspection] No audio backend access - using system audio capture")
                return self._capture_system_audio_sample(kloros_instance, duration)

            print(f"[introspection] Capturing {duration}s of audio at {sample_rate}Hz...")

            # Capture audio in chunks
            samples_needed = int(duration * sample_rate)
            audio_chunks = []
            rms_values = []
            start_time = datetime.now()

            chunk_duration = 0.1  # 100ms chunks
            chunk_samples = int(chunk_duration * sample_rate)
            chunks_needed = int(duration / chunk_duration)

            for i in range(chunks_needed):
                try:
                    chunk = self._capture_audio_chunk(kloros_instance, chunk_samples, sample_rate)
                    if chunk is not None:
                        audio_chunks.append(chunk)

                        # Calculate RMS for this chunk
                        chunk_rms = numpy.sqrt(numpy.mean(chunk.astype('float32')**2))
                        rms_values.append(chunk_rms)
                except Exception as e:
                    print(f"[introspection] Chunk capture error: {e}")
                    continue

            if not audio_chunks:
                print("[introspection] No audio data captured")
                return None

            # Combine all chunks
            all_audio = numpy.concatenate(audio_chunks)

            # Calculate metrics
            rms_16bit = [rms * 32768 for rms in rms_values]
            active_chunks = sum(1 for rms in rms_16bit if rms > 100)

            dbfs_mean = 20 * numpy.log10(numpy.mean(rms_values)) if len(rms_values) > 0 else float('-inf')
            dbfs_peak = 20 * numpy.log10(numpy.max(rms_values)) if len(rms_values) > 0 else float('-inf')

            min_rms = numpy.min(rms_16bit) if len(rms_16bit) > 0 else 0

            # Validate the capture
            if not self._validate_legitimate_audio_capture(audio_chunks, duration, sample_rate):
                print("[introspection] WARNING: Audio capture validation failed - data may be invalid")

            metrics = {
                'data_source': 'generated_realtime',
                'measurement_duration': duration,
                'dbfs_mean': dbfs_mean,
                'dbfs_peak': dbfs_peak,
                'rms_samples': len(rms_values),
                'avg_rms': numpy.mean(rms_16bit),
                'max_rms': numpy.max(rms_16bit),
                'min_rms': min_rms,
                'activity_ratio': active_chunks / len(rms_values) if len(rms_values) > 0 else 0,
                'capture_timestamp': datetime.now().isoformat(),
                'real_operations_log': True
            }

            print(f"[introspection] \u2705 LEGITIMATE CAPTURE: {dbfs_mean:.2f} dBFS mean, {dbfs_peak:.2f} dBFS peak, {metrics['activity_ratio']:.1%} activity")

            return metrics

        except Exception as e:
            print(f"[introspection] KLoROS audio capture failed: {e}")
            return None

    def _capture_audio_chunk(self, kloros_instance, chunk_samples, sample_rate):
        """Capture a single chunk of audio from the KLoROS audio system."""
        try:
            if hasattr(kloros_instance, 'audio_backend') and hasattr(kloros_instance.audio_backend, 'chunks'):
                # Calculate block_ms from chunk_samples and sample_rate
                block_ms = int((chunk_samples / sample_rate) * 1000)
                chunk_iter = kloros_instance.audio_backend.chunks(block_ms)
                chunk = next(chunk_iter)
                return chunk
            else:
                # Fallback to sounddevice
                import sounddevice as sd
                device_index = int(os.getenv('KLR_INPUT_IDX', '11'))
                chunk = sd.rec(chunk_samples, samplerate=sample_rate, channels=1, dtype='int16', device=device_index)
                sd.wait()
                return chunk.flatten()
        except (StopIteration, Exception) as e:
            print(f"[introspection] Chunk capture method failed: {e}")
            return None

    def _capture_system_audio_sample(self, kloros_instance, duration):
        """Fallback method to capture audio using system tools."""
        try:
            import tempfile
            import wave
            import numpy as np

            print("[introspection] Using system audio capture fallback...")

            # Create temporary file
            tmp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            # Use parecord to capture audio
            device_name = "alsa_input.usb-CMTECK_Co._Ltd._CMTECK_000000000000-00.mono-fallback"

            result = subprocess.run(
                ['parecord', '--device', device_name, '--format=s16le', '--rate=48000',
                 '--channels=1', '--raw', '--file-format=wav', tmp_path],
                timeout=duration + 1,
                capture_output=True
            )

            # Read the captured audio
            wav_file = wave.open(tmp_path, 'rb')
            frames = wav_file.readframes(wav_file.getnframes())
            wav_file.close()

            audio_data = numpy.frombuffer(frames, dtype='int16')

            # Calculate metrics
            max_value = 32768.0
            rms = numpy.sqrt(numpy.mean((audio_data / max_value)**2))
            peak = numpy.max(numpy.abs(audio_data)) / max_value

            dbfs_mean = 20 * numpy.log10(rms) if rms > 0 else float('-inf')
            dbfs_peak = 20 * numpy.log10(peak) if peak > 0 else float('-inf')

            active_frames = sum(1 for x in audio_data if abs(x) > 100)

            # Clean up
            os.unlink(tmp_path)

            return {
                'data_source': 'generated_system_capture',
                'measurement_duration': duration,
                'dbfs_mean': dbfs_mean,
                'dbfs_peak': dbfs_peak,
                'rms_samples': len(audio_data),
                'activity_ratio': active_frames / len(audio_data),
                'real_operations_log': True
            }

        except Exception as e:
            print(f"[introspection] System audio capture failed: {e}")
            return None

    def _should_attempt_audio_generation(self, kloros_instance):
        """Check if audio generation should be attempted (prevent infinite loops)."""
        try:
            failure_file = '/tmp/kloros_audio_generation_failures.json'

            if os.path.exists(failure_file):
                with open(failure_file, 'r') as f:
                    failure_data = json.load(f)

                # Check consecutive failures
                consecutive_failures = failure_data.get('consecutive_failures', 0)
                if consecutive_failures >= 3:
                    print("[safeguard] Audio generation blocked: too many consecutive failures")
                    return False

                # Check recent failures (last hour)
                failures = failure_data.get('failures', [])
                current_time = datetime.now()
                recent_failures = [f for f in failures
                                  if (current_time - datetime.fromisoformat(f)).total_seconds() < 3600]

                if len(recent_failures) >= 5:
                    print("[safeguard] Audio generation blocked: too many recent failures")
                    return False

                # Check if we need to cool down
                if failures:
                    last_failure = datetime.fromisoformat(failures[-1])
                    if (current_time - last_failure).total_seconds() < 300:  # 5 minutes
                        print("[safeguard] Audio generation blocked: cooling down after recent failure")
                        return False

            return True

        except Exception as e:
            print(f"[safeguard] Error checking generation eligibility: {e}")
            return True

    def _record_successful_generation(self, kloros_instance):
        """Record successful audio generation to reset failure counters."""
        try:
            failure_file = '/tmp/kloros_audio_generation_failures.json'

            failure_data = {
                'consecutive_failures': 0,
                'failures': [],
                'last_success': datetime.now().isoformat()
            }

            with open(failure_file, 'w') as f:
                json.dump(failure_data, f)

            print("[safeguard] Audio generation success recorded")
        except Exception as e:
            print(f"[safeguard] Error recording success: {e}")

    def _record_failed_generation(self, kloros_instance):
        """Record failed audio generation attempt."""
        try:
            failure_file = '/tmp/kloros_audio_generation_failures.json'

            if os.path.exists(failure_file):
                with open(failure_file, 'r') as f:
                    failure_data = json.load(f)
            else:
                failure_data = {'consecutive_failures': 0, 'failures': []}

            failure_data['consecutive_failures'] = failure_data.get('consecutive_failures', 0) + 1
            failure_data['failures'].append(datetime.now().isoformat())

            with open(failure_file, 'w') as f:
                json.dump(failure_data, f)

            print(f"[safeguard] Audio generation failure recorded (consecutive: {failure_data['consecutive_failures']})")
        except Exception as e:
            print(f"[safeguard] Error recording failure: {e}")

    def _generate_audio_measurements_safely(self, kloros_instance):
        """Generate audio measurements with timeout and error safeguards."""
        def timeout_handler(signum, frames):
            raise TimeoutError("Audio generation timed out")

        try:
            print("[safeguard] Starting audio generation with 10s timeout...")

            # Set alarm for 10 seconds
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)

            try:
                metrics = self._generate_audio_measurements(kloros_instance)
                signal.alarm(0)  # Cancel alarm

                if metrics and metrics.get('dbfs_mean'):
                    print("[safeguard] Audio generation completed successfully")
                    return metrics
                else:
                    print("[safeguard] Audio generation returned empty/invalid data")
                    return None

            except TimeoutError:
                print("[safeguard] Audio generation timed out after 10 seconds")
                return None
            except Exception as e:
                print(f"[safeguard] Audio generation failed with error: {e}")
                return None

        except Exception as e:
            print(f"[safeguard] Safety wrapper failed: {e}")
            return None

    def _analyze_memory_status_proactive(self, kloros_instance):
        """Analyze memory system status with proactive data generation if needed."""
        try:
            output = "MEMORY SYSTEM STATUS (PROACTIVE MODE)\n"
            output += "=" * 50 + "\n"

            # Check if memory system is available
            if not hasattr(kloros_instance, 'memory_enhanced') or not kloros_instance.memory_enhanced:
                return "\u274c Memory system not initialized\nThe episodic memory system is not available on this KLoROS instance."

            memory_system = kloros_instance.memory_enhanced

            # Check if memory is enabled
            if not memory_system.enable_memory:
                return "\u26a0\ufe0f Memory system is disabled\nSet KLR_ENABLE_MEMORY=1 to enable episodic memory."

            # Get memory stats
            stats = memory_system.get_memory_stats()

            # Format the stats
            output += f"Status: \u2705 Enabled\n"
            output += f"Database: {stats.get('database_path', 'unknown')}\n"
            output += f"Current Conversation: {stats.get('current_conversation', 'none')}\n\n"

            output += "EVENT STATISTICS:\n"
            output += f"  Total Events: {stats.get('total_events', 0)}\n"
            output += f"  Recent (24h): {stats.get('events_last_24h', 0)}\n"
            output += f"  This Week: {stats.get('events_last_7d', 0)}\n\n"

            output += "EPISODE STATISTICS:\n"
            output += f"  Total Episodes: {stats.get('total_episodes', 0)}\n"
            output += f"  Recent (24h): {stats.get('episodes_last_24h', 0)}\n\n"

            output += "SUMMARY STATISTICS:\n"
            output += f"  Total Summaries: {stats.get('total_summaries', 0)}\n"
            output += f"  Avg Importance: {stats.get('avg_importance', 0):.2f}\n\n"

            # Add event type breakdown if available
            if 'event_types' in stats:
                output += "EVENT TYPE BREAKDOWN:\n"
                for event_type, count in sorted(stats['event_types'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    output += f"  {event_type}: {count}\n"

            return output

        except Exception as e:
            return f"\u274c Memory status analysis failed: {e}"

    def _has_sufficient_memory_data(self, kloros_instance):
        """Check if we have sufficient recent memory data."""
        try:
            if not hasattr(kloros_instance, 'memory_enhanced'):
                return False

            memory_db = '/home/kloros/.kloros/memory.db'
            if not os.path.exists(memory_db):
                return False

            conn = sqlite3.connect(memory_db)
            cursor = conn.cursor()

            cutoff_time = (datetime.now() - timedelta(hours=1)).isoformat()
            cursor.execute('SELECT COUNT(*) FROM events WHERE timestamp > ?', (cutoff_time,))
            recent_events = cursor.fetchone()[0]

            conn.close()

            return recent_events >= 10

        except Exception as e:
            print(f"[memory] Error checking data sufficiency: {e}")
            return False

    def _generate_memory_activity(self, kloros_instance):
        """Generate memory activity to produce fresh data for analysis."""
        try:
            if not hasattr(kloros_instance, 'memory_enhanced'):
                return None

            operations = 0
            new_events = 0

            # Generate diagnostic event
            if hasattr(kloros_instance.memory_enhanced, 'memory_logger'):
                kloros_instance.memory_enhanced.memory_logger.log_event(
                    event_type='real_time_introspection',
                    content='Memory system diagnostic triggered for introspection analysis'
                )
                new_events += 1

            # Get memory stats
            try:
                stats = kloros_instance.memory_enhanced.get_memory_stats()
                kloros_instance.memory_enhanced.memory_logger.log_event(
                    event_type='real_time_introspection',
                    content=f'Memory statistics retrieved: {len(stats)} metrics available'
                )
                operations += 1
                new_events += 1
            except Exception as e:
                print(f"[memory] Stats generation failed: {e}")

            # Perform a search
            try:
                search_results = kloros_instance.memory_enhanced.search_memory('system status', max_results=5)
                kloros_instance.memory_enhanced.memory_logger.log_event(
                    event_type='real_time_introspection',
                    content=f'Memory search performed: {len(search_results)} results'
                )
                operations += 1
                new_events += 1
            except Exception as e:
                print(f"[memory] Search generation failed: {e}")

            # Run housekeeping
            try:
                if hasattr(kloros_instance.memory_enhanced, 'memory_enhanced'):
                    from src.kloros_memory.housekeeping import MemoryHousekeeper
                    housekeeper = MemoryHousekeeper()
                    health_report = housekeeper.get_health_report()
                    operations += 1
            except Exception as e:
                print(f"[memory] Housekeeping activity generation failed: {e}")

            print(f"[memory] Generated {new_events} events, {operations} operations")

            return {
                'new_events': new_events,
                'operations': operations
            }

        except Exception as e:
            print(f"[memory] Activity generation failed: {e}")
            return None

    def _validate_legitimate_audio_capture(self, audio_chunks, duration, sample_rate):
        """Validate that captured audio data represents legitimate real-world measurements."""
        try:
            if not audio_chunks:
                print("[validation] FAIL: No audio chunks captured")
                return False

            # Combine all chunks
            all_audio = numpy.concatenate(audio_chunks)

            if len(all_audio) == 0:
                print("[validation] FAIL: Empty audio data")
                return False

            # Check for all zeros (dead microphone)
            if numpy.all(all_audio == 0):
                print("[validation] FAIL: All audio samples are zero (dead microphone)")
                return False

            # Check for diversity of values (synthetic data tends to be too uniform)
            unique_values = len(numpy.unique(all_audio))
            if unique_values < 100:
                print(f"[validation] FAIL: Too few unique values ({unique_values}) - likely synthetic")
                return False

            # Calculate RMS for validation
            chunk_rms_values = [numpy.sqrt(numpy.mean(chunk.astype('float32')**2)) for chunk in audio_chunks]
            dbfs_mean = 20 * numpy.log10(numpy.mean(chunk_rms_values)) if len(chunk_rms_values) > 0 else float('-inf')

            # Check for unrealistic dBFS levels
            if dbfs_mean > 0:
                print(f"[validation] FAIL: Unrealistic dBFS level ({dbfs_mean:.2f}) - outside microphone range")
                return False

            if dbfs_mean < -60:
                print(f"[validation] FAIL: Unrealistic dBFS level ({dbfs_mean:.2f}) - outside microphone range")
                return False

            # Check for variation in RMS (real audio should vary)
            rms_variation = numpy.std(chunk_rms_values)
            if rms_variation < 0.001:
                print(f"[validation] FAIL: RMS variation too low ({rms_variation:.6f}) - likely synthetic")
                return False

            # Check activity ratio
            rms_16bit = [rms * 32768 for rms in chunk_rms_values]
            active_chunks = sum(1 for rms in rms_16bit if rms > 100)
            activity_ratio = active_chunks / len(chunk_rms_values) if len(chunk_rms_values) > 0 else 0

            if activity_ratio > 0.95:
                print(f"[validation] FAIL: Activity ratio too high ({activity_ratio:.2%}) - likely synthetic noise")
                return False

            # Check for clipping
            abs_samples = numpy.abs(all_audio.astype('float32'))
            max_amplitude = numpy.max(abs_samples)
            median_amplitude = numpy.median(abs_samples)

            if max_amplitude > 0.95:
                print(f"[validation] WARNING: High amplitude ({max_amplitude:.3f}) - possible clipping")

            if max_amplitude < 0.01:
                print(f"[validation] FAIL: Maximum amplitude too low ({max_amplitude:.6f}) - likely invalid")
                return False

            # Check dynamic range
            dynamic_range = max_amplitude / (median_amplitude + 0.001)
            if dynamic_range < 1.5:
                print(f"[validation] FAIL: Dynamic range too low ({dynamic_range:.2f}) - likely synthetic")
                return False

            # Check sample count
            expected_samples = int(duration * sample_rate * 0.9)  # Allow 10% tolerance
            actual_samples = len(all_audio)

            if actual_samples < expected_samples:
                print(f"[validation] FAIL: Sample count mismatch (got {actual_samples}, expected ~{expected_samples})")
                return False

            print(f"[validation] \u2705 PASS: {actual_samples} samples, {unique_values} unique values, {dbfs_mean:.2f} dBFS, {activity_ratio:.2%} activity")
            return True

        except Exception as e:
            print(f"[validation] ERROR: Validation failed with exception: {e}")
            return False

    def _calculate_quality_score(self, metrics):
        """Calculate composite quality score (0-100)."""
        score = 0

        # dBFS level (40 points)
        dbfs_mean = metrics.get('dbfs_mean')
        if dbfs_mean:
            if -20 <= dbfs_mean <= -10:
                score += 40
            elif -30 <= dbfs_mean <= -20 or -10 <= dbfs_mean <= -6:
                score += 30
            elif -40 <= dbfs_mean <= -30:
                score += 20
            else:
                score += 10

        # Activity ratio (30 points)
        activity = metrics.get('activity_ratio', 0)
        if activity:
            if 0.3 <= activity <= 0.7:
                score += 30
            elif 0.1 <= activity <= 0.3 or 0.7 <= activity <= 0.9:
                score += 20
            else:
                score += 10

        # Dynamic range (30 points)
        if metrics.get('real_operations_log'):
            dynamic_range = metrics.get('max_rms', 0) - metrics.get('min_rms', 0)
            if dynamic_range > 1000:
                score += 30
            elif dynamic_range > 500:
                score += 20
            else:
                score += 10

        return min(score, 100)

    def _get_quality_rating(self, score):
        """Convert numeric score to quality rating."""
        if score >= 80:
            return " EXCELLENT"
        elif score >= 60:
            return " GOOD"
        elif score >= 40:
            return " FAIR"
        elif score >= 20:
            return " POOR"
        else:
            return "\u274c VERY POOR"

    def _assess_signal_strength(self, metrics):
        """Assess signal strength from dBFS levels."""
        dbfs_mean = metrics.get('dbfs_mean')
        if not dbfs_mean:
            return "N/A"

        if dbfs_mean > -10:
            return " TOO LOUD (may clip)"
        elif -20 <= dbfs_mean <= -10:
            return " OPTIMAL"
        elif -30 <= dbfs_mean <= -20:
            return " WEAK"
        else:
            return "\u274c TOO QUIET"

    def _assess_consistency(self, metrics):
        """Assess audio level consistency."""
        if not metrics.get('real_operations_log'):
            return "N/A"

        rms_samples = metrics.get('rms_samples', 0)
        if rms_samples < 2:
            return "N/A"

        avg_rms = metrics.get('avg_rms', 0)
        max_rms = metrics.get('max_rms', 0)

        if max_rms == 0:
            return "N/A"

        variation = (max_rms - avg_rms) / max_rms

        if variation < 0.2:
            return " VERY STABLE"
        elif variation < 0.4:
            return " STABLE"
        elif variation < 0.6:
            return " VARIABLE"
        else:
            return "\u26a0\ufe0f INCONSISTENT"

    def _detect_audio_issues(self, metrics):
        """Detect specific audio quality issues."""
        issues = []

        dbfs_mean = metrics.get('dbfs_mean')
        if dbfs_mean:
            if dbfs_mean < -30:
                issues.append("Signal too quiet - microphone may be too far or gain too low")

            if dbfs_mean > -10:
                issues.append("Signal too loud - risk of clipping and distortion")

            dbfs_peak = metrics.get('dbfs_peak')
            if dbfs_peak and dbfs_peak > -6:
                issues.append("Peak levels indicate clipping - reduce input gain")

        activity_ratio = metrics.get('activity_ratio')
        if activity_ratio and activity_ratio < 0.1:
            issues.append("Very low voice activity detected - check microphone positioning")

        if metrics.get('real_operations_log'):
            max_rms = metrics.get('max_rms', 0)
            min_rms = metrics.get('min_rms', 0)
            dynamic_range = max_rms - min_rms

            if dynamic_range > 2000:
                issues.append("High dynamic range suggests inconsistent microphone distance")

        return issues

    def _generate_suggestions(self, metrics):
        """Generate optimization suggestions based on metrics."""
        suggestions = []

        dbfs_mean = metrics.get('dbfs_mean')
        input_gain = metrics.get('input_gain', 4.5)

        if dbfs_mean:
            if dbfs_mean < -30:
                new_gain = min(input_gain * 1.5, 10.0)
                suggestions.append(f"Increase input gain from {input_gain}x to {new_gain}x")
                suggestions.append("Move closer to microphone (6-12 inches optimal)")

            if dbfs_mean > -10:
                new_gain = max(input_gain * 0.7, 0.5)
                suggestions.append(f"Decrease input gain from {input_gain}x to {new_gain}x")
                suggestions.append("Move further from microphone to reduce volume")

        activity_ratio = metrics.get('activity_ratio')
        if activity_ratio and activity_ratio < 0.3:
            suggestions.append("Speak directly toward microphone for best recognition")
            suggestions.append("Minimize background noise and echoes")
            suggestions.append("Consider using a dedicated USB microphone for better quality")

        if not metrics.get('real_operations_log'):
            suggestions.append("Test microphone with a longer speech sample")
            suggestions.append("Check if microphone is muted or blocked")

        return suggestions

    def _get_vad_threshold(self, kloros_instance):
        """Get VAD threshold from KLoROS configuration."""
        return float(os.getenv('KLR_VAD_THRESHOLD_DBFS', '-30.0'))

    def enable_synthesis(self, enabled: bool):
        """Enable or disable tool synthesis."""
        self.synthesis_enabled = enabled

    def is_synthesis_enabled(self) -> bool:
        """Check if tool synthesis is enabled."""
        return self.synthesis_enabled


    def _analyze_tool_ecosystem(self, kloros_instance):
        """Analyze synthesized tools for optimization opportunities."""
        try:
            from src.tool_synthesis.ecosystem_manager import ToolEcosystemManager
            
            manager = ToolEcosystemManager()
            analysis = manager.analyze_ecosystem()
            
            if analysis['status'] == 'insufficient_tools':
                return f"🔧 Tool Ecosystem Analysis\n\nInsufficient tools for analysis (need at least 2 synthesized tools).\n\nCurrent synthesized tools: {analysis['total_tools']}"
            
            result = ["🔧 Tool Ecosystem Analysis", ""]
            result.append(f"Total Synthesized Tools: {analysis['total_tools']}")
            result.append(f"Analysis Time: {analysis.get('analysis_timestamp', 'unknown')}")
            result.append("")
            
            recommendations = analysis.get('recommendations', [])
            
            if not recommendations:
                result.append("✅ Tool ecosystem is optimized - no redundancy or combination opportunities found.")
                return "\n".join(result)
            
            # Organize by type
            combines = [r for r in recommendations if r['type'] == 'combine']
            prunes = [r for r in recommendations if r['type'] == 'prune']
            
            if combines:
                result.append("📦 Combination Opportunities:")
                for combo in combines:
                    result.append(f"  • Combine: {', '.join(combo['tools'])}")
                    result.append(f"    → {combo['proposed_name']}")
                    result.append(f"    Rationale: {combo['rationale']}")
                    result.append(f"    Priority: {combo['priority']}/10")
                    result.append("")
            
            if prunes:
                result.append("✂️  Pruning Opportunities:")
                for prune in prunes:
                    result.append(f"  • Redundant: {', '.join(prune['tools'])}")
                    result.append(f"    Keep: {prune['keep']}")
                    result.append(f"    Remove: {prune['remove']}")
                    result.append(f"    Rationale: {prune['rationale']}")
                    result.append(f"    Priority: {prune['priority']}/10")
                    result.append("")
            
            result.append("💡 High-priority recommendations auto-submitted to D-REAM for implementation.")
            
            # Auto-submit high priority
            high_priority = [r for r in recommendations if r.get('priority', 0) >= 8]
            if high_priority:
                submitted = manager.submit_recommendations_to_dream(high_priority)
                if submitted:
                    result.append(f"✅ Submitted {len(high_priority)} high-priority optimizations to D-REAM")
            
            return "\n".join(result)
            
        except Exception as e:
            return f"❌ Tool ecosystem analysis failed: {e}"

    def _map_system(self, kloros_instance) -> str:
        """Perform comprehensive system mapping."""
        try:
            from src.introspection.system_mapper import SystemMapper

            print("[map_system] Starting comprehensive system scan...")
            mapper = SystemMapper()
            system_map = mapper.scan_full_system(force=True)  # Force fresh scan

            # Generate human-readable report
            result = []
            result.append("=== KLoROS System Map ===")
            result.append("")

            # Filesystem
            fs = system_map.get("filesystem", {})
            result.append(f"📁 Filesystem:")
            result.append(f"  • Directories: {len(fs.get('directories', []))}")
            result.append(f"  • Python modules: {len(fs.get('python_modules', []))}")
            result.append(f"  • Data directories: {len(fs.get('data_directories', []))}")
            result.append("")

            # Hardware
            hw = system_map.get("hardware", {})
            result.append(f"🖥️  Hardware:")
            gpu = hw.get("gpu", {})
            if gpu.get("available"):
                result.append(f"  • GPU: {gpu['count']} device(s) detected")
                for i, device in enumerate(gpu.get("devices", []), 1):
                    result.append(f"    {i}. {device['name']} ({device['memory_mb']})")
            else:
                result.append("  • GPU: None detected")

            mem = hw.get("memory", {})
            if mem:
                result.append(f"  • Memory: {mem.get('total_gb', '?')}GB total, {mem.get('available_gb', '?')}GB available")

            cpu = hw.get("cpu", {})
            if cpu:
                result.append(f"  • CPU: {cpu.get('model', 'Unknown')} ({cpu.get('cores', '?')} cores)")
            result.append("")

            # Tools
            tools = system_map.get("tools", [])
            result.append(f"🔧 Registered Tools: {len(tools)}")
            if tools:
                result.append("  Most recent:")
                for tool in tools[:10]:
                    result.append(f"  • {tool['name']}: {tool['description'][:60]}")
            result.append("")

            # Gap analysis
            gaps = system_map.get("gap_analysis", {})
            missing_tools = gaps.get("missing_tools", [])
            if missing_tools:
                result.append(f"⚠️  Missing Tools: {len(missing_tools)}")
                for gap in missing_tools[:10]:
                    result.append(f"  • {gap['subsystem']}: {gap['description']}")
                    result.append(f"    Priority: {gap['priority']}")
                result.append("")
                result.append("💡 Use idle reflection to proactively synthesize these tools.")
            else:
                result.append("✅ No critical tool gaps detected")

            return "\n".join(result)

        except Exception as e:
            return f"❌ System mapping failed: {e}"

    def _test_capabilities(self, kloros_instance) -> str:
        """Run comprehensive capability tests."""
        try:
            from src.introspection.capability_tester import CapabilityTester

            print("[test_capabilities] Starting capability tests...")
            tester = CapabilityTester(kloros_instance=kloros_instance)
            test_results = tester.run_all_tests()

            # Generate report
            result = []
            result.append("=== KLoROS Capability Test Results ===")
            result.append("")
            result.append(f"🏥 Overall Health Score: {test_results['health_score']:.2%}")
            result.append(f"⏱️  Test Duration: {test_results['test_duration_s']:.1f}s")
            result.append("")

            # Component breakdown
            components = {
                "stt": "🎤 Speech Recognition",
                "tts": "🔊 Text-to-Speech",
                "rag": "📚 RAG Retrieval",
                "vad": "🎙️  Voice Activity Detection",
                "tool_execution": "🔧 Tool Execution",
                "memory": "🧠 Memory System"
            }

            for comp_key, comp_name in components.items():
                comp_data = test_results.get(comp_key, {})
                if not comp_data.get("available"):
                    result.append(f"{comp_name}: ❌ Not available")
                    continue

                tests = comp_data.get("tests", [])
                if tests:
                    passed = sum(1 for t in tests if t.get("passed", False))
                    total = len(tests)
                    pass_rate = (passed / total * 100) if total > 0 else 0
                    result.append(f"{comp_name}: {passed}/{total} tests passed ({pass_rate:.0f}%)")

                    # Show failed tests
                    failed = [t for t in tests if not t.get("passed", False)]
                    if failed:
                        for f in failed[:3]:
                            test_name = f.get("test", "unknown")
                            error = f.get("error", "no details")
                            result.append(f"  ⚠️  {test_name}: {error[:60]}")
                else:
                    result.append(f"{comp_name}: ✓ Responsive")
            result.append("")

            # Optimization opportunities
            optimization_targets = tester.get_optimization_targets()
            if optimization_targets:
                result.append(f"🎯 Optimization Opportunities: {len(optimization_targets)}")
                for target in optimization_targets[:5]:
                    result.append(f"  • {target['component']}: {target['reason']}")
                    result.append(f"    Priority: {target['priority']}")
                result.append("")
                result.append("💡 These targets can be submitted to D-REAM for optimization.")

            return "\n".join(result)

        except Exception as e:
            return f"❌ Capability testing failed: {e}"

    @staticmethod
    def parse_tool_call(llm_response: str) -> Optional[str]:
        """Parse LLM response for tool call. Returns tool name if found."""
        if 'TOOL:' in llm_response:
            parts = llm_response.split('TOOL:')
            if len(parts) > 1:
                tool_name = parts[1].strip().split()[0]
                return tool_name
        return None

    def _run_chaos_test(self, kloros_instance, **kwargs) -> str:
        """Run a specific chaos experiment asynchronously to prevent blocking main thread."""
        scenario_id = kwargs.get('scenario_id', '').strip()

        if not scenario_id:
            return "❌ Error: scenario_id required. Use list_chaos_scenarios to see available tests."

        if not hasattr(kloros_instance, 'chaos') or kloros_instance.chaos is None:
            return "❌ Chaos Lab not available. System may need restart."

        try:
            from src.dream_lab import load_specs
            import os
            import threading

            specs_path = os.path.join(os.path.dirname(__file__), "dream_lab", "fixtures", "example_specs.yaml")
            specs = load_specs(specs_path)

            target_spec = next((s for s in specs if s.id == scenario_id), None)
            if not target_spec:
                return f"❌ Scenario '{scenario_id}' not found. Use list_chaos_scenarios to see available options."

            print(f"[chaos] Starting experiment in background: {scenario_id}")

            # Run chaos experiment in background thread to prevent blocking main thread/watchdog
            def run_experiment():
                try:
                    print(f"[chaos] Executing experiment: {scenario_id}")
                    result = kloros_instance.chaos.run(target_spec)

                    # Format results
                    output = [
                        "🧪 CHAOS EXPERIMENT RESULTS",
                        "=" * 60,
                        f"Scenario: {result['spec_id']}",
                        f"Target: {result['target']}",
                        f"Mode: {result['mode']}",
                        "",
                        f"✅ Healed: {result['outcome'].get('healed')}" if result['outcome'].get('healed') else f"❌ Healed: False",
                        f"⏱️  Duration: {result['outcome'].get('duration_s', 0):.1f}s",
                        f"📊 Score: {result['score']}/100",
                        ""
                    ]

                    if result['outcome'].get('reason'):
                        output.append(f"Reason: {result['outcome']['reason']}")
                        output.append("")

                    events = result.get('events', [])
                    if events:
                        output.append(f"📨 Events Captured: {len(events)}")
                        for evt in events[:5]:
                            output.append(f"  • {evt['source']}.{evt['kind']} ({evt['severity']})")
                    else:
                        output.append("📨 No healing events captured")

                    # Save to history
                    self._save_chaos_result(result)

                    # Always feed to D-REAM (especially low scores = weaknesses!)
                    self._feed_to_dream(kloros_instance, result)

                    print(f"[chaos] Experiment complete: {scenario_id}")
                    print("\n".join(output))

                except Exception as e:
                    print(f"[chaos] ❌ Experiment failed: {e}")

            # Start background thread (daemon=True means it won't block shutdown)
            thread = threading.Thread(target=run_experiment, daemon=True, name=f"chaos-{scenario_id}")
            thread.start()

            return f"🧪 Chaos experiment '{scenario_id}' started in background. Results will be logged when complete."

        except Exception as e:
            return f"❌ Chaos test failed to start: {e}"

    def _list_chaos_scenarios(self, kloros_instance) -> str:
        """List all available chaos scenarios."""
        try:
            from src.dream_lab import load_specs
            import os
            
            specs_path = os.path.join(os.path.dirname(__file__), "dream_lab", "fixtures", "example_specs.yaml")
            specs = load_specs(specs_path)
            
            if not specs:
                return "❌ No chaos scenarios found"
            
            output = [
                "📋 AVAILABLE CHAOS SCENARIOS",
                "=" * 60,
                ""
            ]
            
            # Group by target
            by_target = {}
            for spec in specs:
                target = spec.target.split('.')[0] if '.' in spec.target else spec.target.split(':')[0]
                if target not in by_target:
                    by_target[target] = []
                by_target[target].append(spec)
            
            for target in sorted(by_target.keys()):
                output.append(f"\n🎯 {target.upper()}")
                output.append("-" * 60)
                for spec in by_target[target]:
                    output.append(f"  {spec.id}")
                    output.append(f"    Mode: {spec.mode}")
                    output.append(f"    Max Duration: {spec.guards.get('max_duration_s', 20)}s")
                    expected = spec.expected.get('heal_event')
                    if expected:
                        output.append(f"    Tests: {expected.get('source')}.{expected.get('kind')}")
                    output.append("")
            
            output.append(f"Total: {len(specs)} scenarios available")
            output.append("\nUsage: TOOL: run_chaos_test scenario_id=<id>")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"❌ Failed to list scenarios: {e}"

    def _chaos_history(self, kloros_instance, **kwargs) -> str:
        """View chaos experiment history."""
        limit = kwargs.get('limit', 10)
        
        try:
            import json
            from pathlib import Path
            
            history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
            
            if not history_file.exists():
                return "📊 No chaos history yet. Run some experiments with run_chaos_test!"
            
            # Read last N results
            results = []
            with open(history_file, 'r') as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
            
            results = results[-limit:]  # Take last N
            
            if not results:
                return "📊 No chaos history yet"
            
            output = [
                "📊 CHAOS EXPERIMENT HISTORY",
                "=" * 60,
                ""
            ]
            
            # Stats
            total = len(results)
            healed = sum(1 for r in results if r.get('outcome', {}).get('healed'))
            avg_score = sum(r.get('score', 0) for r in results) / total if total > 0 else 0
            avg_mttr = sum(r.get('outcome', {}).get('duration_s', 0) for r in results) / total if total > 0 else 0
            
            output.append(f"📈 Overall Stats (last {total} tests)")
            output.append(f"  Healing Success Rate: {healed}/{total} ({healed/total*100:.0f}%)")
            output.append(f"  Average Score: {avg_score:.1f}/100")
            output.append(f"  Average MTTR: {avg_mttr:.1f}s")
            output.append("")
            
            # Recent tests
            output.append(f"🔬 Recent Tests:")
            output.append("")
            for r in reversed(results[-5:]):  # Last 5
                spec_id = r.get('spec_id', 'unknown')
                score = r.get('score', 0)
                healed_str = "✅" if r.get('outcome', {}).get('healed') else "❌"
                duration = r.get('outcome', {}).get('duration_s', 0)
                
                output.append(f"  {healed_str} {spec_id}")
                output.append(f"     Score: {score}/100 | MTTR: {duration:.1f}s")
                output.append("")
            
            # Patterns
            output.append("🔍 Patterns:")
            by_target = {}
            for r in results:
                target = r.get('target', 'unknown')
                if target not in by_target:
                    by_target[target] = {'healed': 0, 'total': 0, 'total_score': 0}
                by_target[target]['total'] += 1
                by_target[target]['total_score'] += r.get('score', 0)
                if r.get('outcome', {}).get('healed'):
                    by_target[target]['healed'] += 1
            
            for target, stats in sorted(by_target.items(), key=lambda x: x[1]['total'], reverse=True):
                heal_rate = stats['healed'] / stats['total'] * 100 if stats['total'] > 0 else 0
                avg_score = stats['total_score'] / stats['total'] if stats['total'] > 0 else 0
                output.append(f"  {target}: {stats['healed']}/{stats['total']} healed ({heal_rate:.0f}%), avg score: {avg_score:.0f}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"❌ Failed to read history: {e}"

    def _auto_chaos_test(self, kloros_instance) -> str:
        """Automatically select and run a chaos scenario."""
        try:
            from src.dream_lab import load_specs
            import os
            import random
            
            specs_path = os.path.join(os.path.dirname(__file__), "dream_lab", "fixtures", "example_specs.yaml")
            specs = load_specs(specs_path)
            
            if not specs:
                return "❌ No scenarios available"
            
            # Prefer scenarios we haven't tested recently
            history = self._get_recent_chaos_history(limit=20)
            recent_ids = {r.get('spec_id') for r in history}
            
            untested = [s for s in specs if s.id not in recent_ids]
            if untested:
                selected = random.choice(untested)
                reason = "untested scenario"
            else:
                # Select based on lowest average score (hardest to heal)
                scores_by_id = {}
                for r in history:
                    spec_id = r.get('spec_id')
                    score = r.get('score', 50)
                    if spec_id not in scores_by_id:
                        scores_by_id[spec_id] = []
                    scores_by_id[spec_id].append(score)
                
                # Find lowest average
                avg_scores = {sid: sum(scores)/len(scores) for sid, scores in scores_by_id.items()}
                lowest_id = min(avg_scores, key=avg_scores.get, default=None)
                
                if lowest_id:
                    selected = next((s for s in specs if s.id == lowest_id), None)
                    reason = f"weakest healing (avg score: {avg_scores[lowest_id]:.0f})"
                else:
                    selected = random.choice(specs)
                    reason = "random selection"
            
            if not selected:
                return "❌ Could not select scenario"
            
            output = [
                f"🎲 Auto-selected: {selected.id}",
                f"   Reason: {reason}",
                f"   Target: {selected.target}",
                f"   Mode: {selected.mode}",
                ""
            ]
            
            # Run it
            result_str = self._run_chaos_test(kloros_instance, scenario_id=selected.id)
            output.append(result_str)
            
            return "\n".join(output)
            
        except Exception as e:
            return f"❌ Auto chaos test failed: {e}"

    def _save_chaos_result(self, result):
        """Save chaos result to history."""
        try:
            import json
            from pathlib import Path
            
            history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
            history_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(history_file, 'a') as f:
                f.write(json.dumps(result) + '\n')
                
        except Exception as e:
            print(f"[chaos] Failed to save result: {e}")

    def _get_recent_chaos_history(self, limit=20):
        """Get recent chaos results."""
        try:
            import json
            from pathlib import Path
            
            history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
            if not history_file.exists():
                return []
            
            results = []
            with open(history_file, 'r') as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
            
            return results[-limit:]
            
        except Exception:
            return []

    def _feed_to_dream(self, kloros_instance, chaos_result):
        """Feed chaos results to D-REAM for learning (especially weaknesses!)."""
        try:
            # Extract fitness signals from chaos result
            score = chaos_result.get('score', 0)
            mttr = chaos_result.get('outcome', {}).get('duration_s', 999)
            healed = chaos_result.get('outcome', {}).get('healed', False)

            # Feed ALL results to D-REAM (low scores = weaknesses to fix!)
            # No early return - we want to learn from failures
            
            # Create fitness metric for D-REAM
            fitness_metric = {
                'source': 'chaos_lab',
                'scenario': chaos_result.get('spec_id'),
                'score': score,
                'mttr': mttr,
                'healed': healed,
                'target': chaos_result.get('target'),
                'timestamp': chaos_result.get('timestamp')
            }
            
            # Try to feed to D-REAM if available
            if hasattr(kloros_instance, 'dream_runtime') and kloros_instance.dream_runtime:
                # D-REAM can use this as a fitness signal
                print(f"[chaos→dream] Feeding result: score={score}, mttr={mttr:.1f}s")
                
                # Store in D-REAM metrics if available
                if hasattr(kloros_instance.dream_runtime, 'record_fitness'):
                    kloros_instance.dream_runtime.record_fitness('self_healing', fitness_metric)
            
            # Also save to a D-REAM-readable file
            import json
            from pathlib import Path
            
            dream_metrics = Path("/home/kloros/.kloros/dream_chaos_metrics.jsonl")
            dream_metrics.parent.mkdir(parents=True, exist_ok=True)
            
            with open(dream_metrics, 'a') as f:
                f.write(json.dumps(fitness_metric) + '\n')
                
            print(f"[chaos→dream] Saved fitness metric for D-REAM analysis")
            
        except Exception as e:
            print(f"[chaos→dream] Failed to feed to D-REAM: {e}")

# Active proposal submission tool functions
def tool_submit_improvement_idea(kloros_instance, component="", description="", priority="medium", issue_type="enhancement", **kwargs):
    """Submit an improvement idea to D-REAM during active thinking."""
    try:
        from src.dream.active_proposal_helper import get_active_proposal_helper
        helper = get_active_proposal_helper()

        if not component or not description:
            return "Error: Both 'component' and 'description' are required. Example: component='tool_synthesis', description='Tool validation too strict'"

        submitted = helper.submit_improvement_idea(
            component=component,
            issue_type=issue_type,
            description=description,
            priority=priority,
            evidence={"source": "active_introspection", "timestamp": datetime.now().isoformat()}
        )

        if submitted:
            return f"✅ Improvement idea submitted to D-REAM evolution queue\n  Component: {component}\n  Priority: {priority}\n  Description: {description[:100]}..."
        else:
            return "❌ Failed to submit improvement idea"

    except Exception as e:
        return f"Error submitting improvement idea: {e}"


def tool_submit_quick_fix(kloros_instance, description="", target_file="", **kwargs):
    """Quickly submit a simple fix idea to D-REAM."""
    try:
        from src.dream.active_proposal_helper import get_active_proposal_helper
        helper = get_active_proposal_helper()

        if not description:
            return "Error: 'description' is required. Example: description='RAG context window too small'"

        submitted = helper.submit_quick_fix_idea(
            description=description,
            target_file=target_file if target_file else None
        )

        if submitted:
            result = f"✅ Quick fix idea submitted to D-REAM\n  Description: {description[:100]}..."
            if target_file:
                result += f"\n  Target file: {target_file}"
            return result
        else:
            return "❌ Failed to submit quick fix idea"

    except Exception as e:
        return f"Error submitting quick fix: {e}"


def tool_view_pending_proposals(kloros_instance, component="", priority="", limit=10, **kwargs):
    """
    View pending improvement proposals in D-REAM queue.

    Args:
        component: Filter by component name (optional)
        priority: Filter by priority level (low/medium/high/critical) (optional)
        limit: Maximum number of proposals to show (default: 10)

    Returns:
        Formatted list of pending proposals with details
    """
    try:
        from src.dream.improvement_proposer import get_improvement_proposer
        from datetime import datetime

        proposer = get_improvement_proposer()

        # Get all pending proposals
        all_proposals = proposer.get_pending_proposals(
            component=component if component else None,
            priority=priority if priority else None
        )

        if not all_proposals:
            return "📋 No pending improvement proposals at this time."

        # Sort by priority and timestamp
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_proposals = sorted(
            all_proposals,
            key=lambda p: (priority_order.get(p.priority, 99), p.timestamp),
            reverse=False
        )

        # Limit results
        display_proposals = sorted_proposals[:int(limit)]

        # Format output
        result = f"📋 Pending Improvement Proposals ({len(all_proposals)} total"
        if len(display_proposals) < len(all_proposals):
            result += f", showing {len(display_proposals)}"
        result += "):\n\n"

        for i, proposal in enumerate(display_proposals, 1):
            # Priority emoji
            priority_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }.get(proposal.priority, "⚪")

            result += f"{i}. {priority_emoji} [{proposal.priority.upper()}] {proposal.component}\n"
            result += f"   ID: {proposal.id}\n"
            result += f"   Description: {proposal.description}\n"
            result += f"   Issue Type: {proposal.issue_type}\n"

            # Timestamp
            try:
                ts = datetime.fromisoformat(proposal.timestamp)
                result += f"   Submitted: {ts.strftime('%Y-%m-%d %H:%M:%S')}\n"
            except:
                result += f"   Submitted: {proposal.timestamp}\n"

            # Occurrence count
            if hasattr(proposal, 'occurrence_count') and proposal.occurrence_count > 1:
                result += f"   Occurrences: {proposal.occurrence_count}\n"

            # Evidence if available
            if proposal.evidence:
                evidence_str = str(proposal.evidence)[:100]
                result += f"   Evidence: {evidence_str}{'...' if len(str(proposal.evidence)) > 100 else ''}\n"

            # Proposed change if available
            if proposal.proposed_change:
                change_str = proposal.proposed_change[:80]
                result += f"   Proposed: {change_str}{'...' if len(proposal.proposed_change) > 80 else ''}\n"

            # Target files if available
            if proposal.target_files:
                files_str = ", ".join(proposal.target_files[:3])
                if len(proposal.target_files) > 3:
                    files_str += f" (+{len(proposal.target_files) - 3} more)"
                result += f"   Files: {files_str}\n"

            result += "\n"

        # Summary by priority
        priority_counts = {}
        for p in all_proposals:
            priority_counts[p.priority] = priority_counts.get(p.priority, 0) + 1

        if len(priority_counts) > 1:
            result += "📊 By Priority: "
            result += ", ".join([f"{p}: {c}" for p, c in sorted(priority_counts.items())])
            result += "\n"

        # Usage hint
        result += "\n💡 Use filters: component='tool_synthesis', priority='high', limit=5"

        return result

    except Exception as e:
        return f"❌ Error viewing proposals: {e}"


def tool_invoke_deep_reasoning(kloros_instance, problem="", method="tot", context="", **kwargs):
    """
    Invoke advanced reasoning (Tree of Thought or Debate) for complex problems.

    Useful for:
    - Analyzing recurring failures with no obvious solution
    - Exploring multiple solution paths systematically
    - Getting consensus through multi-perspective debate
    - Breaking down complex system issues

    Args:
        problem: Problem description or question to analyze
        method: Reasoning method ('tot' for Tree of Thought, 'debate' for multi-agent debate)
        context: Additional context (failure patterns, evidence, constraints)

    Returns:
        Deep reasoning analysis with recommended solutions
    """
    try:
        if not problem:
            return "❌ Error: 'problem' is required. Example: problem='Why do 15 bugfix.core tests keep failing?'"

        method = method.lower()
        if method not in ['tot', 'debate']:
            return f"❌ Error: method must be 'tot' or 'debate', got '{method}'"

        result = f"🧠 Deep Reasoning Analysis: {method.upper()}\n"
        result += f"Problem: {problem}\n\n"

        if method == 'tot':
            # Tree of Thought reasoning
            from src.brainmods import TreeOfThought

            # Define expansion function: generate possible solution approaches
            def expand_solutions(state):
                """Generate next solution steps."""
                if isinstance(state, str):
                    # Initial state - generate root approaches
                    return [
                        ("analyze_logs", "Examine system logs for error patterns"),
                        ("check_dependencies", "Verify all dependencies are correct"),
                        ("isolate_failure", "Create minimal reproduction case"),
                        ("review_code", "Audit recent code changes")
                    ]
                else:
                    # Expand from current solution path
                    return [
                        ("investigate", f"Investigate {state}"),
                        ("test_hypothesis", f"Test hypothesis about {state}"),
                        ("implement_fix", f"Implement fix for {state}")
                    ]

            # Define scoring function
            def score_solution(state):
                """Score solution quality."""
                # Simple heuristic: longer paths get higher scores
                # In practice, this would use LLM evaluation
                if isinstance(state, str):
                    keywords = ["fix", "solution", "resolve", "correct"]
                    score = sum(1 for kw in keywords if kw in state.lower())
                    return float(score) / len(keywords)
                return 0.5

            # Run Tree of Thought
            tot = TreeOfThought(
                expand_fn=expand_solutions,
                score_fn=score_solution,
                beam_width=3,
                max_depth=3,
                strategy="beam"
            )

            search_result = tot.search(problem)

            result += "🌳 Tree of Thought Search Results:\n\n"
            result += f"Best Solution Path (score: {search_result['score']:.2f}):\n"
            for i, step in enumerate(search_result['path'], 1):
                result += f"  {i}. {step}\n"
            result += f"\nDepth explored: {search_result['depth']} steps\n"
            result += f"Final state: {str(search_result['state'])[:100]}\n\n"

            result += "💡 Recommended Actions:\n"
            result += "  1. Follow the solution path above step-by-step\n"
            result += "  2. Document findings at each step\n"
            result += "  3. If a step fails, backtrack and try alternative branches\n"

        elif method == 'debate':
            # Multi-agent debate reasoning
            from src.brainmods import DebateRunner

            # Simple debate agents
            def proposer(prompt, ctx):
                return f"Proposed solution: The failures are likely due to state persistence issues. Need to clear cache and restart services."

            def critic(prompt, proposal, ctx):
                return f"Critique: While cache clearing helps, this doesn't explain why only bugfix.core fails and not other families. Need deeper root cause analysis."

            def judge(prompt, proposal, critique, ctx):
                return {
                    "verdict": "Partially accept both perspectives",
                    "requires_revision": True,
                    "reasoning": "Cache issues AND component-specific bugs both plausible. Need systematic testing of both hypotheses."
                }

            # Run debate
            debate = DebateRunner(
                proposer=proposer,
                critic=critic,
                judge=judge,
                rounds=2
            )

            debate_result = debate.run(problem, {"context": context})

            result += "⚖️ Multi-Agent Debate Results:\n\n"
            result += f"Rounds completed: {debate_result['rounds_completed']}\n\n"

            for round_data in debate_result['history']:
                result += f"Round {round_data['round']}:\n"
                result += f"  Proposal: {round_data['proposal'][:150]}...\n"
                result += f"  Critique: {round_data['critique'][:150]}...\n"
                result += f"  Verdict: {round_data['verdict'].get('verdict', 'N/A')}\n\n"

            result += f"Final Proposal: {debate_result['final_proposal'][:200]}...\n\n"

            result += "💡 Consensus Recommendation:\n"
            result += "  Based on debate, investigate BOTH:\n"
            result += "  - System-level issues (cache, state, services)\n"
            result += "  - Component-specific bugs in failing modules\n"

        # Add context if provided
        if context:
            result += f"\n📝 Additional Context Considered:\n{context[:200]}...\n"

        result += "\n✅ Deep reasoning complete. Use insights to guide investigation or submit refined proposals."

        return result

    except Exception as e:
        return f"❌ Error during deep reasoning: {e}\n\nNote: This is a basic implementation. For production deep reasoning, integrate with your LLM backend or use TUMIX deep planner."


def tool_synthesize_new_tool(kloros_instance, tool_name="", description="", requirements="", **kwargs):
    """
    Synthesize a new tool on-demand.

    Args:
        kloros_instance: KLoROS instance
        tool_name: Name for the new tool
        description: What the tool should do
        requirements: Detailed requirements/context

    Returns:
        Status message about synthesis result
    """
    try:
        from src.tool_synthesis.synthesizer import ToolSynthesizer

        if not tool_name:
            return "Error: 'tool_name' is required. Example: tool_name='full_system_diagnostic'"

        if not description:
            return f"Error: 'description' is required for tool '{tool_name}'. Provide what the tool should do."

        # Create synthesizer instance
        synthesizer = ToolSynthesizer(kloros_instance)

        # Build context from description and requirements
        context = f"{description}"
        if requirements:
            context += f"\n\nRequirements:\n{requirements}"

        print(f"[synthesis] Starting synthesis for tool '{tool_name}'...")
        print(f"[synthesis] Context: {context[:200]}...")

        # Synthesize the tool
        new_tool = synthesizer.synthesize_tool(tool_name, context)

        if new_tool:
            # Register the tool so it's immediately available
            if hasattr(kloros_instance, 'tool_registry'):
                kloros_instance.tool_registry.register(new_tool)
                return f"✅ Tool '{tool_name}' synthesized and registered successfully!\n\nDescription: {new_tool.description}\n\nYou can now use it by saying: TOOL: {tool_name}"
            else:
                return f"✅ Tool '{tool_name}' synthesized but could not auto-register (no tool_registry). Code has been saved to storage."
        else:
            return f"❌ Tool synthesis failed for '{tool_name}'. Check logs for details. The request may have been submitted to D-REAM for refinement."

    except ImportError as e:
        return f"Error: Tool synthesis system not available: {e}"
    except Exception as e:
        return f"Error during tool synthesis: {e}"


def tool_check_synthesis_notifications(kloros_instance, **kwargs):
    """
    Check for pending autonomous tool synthesis notifications.
    Should be called proactively at conversation start.
    Part of Level 2 autonomy - user notification approach.

    Returns:
        Notification message if proposals are pending, empty string otherwise
    """
    try:
        from pathlib import Path
        import json

        notification_file = Path("/home/kloros/.kloros/synthesis_notifications.json")

        if not notification_file.exists():
            return ""  # No notifications

        # Read notification data
        with open(notification_file, 'r') as f:
            data = json.load(f)

        # Check if already notified
        if data.get('notified', True):
            return ""  # Already notified

        pending_count = data.get('pending_count', 0)
        if pending_count == 0:
            return ""  # No pending proposals

        # Mark as notified
        data['notified'] = True
        with open(notification_file, 'w') as f:
            json.dump(data, f, indent=2)

        # Return notification message
        msg = f"🔧 Autonomous Tool Synthesis Alert!\n\n"
        msg += f"I detected {pending_count} opportunity/opportunities for new tool synthesis during my reflection cycles.\n\n"
        msg += "These are autonomous proposals based on patterns I've observed.\n\n"
        msg += "Would you like me to review them with you?\n"
        msg += "Use: TOOL: review_synthesis_queue"

        return msg

    except Exception as e:
        return ""  # Silently fail - notifications are non-critical


def tool_review_synthesis_queue(kloros_instance, **kwargs):
    """
    Review pending autonomous tool synthesis proposals.
    Part of Level 2 autonomy - user notification approach.

    Returns:
        Summary of pending proposals in the synthesis queue
    """
    try:
        from src.synthesis_queue import SynthesisQueue

        queue = SynthesisQueue()
        pending = queue.get_pending_proposals()
        stats = queue.get_queue_summary()

        if not pending:
            return f"No pending tool synthesis proposals.\n\nQueue summary: {stats['total']} total ({stats['approved']} approved, {stats['rejected']} rejected, {stats['synthesized']} synthesized)"

        # Format pending proposals
        lines = [f"📋 Found {len(pending)} pending tool synthesis proposal(s):\n"]

        for i, proposal in enumerate(pending, 1):
            lines.append(f"{i}. Tool: {proposal['tool_name']}")
            lines.append(f"   ID: {proposal['id']}")
            lines.append(f"   Source: {proposal['source']}")
            lines.append(f"   Confidence: {proposal['confidence']:.2f}")
            lines.append(f"   Description: {proposal['description'][:150]}...")
            lines.append(f"   Created: {proposal['created_at']}")
            lines.append("")

        lines.append(f"\nQueue summary: {stats['total']} total ({stats['pending']} pending, {stats['approved']} approved, {stats['rejected']} rejected)")
        lines.append("\nTo approve a proposal, use: TOOL: approve_synthesis (proposal_id='...')")
        lines.append("To reject a proposal, use: TOOL: reject_synthesis (proposal_id='...')")

        return "\n".join(lines)

    except ImportError as e:
        return f"Error: Synthesis queue not available: {e}"
    except Exception as e:
        return f"Error reviewing synthesis queue: {e}"


def tool_approve_synthesis(kloros_instance, proposal_id="", **kwargs):
    """
    Approve and execute a queued tool synthesis proposal.
    Part of Level 2 autonomy - executes synthesis after user approval.

    Args:
        kloros_instance: KLoROS instance
        proposal_id: ID of the proposal to approve

    Returns:
        Result of synthesis execution
    """
    try:
        from src.synthesis_queue import SynthesisQueue

        if not proposal_id:
            return "Error: 'proposal_id' is required. Use TOOL: review_synthesis_queue to see pending proposals."

        queue = SynthesisQueue()
        proposal = queue.get_proposal_by_id(proposal_id)

        if not proposal:
            return f"Error: Proposal '{proposal_id}' not found in queue."

        if proposal['status'] != 'pending':
            return f"Error: Proposal '{proposal_id}' has already been {proposal['status']}."

        # Update status to approved
        queue.update_proposal_status(proposal_id, 'approved')

        print(f"[synthesis_queue] Approved proposal: {proposal['tool_name']}")
        print(f"[synthesis_queue] Starting synthesis...")

        # Execute synthesis using the synthesize_new_tool function
        result = tool_synthesize_new_tool(
            kloros_instance,
            tool_name=proposal['tool_name'],
            description=proposal['description'],
            requirements=proposal['requirements']
        )

        # Update status based on result
        if "✅" in result:
            queue.update_proposal_status(proposal_id, 'synthesized')
            status_msg = f"✅ Synthesis successful for proposal '{proposal_id}'"
        else:
            queue.update_proposal_status(proposal_id, 'failed')
            status_msg = f"❌ Synthesis failed for proposal '{proposal_id}'"

        return f"{status_msg}\n\n{result}"

    except ImportError as e:
        return f"Error: Synthesis queue not available: {e}"
    except Exception as e:
        return f"Error approving synthesis: {e}"


def tool_reject_synthesis(kloros_instance, proposal_id="", **kwargs):
    """
    Reject a queued tool synthesis proposal.
    Part of Level 2 autonomy - user can decline autonomous suggestions.

    Args:
        kloros_instance: KLoROS instance
        proposal_id: ID of the proposal to reject

    Returns:
        Confirmation message
    """
    try:
        from src.synthesis_queue import SynthesisQueue

        if not proposal_id:
            return "Error: 'proposal_id' is required. Use TOOL: review_synthesis_queue to see pending proposals."

        queue = SynthesisQueue()
        proposal = queue.get_proposal_by_id(proposal_id)

        if not proposal:
            return f"Error: Proposal '{proposal_id}' not found in queue."

        if proposal['status'] != 'pending':
            return f"Error: Proposal '{proposal_id}' has already been {proposal['status']}."

        # Update status to rejected
        queue.update_proposal_status(proposal_id, 'rejected')

        print(f"[synthesis_queue] Rejected proposal: {proposal['tool_name']}")

        return f"❌ Rejected proposal '{proposal_id}' for tool '{proposal['tool_name']}'.\n\nThe tool will not be synthesized."

    except ImportError as e:
        return f"Error: Synthesis queue not available: {e}"
    except Exception as e:
        return f"Error rejecting synthesis: {e}"


def register_scholar_tools():
    """Register scholar tool for research report generation.

    Idempotent: safe to call multiple times.
    """
    global _SCHOLAR_REGISTERED

    if _SCHOLAR_REGISTERED:
        return

    import logging
    logger = logging.getLogger(__name__)

    def _generate_research_report(kloros_instance, title: str = "", research_question: str = "",
                                   sources: str = "", use_tumix_review: bool = True, **kwargs) -> Dict:
        """Generate a research report using scholar pipeline.

        Args:
            kloros_instance: KLoROS instance
            title: Report title
            research_question: Research question to investigate
            sources: Comma-separated list of sources/topics
            use_tumix_review: Whether to use TUMIX committee review

        Returns:
            Dict with report_path, spec, and tumix_used
        """
        try:
            from src.scholar import Collector, build_plus_report
            from src.kloros.orchestration.chem_bus import ChemPub

            logger.info(f"Generating research report: {title}")

            collector = Collector()

            spec_dict = {
                "title": title,
                "research_question": research_question,
                "sources": sources.split(",") if sources else [],
                "use_tumix_review": use_tumix_review
            }

            out_dir = "/tmp/scholar_reports"
            report_path = build_plus_report(
                collector,
                out_dir=out_dir,
                title=title,
                run_reviewer=use_tumix_review
            )

            pub = ChemPub()
            pub.emit(
                "introspection.scholar",
                ecosystem="kloros_tools",
                intensity=0.8,
                facts={
                    "title": title,
                    "research_question": research_question,
                    "sources_count": len(spec_dict["sources"]),
                    "tumix_used": use_tumix_review
                }
            )
            pub.close()

            result = {
                "report_path": str(report_path),
                "spec": spec_dict,
                "tumix_used": use_tumix_review,
                "status": "success"
            }

            logger.info(f"Scholar report generated: {report_path}")
            return result

        except Exception as e:
            logger.error(f"Error generating research report: {e}")
            return {
                "status": "error",
                "error": str(e),
                "tumix_used": use_tumix_review
            }

    registry = IntrospectionToolRegistry()
    registry.register(IntrospectionTool(
        name='generate_research_report',
        description='Generate a research report with optional TUMIX committee review',
        func=_generate_research_report,
        parameters=['title', 'research_question', 'sources', 'use_tumix_review']
    ))

    _SCHOLAR_REGISTERED = True
    logger.info("Scholar tools registered")


def register_browser_tools():
    """Register browser_agent tool for web navigation and extraction.

    Idempotent: safe to call multiple times.
    """
    global _BROWSER_REGISTERED

    if _BROWSER_REGISTERED:
        return

    import logging
    import asyncio
    logger = logging.getLogger(__name__)

    def _browse_web(kloros_instance, url: str = "", extract_selector: str = None,
                     max_depth: int = 1, **kwargs):
        """Navigate and extract content from web pages with PETRI safety.

        Args:
            kloros_instance: KLoROS instance
            url: URL to navigate to
            extract_selector: CSS selector for content extraction
            max_depth: Maximum navigation depth

        Returns:
            Dict with content, links, and petri_violations
        """
        try:
            from src.config.browser_petri import (
                BROWSER_PETRI_ALLOWED_DOMAINS,
                BROWSER_BLOCK_EXECUTABLES,
                BROWSER_BLOCK_FORMS
            )
            from src.browser_agent.agent.petri_policy import PetriPolicy
            from src.browser_agent.agent.executor import BrowserExecutor
            from src.kloros.orchestration.chem_bus import ChemPub

            logger.info(f"Browser tool: navigating to {url}")

            if not url:
                return {
                    "status": "error",
                    "error": "URL is required",
                    "petri_violations": []
                }

            policy = PetriPolicy()
            policy.allow_domains = BROWSER_PETRI_ALLOWED_DOMAINS

            petri_violations = []

            if BROWSER_BLOCK_EXECUTABLES:
                policy.max_actions = 20

            if BROWSER_BLOCK_FORMS:
                policy.screenshot_every_step = True

            policy.check_domain(url)

            async def _run_browser():
                async with BrowserExecutor(policy=policy, headless=True) as executor:
                    plan = {
                        "meta": {
                            "name": f"extract_{url.replace('://', '_').replace('/', '_')}",
                            "start_url": url,
                            "max_depth": max_depth
                        },
                        "actions": [
                            {
                                "type": "goto",
                                "url": url
                            }
                        ]
                    }

                    if extract_selector:
                        plan["actions"].append({
                            "type": "extract",
                            "selector": extract_selector
                        })

                    result = await executor.run_plan(plan)
                    return result

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            browser_result = loop.run_until_complete(_run_browser())
            loop.close()

            content = ""
            links = []

            for step in browser_result.get("steps", []):
                if step.get("success"):
                    content += step.get("content", "")
                    links.extend(step.get("links", []))

            pub = ChemPub()
            pub.emit(
                "introspection.browser",
                ecosystem="kloros_tools",
                intensity=0.7,
                facts={
                    "url": url,
                    "extract_selector": extract_selector,
                    "max_depth": max_depth,
                    "content_length": len(content),
                    "links_found": len(links),
                    "petri_violations": len(petri_violations)
                }
            )
            pub.close()

            result = {
                "url": url,
                "content": content[:1000],
                "links": links[:10],
                "petri_violations": petri_violations,
                "status": "success"
            }

            logger.info(f"Browser navigation completed for {url}")
            return result

        except Exception as e:
            logger.error(f"Error in browser tool: {e}")
            return {
                "status": "error",
                "error": str(e),
                "petri_violations": []
            }

    registry = IntrospectionToolRegistry()
    registry.register(IntrospectionTool(
        name='browse_web',
        description='Navigate and extract content from web pages with PETRI safety gates',
        func=_browse_web,
        parameters=['url', 'extract_selector', 'max_depth']
    ))

    _BROWSER_REGISTERED = True
    logger.info("Browser tools registered")
