"""
Tool templates and patterns for KLoROS tool synthesis.

Provides templates for common tool categories to guide code generation.
"""

from typing import Dict, List, Optional
import re


class ToolTemplateEngine:
    """Engine for selecting and applying tool templates."""

    def __init__(self):
        self.templates = self._initialize_templates()

    def select_template(self, tool_name: str, analysis: Dict) -> Dict:
        """
        Select the most appropriate template for a tool.

        Args:
            tool_name: Name of the tool being synthesized
            analysis: Tool analysis from LLM

        Returns:
            Template dictionary with implementation guidance
        """
        category = analysis.get('category', 'utility')

        # Select template based on category and tool name patterns
        if category == 'audio':
            return self._select_audio_template(tool_name, analysis)
        elif category == 'system':
            return self._select_system_template(tool_name, analysis)
        elif category == 'user_management':
            return self._select_user_management_template(tool_name, analysis)
        else:
            return self.templates['utility']['basic']

    def _select_audio_template(self, tool_name: str, analysis: Dict) -> Dict:
        """Select template for audio-related tools."""

        name_lower = tool_name.lower()

        # Audio analysis tools
        if any(keyword in name_lower for keyword in ['analysis', 'analyze', 'detect']):
            return self.templates['audio']['analysis']

        # Audio processing tools
        elif any(keyword in name_lower for keyword in ['process', 'filter', 'enhance']):
            return self.templates['audio']['processing']

        # Audio capture/recording tools
        elif any(keyword in name_lower for keyword in ['capture', 'record', 'input']):
            return self.templates['audio']['capture']

        # Audio playback/output tools
        elif any(keyword in name_lower for keyword in ['play', 'output', 'speak']):
            return self.templates['audio']['playback']

        # Voice recognition tools
        elif any(keyword in name_lower for keyword in ['voice', 'recognition', 'speaker']):
            return self.templates['audio']['voice_recognition']

        # Default audio template
        else:
            return self.templates['audio']['status']

    def _select_system_template(self, tool_name: str, analysis: Dict) -> Dict:
        """Select template for system-related tools."""

        name_lower = tool_name.lower()

        # Diagnostic tools
        if any(keyword in name_lower for keyword in ['diagnostic', 'status', 'health']):
            return self.templates['system']['diagnostic']

        # Error resolution tools
        elif any(keyword in name_lower for keyword in ['error', 'resolve', 'fix', 'repair']):
            return self.templates['system']['error_resolution']

        # System control tools
        elif any(keyword in name_lower for keyword in ['control', 'manage', 'configure']):
            return self.templates['system']['control']

        # Default system template
        else:
            return self.templates['system']['info']

    def _select_user_management_template(self, tool_name: str, analysis: Dict) -> Dict:
        """Select template for user management tools."""

        name_lower = tool_name.lower()

        # User verification tools
        if any(keyword in name_lower for keyword in ['verify', 'validate', 'check']):
            return self.templates['user_management']['verification']

        # Enrollment tools
        elif any(keyword in name_lower for keyword in ['enroll', 'register', 'add']):
            return self.templates['user_management']['enrollment']

        # User lookup tools
        elif any(keyword in name_lower for keyword in ['lookup', 'find', 'search']):
            return self.templates['user_management']['lookup']

        # Default user management template
        else:
            return self.templates['user_management']['info']

    def _initialize_templates(self) -> Dict:
        """Initialize all tool templates."""

        return {
            'audio': {
                'status': {
                    'name': 'audio_status',
                    'implementation_guide': '''
Access audio backend status via kloros_instance.audio_backend.
Check device configuration, sample rates, and connection status.
Return formatted status information with KLoROS personality.
                    ''',
                    'example_apis': [
                        'kloros_instance.audio_backend.get_device_info()',
                        'kloros_instance.audio_backend.sample_rate',
                        'kloros_instance.audio_backend.device_index'
                    ]
                },
                'analysis': {
                    'name': 'audio_analysis',
                    'implementation_guide': '''
Analyze audio data from recent captures or memory.
Use signal processing techniques for analysis.
Return insights about audio characteristics, quality, patterns.
                    ''',
                    'example_apis': [
                        'kloros_instance.audio_backend.get_recent_audio()',
                        'kloros_instance.memory_system.get_audio_events()',
                        'numpy.fft for frequency analysis'
                    ]
                },
                'processing': {
                    'name': 'audio_processing',
                    'implementation_guide': '''
Process audio signals for enhancement or modification.
Apply filters, normalization, or other processing.
Return processed audio information or status.
                    ''',
                    'example_apis': [
                        'kloros_instance.audio_backend.get_audio_level()',
                        'kloros_instance.audio_backend.set_input_gain()',
                        'numpy for audio math operations',
                        'librosa for advanced audio processing',
                        'faster_whisper for speech analysis'
                    ]
                },
                'capture': {
                    'name': 'audio_capture',
                    'implementation_guide': '''
Control audio capture functionality.
Start/stop recordings, adjust capture parameters.
Return capture status and configuration info.
                    ''',
                    'example_apis': [
                        'kloros_instance.audio_backend.start_capture()',
                        'kloros_instance.audio_backend.stop_capture()',
                        'kloros_instance.audio_backend.capture_duration'
                    ]
                },
                'playback': {
                    'name': 'audio_playback',
                    'implementation_guide': '''
Control audio playback functionality.
Manage TTS output, audio file playback.
Return playback status and queue information.
                    ''',
                    'example_apis': [
                        'kloros_instance.tts_backend.speak()',
                        'kloros_instance.tts_backend.queue_status',
                        'os.system for audio file playback'
                    ]
                },
                'voice_recognition': {
                    'name': 'voice_recognition',
                    'implementation_guide': '''
Enhance voice recognition capabilities.
Access speaker recognition, voice profiling.
Return recognition accuracy and user identification.
                    ''',
                    'example_apis': [
                        'kloros_instance.speaker_backend.identify_speaker()',
                        'kloros_instance.speaker_backend.get_profiles()',
                        'kloros_instance.stt_backend.confidence_score'
                    ]
                }
            },
            'system': {
                'diagnostic': {
                    'name': 'system_diagnostic',
                    'implementation_guide': '''
Perform comprehensive system diagnostics.
Check component health, resource usage, errors.
Return detailed diagnostic report with actionable insights.
                    ''',
                    'example_apis': [
                        'kloros_instance.tool_registry.get_tool("system_diagnostic")',
                        'psutil for system metrics',
                        'os.path.exists for file checks'
                    ]
                },
                'error_resolution': {
                    'name': 'error_resolution',
                    'implementation_guide': '''
Analyze and resolve system errors.
Identify error patterns, suggest fixes.
Return resolution steps and success probability.
                    ''',
                    'example_apis': [
                        'kloros_instance.memory_system.get_error_events()',
                        'traceback for error analysis',
                        'subprocess for system commands'
                    ]
                },
                'control': {
                    'name': 'system_control',
                    'implementation_guide': '''
Control system parameters and configuration.
Adjust settings, restart services, manage resources.
Return control action results and system response.
                    ''',
                    'example_apis': [
                        'os.environ for environment variables',
                        'subprocess.run for system commands',
                        'systemctl for service management'
                    ]
                },
                'info': {
                    'name': 'system_info',
                    'implementation_guide': '''
Provide system information and status.
Report uptime, versions, configurations.
Return formatted system information with personality.
                    ''',
                    'example_apis': [
                        'platform.system() for OS info',
                        'psutil.virtual_memory() for memory',
                        'os.uname() for system details'
                    ]
                }
            },
            'user_management': {
                'verification': {
                    'name': 'user_verification',
                    'implementation_guide': '''
Verify user identity and credentials.
Check voice profiles, enrollment status.
Return verification results and confidence.
                    ''',
                    'example_apis': [
                        'kloros_instance.speaker_backend.verify_speaker()',
                        'kloros_instance.enrollment_mode',
                        'json.load for user database'
                    ]
                },
                'enrollment': {
                    'name': 'user_enrollment',
                    'implementation_guide': '''
Manage user enrollment processes.
Control enrollment flow, save voice samples.
Return enrollment progress and status.
                    ''',
                    'example_apis': [
                        'kloros_instance._start_enrollment()',
                        'kloros_instance.enrollment_state',
                        'kloros_instance.speaker_backend.enroll_user()'
                    ]
                },
                'lookup': {
                    'name': 'user_lookup',
                    'implementation_guide': '''
Look up user information and profiles.
Search user database, retrieve profiles.
Return user details and interaction history.
                    ''',
                    'example_apis': [
                        'kloros_instance.speaker_backend.get_user_profiles()',
                        'kloros_instance.memory_system.get_user_events()',
                        'json.load for user data'
                    ]
                },
                'info': {
                    'name': 'user_info',
                    'implementation_guide': '''
Provide user management information.
Report enrolled users, active sessions.
Return formatted user management status.
                    ''',
                    'example_apis': [
                        'kloros_instance.speaker_backend.list_users()',
                        'kloros_instance.conversation_flow.active_user',
                        'len() for user counts'
                    ]
                }
            },
            'utility': {
                'basic': {
                    'name': 'utility_basic',
                    'implementation_guide': '''
Provide utility functionality based on tool purpose.
Implement specific utility logic as needed.
Return helpful results maintaining KLoROS personality.
                    ''',
                    'example_apis': [
                        'datetime for time operations',
                        'math for calculations',
                        'json for data processing'
                    ]
                }
            }
        }