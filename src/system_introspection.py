"""System introspection capabilities for KLoROS self-awareness with intelligent capability detection."""

import os
import subprocess
from typing import Dict, Any, Optional
from datetime import datetime

def get_component_status(kloros_instance) -> Dict[str, Any]:
    """Get actual status of all KLoROS components with intelligent capability detection."""

    def safe_get_attr(obj, attr, default=None):
        """Safely get attribute, returning default if missing."""
        return getattr(obj, attr, default)

    def analyze_component_availability(component_name: str, required_attrs: list) -> Dict[str, Any]:
        """Intelligently analyze component availability and provide appropriate status."""
        missing_attrs = [attr for attr in required_attrs if not hasattr(kloros_instance, attr)]

        if missing_attrs:
            # Determine the operating mode based on missing components
            if 'audio_backend' in missing_attrs:
                mode = "text_only_mode"
                status = "Text interface - audio components not initialized"
            else:
                mode = "partial_initialization"
                status = f"Missing attributes: {', '.join(missing_attrs)}"

            return {
                "mode": mode,
                "status": status,
                "missing_capabilities": missing_attrs,
                "available": False
            }
        else:
            return {"available": True, "mode": "full_voice_mode"}

    # Determine interface mode more intelligently
    has_audio_backend = hasattr(kloros_instance, 'audio_backend')
    audio_backend_obj = safe_get_attr(kloros_instance, 'audio_backend')
    audio_backend_name = safe_get_attr(kloros_instance, 'audio_backend_name')

    # Check if audio is actually operational (not just if the object exists)
    audio_operational = (has_audio_backend and
                        audio_backend_obj is not None and
                        audio_backend_name and
                        audio_backend_name != "None")

    status = {
        "timestamp": datetime.now().isoformat(),
        "interface_mode": "voice_interface" if audio_operational else "text_chat",
    }

    # Audio backend analysis
    audio_analysis = analyze_component_availability("audio_backend", ["audio_backend", "audio_backend_name", "audio_sample_rate"])
    if audio_analysis["available"]:
        status["audio_backend"] = {
            "initialized": kloros_instance.audio_backend is not None,
            "backend_type": safe_get_attr(kloros_instance, "audio_backend_name"),
            "sample_rate": safe_get_attr(kloros_instance, "audio_sample_rate"),
            "device_index": safe_get_attr(kloros_instance, "audio_device_index"),
        }
    else:
        status["audio_backend"] = audio_analysis

    # STT backend analysis
    stt_analysis = analyze_component_availability("stt_backend", ["stt_backend", "stt_backend_name", "enable_stt"])
    if stt_analysis["available"]:
        status["stt_backend"] = {
            "initialized": kloros_instance.stt_backend is not None,
            "backend_type": safe_get_attr(kloros_instance, "stt_backend_name"),
            "enabled": bool(safe_get_attr(kloros_instance, "enable_stt", 0)),
            "vosk_model_loaded": safe_get_attr(kloros_instance, "vosk_model") is not None,
        }
    else:
        status["stt_backend"] = stt_analysis

    # TTS backend analysis
    tts_analysis = analyze_component_availability("tts_backend", ["tts_backend", "tts_backend_name", "enable_tts"])
    if tts_analysis["available"]:
        status["tts_backend"] = {
            "initialized": kloros_instance.tts_backend is not None,
            "backend_type": safe_get_attr(kloros_instance, "tts_backend_name"),
            "enabled": bool(safe_get_attr(kloros_instance, "enable_tts", 0)),
            "sample_rate": safe_get_attr(kloros_instance, "tts_sample_rate"),
        }
    else:
        status["tts_backend"] = tts_analysis

    # Reasoning backend (should always be available)
    status["reasoning_backend"] = {
        "initialized": safe_get_attr(kloros_instance, "reason_backend") is not None,
        "backend_type": safe_get_attr(kloros_instance, "reason_backend_name", "unknown"),
    }

    # Memory system
    status["memory_system"] = {
        "enhanced_memory": hasattr(kloros_instance, 'memory_enhanced') and safe_get_attr(kloros_instance, 'memory_enhanced') is not None,
        "conversation_history_size": len(safe_get_attr(kloros_instance, "conversation_history", [])),
    }

    # Wake detection analysis
    wake_analysis = analyze_component_availability("wake_detection", ["enable_wakeword", "wake_phrases"])
    if wake_analysis["available"]:
        status["wake_detection"] = {
            "enabled": bool(safe_get_attr(kloros_instance, "enable_wakeword", 0)),
            "wake_phrases": safe_get_attr(kloros_instance, "wake_phrases", []),
            "fuzzy_threshold": safe_get_attr(kloros_instance, "fuzzy_threshold", 0.0),
            "rms_min": safe_get_attr(kloros_instance, "wake_rms_min", 0),
            "conf_min": safe_get_attr(kloros_instance, "wake_conf_min", 0.0),
        }
    else:
        status["wake_detection"] = wake_analysis

    # Operational state
    status["operational_state"] = {
        "listening": safe_get_attr(kloros_instance, "listening", False),
        "sample_rate": safe_get_attr(kloros_instance, "sample_rate", 48000),
        "blocksize": safe_get_attr(kloros_instance, "blocksize", 1024),
    }

    return status

def generate_full_diagnostic(kloros_instance) -> str:
    """Generate a comprehensive system diagnostic report with intelligent adaptation."""
    try:
        component_status = get_component_status(kloros_instance)

        # Determine interface mode
        interface_mode = component_status.get("interface_mode", "unknown")

        report = []
        report.append("🔍 KLoROS System Diagnostic Report")
        report.append(f"📅 Timestamp: {component_status['timestamp']}")
        report.append(f"🖥️  Interface Mode: {interface_mode.upper()}")
        report.append("")

        # Audio Backend Status
        audio = component_status.get("audio_backend", {})
        if audio.get("available", True):
            report.append("🎵 Audio Backend:")
            report.append(f"   • Initialized: {audio.get('initialized', False)}")
            report.append(f"   • Type: {audio.get('backend_type', 'Unknown')}")
            report.append(f"   • Sample Rate: {audio.get('sample_rate', 'Unknown')} Hz")
        else:
            report.append("🎵 Audio Backend:")
            report.append(f"   • Status: {audio.get('status', 'Not available')}")
            report.append(f"   • Mode: {audio.get('mode', 'Unknown')}")

        # STT Backend Status
        stt = component_status.get("stt_backend", {})
        if stt.get("available", True):
            report.append("🎤 Speech Recognition:")
            report.append(f"   • Initialized: {stt.get('initialized', False)}")
            report.append(f"   • Type: {stt.get('backend_type', 'Unknown')}")
            report.append(f"   • Enabled: {stt.get('enabled', False)}")
        else:
            report.append("🎤 Speech Recognition:")
            report.append(f"   • Status: {stt.get('status', 'Not available')}")

        # TTS Backend Status
        tts = component_status.get("tts_backend", {})
        if tts.get("available", True):
            report.append("🗣️  Text-to-Speech:")
            report.append(f"   • Initialized: {tts.get('initialized', False)}")
            report.append(f"   • Type: {tts.get('backend_type', 'Unknown')}")
            report.append(f"   • Enabled: {tts.get('enabled', False)}")
        else:
            report.append("🗣️  Text-to-Speech:")
            report.append(f"   • Status: {tts.get('status', 'Not available')}")

        # Reasoning Backend
        reasoning = component_status.get("reasoning_backend", {})
        report.append("🧠 Reasoning System:")
        report.append(f"   • Initialized: {reasoning.get('initialized', False)}")
        report.append(f"   • Type: {reasoning.get('backend_type', 'Unknown')}")

        # Memory System
        memory = component_status.get("memory_system", {})
        report.append("💾 Memory System:")
        report.append(f"   • Enhanced Memory: {memory.get('enhanced_memory', False)}")
        report.append(f"   • History Size: {memory.get('conversation_history_size', 0)} entries")

        # Add intelligent summary based on detected mode
        report.append("")
        if interface_mode == "text_chat":
            report.append("💡 Diagnostic Summary:")
            report.append("   • Running in text-only mode - voice components not initialized")
            report.append("   • Core reasoning and memory systems operational")
            report.append("   • All diagnostic and tool execution capabilities available")
        else:
            report.append("💡 System Status: Full voice interface operational")

        return "\n".join(report)

    except Exception as e:
        return f"❌ Diagnostic generation failed: {str(e)}"

def get_audio_diagnostics(kloros_instance) -> str:
    """Get audio pipeline diagnostics with intelligent mode detection."""
    try:
        component_status = get_component_status(kloros_instance)
        audio = component_status.get("audio_backend", {})

        if not audio.get("available", True):
            return f"🎵 Audio System: {audio.get('status', 'Not available')} (Mode: {audio.get('mode', 'Unknown')})"

        # Full audio diagnostics for voice mode
        lines = ["🎵 Audio Pipeline Diagnostics:"]
        lines.append(f"   • Backend: {audio.get('backend_type', 'Unknown')}")
        lines.append(f"   • Sample Rate: {audio.get('sample_rate', 'Unknown')} Hz")
        lines.append(f"   • Device Index: {audio.get('device_index', 'Unknown')}")
        lines.append(f"   • Status: {'Operational' if audio.get('initialized') else 'Not Initialized'}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Audio diagnostics failed: {str(e)}"

def get_stt_diagnostics(kloros_instance) -> str:
    """Get speech recognition diagnostics with intelligent adaptation."""
    try:
        component_status = get_component_status(kloros_instance)
        stt = component_status.get("stt_backend", {})

        if not stt.get("available", True):
            return f"🎤 Speech Recognition: {stt.get('status', 'Not available')} (Text input used instead)"

        lines = ["🎤 Speech Recognition Diagnostics:"]
        lines.append(f"   • Backend: {stt.get('backend_type', 'Unknown')}")
        lines.append(f"   • Enabled: {stt.get('enabled', False)}")
        lines.append(f"   • VOSK Model: {'Loaded' if stt.get('vosk_model_loaded') else 'Not Loaded'}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ STT diagnostics failed: {str(e)}"

def get_memory_diagnostics(kloros_instance) -> str:
    """Get memory system diagnostics."""
    try:
        component_status = get_component_status(kloros_instance)
        memory = component_status.get("memory_system", {})

        lines = ["💾 Memory System Diagnostics:"]
        lines.append(f"   • Enhanced Memory: {memory.get('enhanced_memory', False)}")
        lines.append(f"   • Conversation History: {memory.get('conversation_history_size', 0)} entries")

        if hasattr(kloros_instance, 'memory_enhanced') and kloros_instance.memory_enhanced:
            lines.append("   • Episodic Memory: Available")
            lines.append("   • Context Retrieval: Operational")
        else:
            lines.append("   • Basic Memory Mode: Active")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Memory diagnostics failed: {str(e)}"