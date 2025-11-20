#!/usr/bin/env python3
"""
kloros-map: System Capability Mapper

Shows current KLoROS capabilities, active modules, and system status.
"""

import json
import sys
import os
from pathlib import Path

def get_active_modules():
    """Detect active KLoROS modules."""
    modules = {
        "Audio (STT)": check_audio_system(),
        "Audio (TTS)": check_tts_system(),
        "Memory (Episodic)": check_memory_system(),
        "RAG (Knowledge)": check_rag_system(),
        "D-REAM (Evolution)": check_dream_system(),
        "Synthesis (Tool Gen)": check_synthesis_system(),
        "Reflection": check_reflection_system(),
        "MQTT Integration": check_mqtt_system(),
    }
    return modules

def check_audio_system():
    """Check if audio system is configured."""
    return os.path.exists("/home/kloros/.kloros/audio.conf")

def check_tts_system():
    """Check if TTS is available."""
    return os.path.exists("/usr/bin/piper") or os.path.exists("/home/kloros/.venv/bin/piper")

def check_memory_system():
    """Check if memory database exists."""
    return os.path.exists("/home/kloros/.kloros/memory.db")

def check_rag_system():
    """Check if RAG is configured."""
    return os.path.exists("/home/kloros/.kloros/rag_index")

def check_dream_system():
    """Check if D-REAM ledger exists."""
    return os.path.exists("/home/kloros/var/dream/ledger.jsonl")

def check_synthesis_system():
    """Check if synthesis is active."""
    return os.path.exists("/home/kloros/.kloros/synth")

def check_reflection_system():
    """Check if reflection is configured."""
    return os.path.exists("/home/kloros/src/idle_reflection")

def check_mqtt_system():
    """Check if MQTT is configured."""
    # Check for MQTT broker config
    return os.path.exists("/home/kloros/.kloros/mqtt.conf")

def get_tool_count():
    """Count synthesized tools."""
    synth_dir = Path("/home/kloros/.kloros/synth")
    if not synth_dir.exists():
        return 0
    
    count = 0
    for tool_dir in synth_dir.iterdir():
        if tool_dir.is_dir() and (tool_dir / "manifest.json").exists():
            count += 1
    return count

def get_promotion_stats():
    """Get tool promotion statistics."""
    evidence_dir = Path("/home/kloros/.kloros/synth/evidence")
    if not evidence_dir.exists():
        return {"promoted": 0, "total": 0}
    
    promoted = 0
    total = 0
    
    for tool_dir in evidence_dir.iterdir():
        if not tool_dir.is_dir():
            continue
        for version_dir in tool_dir.iterdir():
            if not version_dir.is_dir():
                continue
            bundle_path = version_dir / "bundle.json"
            if bundle_path.exists():
                try:
                    with open(bundle_path) as f:
                        bundle = json.load(f)
                    total += 1
                    if bundle.get("decision", {}).get("promoted", False):
                        promoted += 1
                except (json.JSONDecodeError, IOError):
                    pass
    
    return {"promoted": promoted, "total": total}

def format_output(modules, tool_count, promo_stats):
    """Format capability map output."""
    lines = []
    lines.append("=== KLoROS Capability Map ===\n")
    
    lines.append("Active Modules:")
    for module, active in modules.items():
        status = "✓" if active else "✗"
        lines.append(f"  {status} {module}")
    
    lines.append(f"\nSynthesized Tools: {tool_count}")
    
    if promo_stats["total"] > 0:
        lines.append(f"  Promoted: {promo_stats['promoted']}/{promo_stats['total']} " + 
                    f"({int(promo_stats['promoted']/promo_stats['total']*100)}%)")
    
    lines.append("\nCapabilities:")
    if modules["Audio (STT)"]:
        lines.append("  • Voice interaction (VOSK + Whisper hybrid)")
    if modules["Audio (TTS)"]:
        lines.append("  • Speech synthesis (Piper TTS)")
    if modules["Memory (Episodic)"]:
        lines.append("  • Long-term memory with episodic recall")
    if modules["RAG (Knowledge)"]:
        lines.append("  • Knowledge base with vector search")
    if modules["D-REAM (Evolution)"]:
        lines.append("  • Evolutionary self-improvement")
    if modules["Synthesis (Tool Gen)"]:
        lines.append("  • Dynamic tool synthesis and promotion")
    if modules["Reflection"]:
        lines.append("  • Meta-cognitive self-reflection")
    if modules["MQTT Integration"]:
        lines.append("  • MQTT event bus integration")
    
    lines.append("")
    return "\n".join(lines)

def main():
    modules = get_active_modules()
    tool_count = get_tool_count()
    promo_stats = get_promotion_stats()
    
    output = format_output(modules, tool_count, promo_stats)
    print(output)
    
    # Optionally output JSON for programmatic use
    if "--json" in sys.argv:
        json_output = {
            "modules": modules,
            "tool_count": tool_count,
            "promotion_stats": promo_stats
        }
        print(json.dumps(json_output, indent=2))

if __name__ == "__main__":
    main()
