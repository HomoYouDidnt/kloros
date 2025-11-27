#!/usr/bin/env python3
"""
kloros-ux: UX Analysis and Feedback

Analyzes user experience aspects and provides actionable UX improvements.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

def analyze_response_times():
    """Analyze response latency and suggest improvements."""
    suggestions = []
    
    # Check if logs exist
    ops_log = Path("/home/kloros/.kloros/ops.log")
    if not ops_log.exists():
        return suggestions
    
    # In production, parse logs for response times
    # For now, provide general guidance
    suggestions.append({
        "area": "latency",
        "impact": "high",
        "title": "Monitor response latency",
        "issue": "User experience depends on sub-second response times",
        "recommendation": "Implement P95/P99 latency tracking for all interactions",
        "metric": "Target: <500ms for text, <2s for audio"
    })
    
    return suggestions

def analyze_wake_word_ux():
    """Analyze wake word detection UX."""
    suggestions = []
    
    audio_conf = Path("/home/kloros/.kloros/audio.conf")
    if not audio_conf.exists():
        return suggestions
    
    suggestions.append({
        "area": "wake_word",
        "impact": "medium",
        "title": "Optimize wake word sensitivity",
        "issue": "Balance between false positives and missed detections",
        "recommendation": "Review VAD thresholds and adjust based on environment noise",
        "metric": "Target: >95% detection rate, <5% false positive"
    })
    
    return suggestions

def analyze_conversation_flow():
    """Analyze conversation continuity and context."""
    suggestions = []
    
    memory_db = Path("/home/kloros/.kloros/memory.db")
    if not memory_db.exists():
        suggestions.append({
            "area": "conversation",
            "impact": "high",
            "title": "Enable conversation memory",
            "issue": "Without memory, context is lost between interactions",
            "recommendation": "Initialize episodic memory system for conversation continuity",
            "metric": "Target: 100% context retention within session"
        })
        return suggestions
    
    # Check for recent conversations
    try:
        import sqlite3
        import time
        
        conn = sqlite3.connect(str(memory_db), timeout=2.0)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM events 
            WHERE event_type = 'user_input' 
            AND timestamp > ?
        """, (time.time() - 86400,))
        
        recent_inputs = cursor.fetchone()[0]
        conn.close()
        
        if recent_inputs == 0:
            suggestions.append({
                "area": "engagement",
                "impact": "medium",
                "title": "Low recent user engagement",
                "issue": "No user inputs recorded in last 24 hours",
                "recommendation": "Check if KLoROS is accessible and prompting is clear",
                "metric": "Target: Daily active engagement"
            })
        
    except Exception:
        pass
    
    return suggestions

def analyze_feedback_mechanisms():
    """Analyze user feedback collection."""
    suggestions = []
    
    suggestions.append({
        "area": "feedback",
        "impact": "medium",
        "title": "Implement explicit feedback collection",
        "issue": "Limited data on user satisfaction with responses",
        "recommendation": "Add thumbs up/down or rating system after responses",
        "metric": "Target: Collect feedback on 20%+ of interactions"
    })
    
    return suggestions

def analyze_accessibility():
    """Analyze accessibility features."""
    suggestions = []
    
    # Check TTS availability
    if not (os.path.exists("/usr/bin/piper") or 
            os.path.exists("/home/kloros/.venv/bin/piper")):
        suggestions.append({
            "area": "accessibility",
            "impact": "high",
            "title": "Enable text-to-speech",
            "issue": "TTS not available limits accessibility",
            "recommendation": "Install Piper TTS for voice output",
            "metric": "Target: 100% response coverage with voice option"
        })
    
    # Check for visual indicators
    suggestions.append({
        "area": "accessibility",
        "impact": "low",
        "title": "Add visual status indicators",
        "issue": "Users may not know when KLoROS is listening or processing",
        "recommendation": "Implement LED or display indicators for system state",
        "metric": "Target: Clear state visibility at all times"
    })
    
    return suggestions

def analyze_error_handling():
    """Analyze error handling and user communication."""
    suggestions = []
    
    ops_log = Path("/home/kloros/.kloros/ops.log")
    if ops_log.exists():
        # In production, parse for error patterns
        suggestions.append({
            "area": "error_handling",
            "impact": "medium",
            "title": "Improve error message clarity",
            "issue": "Technical errors may confuse users",
            "recommendation": "Translate system errors into user-friendly explanations",
            "metric": "Target: All errors have user-facing messages"
        })
    
    return suggestions

def format_ux_report(all_suggestions):
    """Format UX suggestions into readable report."""
    if not all_suggestions:
        return "✓ UX appears well-optimized. No critical issues detected.\n"
    
    # Sort by impact
    impact_order = {"high": 0, "medium": 1, "low": 2}
    all_suggestions.sort(key=lambda s: impact_order.get(s["impact"], 99))
    
    lines = []
    lines.append("=== KLoROS UX Analysis Report ===\n")
    
    # Group by impact
    by_impact = {"high": [], "medium": [], "low": []}
    for sug in all_suggestions:
        by_impact[sug["impact"]].append(sug)
    
    for impact in ["high", "medium", "low"]:
        if not by_impact[impact]:
            continue
        
        impact_icon = {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}[impact]
        lines.append(f"\n{impact_icon} IMPACT\n{'-' * 40}")
        
        for sug in by_impact[impact]:
            lines.append(f"\n[{sug['area'].upper()}] {sug['title']}")
            lines.append(f"Issue: {sug['issue']}")
            lines.append(f"Recommendation: {sug['recommendation']}")
            lines.append(f"Success Metric: {sug['metric']}")
    
    lines.append("")
    return "\n".join(lines)

def main():
    all_suggestions = []
    
    # Gather UX suggestions
    all_suggestions.extend(analyze_response_times())
    all_suggestions.extend(analyze_wake_word_ux())
    all_suggestions.extend(analyze_conversation_flow())
    all_suggestions.extend(analyze_feedback_mechanisms())
    all_suggestions.extend(analyze_accessibility())
    all_suggestions.extend(analyze_error_handling())
    
    report = format_ux_report(all_suggestions)
    print(report)
    
    # JSON output
    if "--json" in sys.argv:
        print(json.dumps(all_suggestions, indent=2))
    
    # Summary stats
    impact_counts = {}
    for sug in all_suggestions:
        impact_counts[sug["impact"]] = impact_counts.get(sug["impact"], 0) + 1
    
    if all_suggestions:
        print("\nSummary:")
        print(f"  Total suggestions: {len(all_suggestions)}")
        for impact in ["high", "medium", "low"]:
            if impact in impact_counts:
                print(f"  {impact.title()} impact: {impact_counts[impact]}")

if __name__ == "__main__":
    main()
