#!/usr/bin/env python3
"""Standalone tool ecosystem analyzer for KLoROS."""
import sys
sys.path.insert(0, '/home/kloros/src')

from tool_synthesis.ecosystem_manager import ToolEcosystemManager

def main():
    manager = ToolEcosystemManager()
    analysis = manager.analyze_ecosystem()
    
    print(f"\n🔧 Tool Ecosystem Analysis\n")
    print(f"Total Synthesized Tools: {analysis['total_tools']}")
    
    if analysis['status'] == 'insufficient_tools':
        print("Need at least 2 tools for analysis.")
        return
    
    recommendations = analysis.get('recommendations', [])
    if not recommendations:
        print("✅ Ecosystem is optimized!")
        return
    
    for rec in recommendations:
        if rec['type'] == 'combine':
            print(f"\n📦 Combine: {', '.join(rec['tools'])}")
            print(f"   → {rec['proposed_name']}")
            print(f"   {rec['rationale']}")
        else:
            print(f"\n✂️  Prune: {rec['remove']}")
            print(f"   Keep: {rec['keep']}")
            print(f"   {rec['rationale']}")
    
    # Submit to D-REAM
    if recommendations:
        manager.submit_recommendations_to_dream(recommendations)
        print(f"\n✅ Submitted {len(recommendations)} recommendations to D-REAM")

if __name__ == "__main__":
    main()
