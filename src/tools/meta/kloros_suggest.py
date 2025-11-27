#!/usr/bin/env python3
"""
kloros-suggest: Improvement Suggestion System

Analyzes system state and suggests actionable improvements.
"""

import json
import sys
import os
from pathlib import Path
from collections import Counter
from datetime import datetime, timedelta

def analyze_test_coverage():
    """Analyze test pass rates and suggest improvements."""
    suggestions = []
    
    # Placeholder - in production would parse pytest cache
    # For now, use known test stats from metrics
    test_families = {
        "dream_e2e": {"total": 25, "passed": 10, "pass_rate": 0.4}
    }
    
    for family, stats in test_families.items():
        if stats["pass_rate"] < 0.6:
            suggestions.append({
                "category": "testing",
                "priority": "medium",
                "title": f"Improve {family} test reliability",
                "description": f"Pass rate is {int(stats['pass_rate']*100)}% ({stats['passed']}/{stats['total']}). " + 
                              f"Consider adding error handling or adjusting test expectations.",
                "action": f"Review failing tests in {family} family"
            })
    
    return suggestions

def analyze_tool_promotions():
    """Analyze tool promotion pipeline and suggest improvements."""
    suggestions = []
    
    evidence_dir = Path("/home/kloros/.kloros/synth/evidence")
    if not evidence_dir.exists():
        return suggestions
    
    declined_reasons = Counter()
    low_win_rate_tools = []
    
    for tool_dir in evidence_dir.iterdir():
        if not tool_dir.is_dir():
            continue
        for version_dir in tool_dir.iterdir():
            bundle_path = version_dir / "bundle.json"
            if not bundle_path.exists():
                continue
            
            try:
                with open(bundle_path) as f:
                    bundle = json.load(f)
                
                decision = bundle.get("decision", {})
                perf = bundle.get("performance", {})
                
                if not decision.get("promoted", False):
                    reason = decision.get("decision_reason", "unknown")
                    declined_reasons[reason] += 1
                
                win_rate = perf.get("win_rate", 0.0)
                if 0 < win_rate < 0.6:
                    low_win_rate_tools.append({
                        "tool": bundle.get("tool_name"),
                        "version": bundle.get("version"),
                        "win_rate": win_rate
                    })
                    
            except (json.JSONDecodeError, IOError):
                pass
    
    # Suggest based on common decline reasons
    if declined_reasons:
        top_reason = declined_reasons.most_common(1)[0]
        suggestions.append({
            "category": "synthesis",
            "priority": "medium",
            "title": f"Address common promotion blocker: {top_reason[0]}",
            "description": f"{top_reason[1]} tools failed promotion due to '{top_reason[0]}'. " +
                          f"Review promotion gates and tool synthesis quality.",
            "action": "Adjust synthesis templates or promotion thresholds"
        })
    
    # Suggest for low win rate tools
    if low_win_rate_tools:
        suggestions.append({
            "category": "synthesis",
            "priority": "low",
            "title": f"Review {len(low_win_rate_tools)} low-performing tools",
            "description": "Several tools have win rates below 60%. Consider retiring or improving them.",
            "action": "Run analysis on low-performing tools"
        })
    
    return suggestions

def analyze_system_resources():
    """Analyze system resource usage and suggest optimizations."""
    suggestions = []
    
    try:
        import psutil
        
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        if mem.percent > 85:
            suggestions.append({
                "category": "performance",
                "priority": "high",
                "title": "High memory usage detected",
                "description": f"Memory usage at {mem.percent:.1f}%. Consider freeing resources or upgrading RAM.",
                "action": "Review memory-intensive processes"
            })
        
        if cpu > 80:
            suggestions.append({
                "category": "performance",
                "priority": "high",
                "title": "High CPU usage detected",
                "description": f"CPU usage at {cpu:.1f}%. May impact response times.",
                "action": "Review CPU-intensive tasks"
            })
            
    except ImportError:
        pass
    
    return suggestions

def analyze_memory_system():
    """Analyze episodic memory and suggest improvements."""
    suggestions = []
    
    memory_db = Path("/home/kloros/.kloros/memory.db")
    if not memory_db.exists():
        suggestions.append({
            "category": "memory",
            "priority": "high",
            "title": "Memory system not initialized",
            "description": "Episodic memory database not found. This impacts conversation continuity.",
            "action": "Initialize memory system with default schema"
        })
        return suggestions
    
    # Check memory database size and age
    stat = memory_db.stat()
    size_mb = stat.st_size / (1024 * 1024)
    age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400
    
    if size_mb > 500:
        suggestions.append({
            "category": "memory",
            "priority": "medium",
            "title": "Large memory database",
            "description": f"Memory DB is {size_mb:.1f}MB. Consider archiving old episodes.",
            "action": "Run memory cleanup/archival"
        })
    
    if age_days < 1:
        # Recent modification - check if properly indexed
        suggestions.append({
            "category": "memory",
            "priority": "low",
            "title": "Verify memory indexes",
            "description": "Recent memory activity detected. Ensure indexes are optimized.",
            "action": "Run ANALYZE on memory.db"
        })
    
    return suggestions

def analyze_rag_system():
    """Analyze RAG knowledge base and suggest improvements."""
    suggestions = []
    
    rag_index = Path("/home/kloros/.kloros/rag_index")
    if not rag_index.exists():
        suggestions.append({
            "category": "knowledge",
            "priority": "medium",
            "title": "RAG system not configured",
            "description": "Vector search index not found. This limits knowledge retrieval.",
            "action": "Initialize RAG system with document corpus"
        })
    
    return suggestions

def format_suggestions(suggestions):
    """Format suggestions for display."""
    if not suggestions:
        return "✓ No immediate suggestions. System is performing well!\n"
    
    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: priority_order.get(s["priority"], 99))
    
    lines = []
    lines.append("=== KLoROS Improvement Suggestions ===\n")
    
    for i, sug in enumerate(suggestions, 1):
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sug["priority"], "⚪")
        
        lines.append(f"{i}. {priority_icon} [{sug['category'].upper()}] {sug['title']}")
        lines.append(f"   {sug['description']}")
        lines.append(f"   → Action: {sug['action']}\n")
    
    return "\n".join(lines)

def main():
    all_suggestions = []
    
    # Gather suggestions from various analyzers
    all_suggestions.extend(analyze_test_coverage())
    all_suggestions.extend(analyze_tool_promotions())
    all_suggestions.extend(analyze_system_resources())
    all_suggestions.extend(analyze_memory_system())
    all_suggestions.extend(analyze_rag_system())
    
    output = format_suggestions(all_suggestions)
    print(output)
    
    # JSON output for programmatic use
    if "--json" in sys.argv:
        print(json.dumps(all_suggestions, indent=2))

if __name__ == "__main__":
    main()
