"""
Comprehensive Reporting System for KLoROS

Generates natural language reports on-demand for various system aspects.
All reports are in regular, conversational language - no JSON dumps or technical jargon.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any


class ReportGenerator:
    """Generate human-readable reports for KLoROS system status."""

    def __init__(self, kloros_instance=None):
        """Initialize report generator."""
        self.kloros = kloros_instance
        self.kloros_dir = Path("/home/kloros/.kloros")

    def generate_tool_curation_report(self) -> str:
        """Generate summary of recent tool curation activities."""
        deployments_file = self.kloros_dir / "tool_deployments.jsonl"

        if not deployments_file.exists():
            return "No tool curation activities recorded yet. Tool curation runs weekly during reflection cycles."

        # Read recent deployments (last 30 days)
        deployments = []
        cutoff = datetime.now() - timedelta(days=30)

        try:
            with open(deployments_file) as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        timestamp = datetime.fromisoformat(record['timestamp'])
                        if timestamp > cutoff:
                            deployments.append(record)
        except Exception as e:
            return f"Error reading tool deployment log: {e}"

        if not deployments:
            return "No tool curation activities in the past 30 days."

        # Generate report
        report = "## Tool Curation Activity (Past 30 Days)\n\n"

        total_deployed = sum(d['deployed'] for d in deployments)
        total_failed = sum(d['failed'] for d in deployments)

        report += f"I've performed {len(deployments)} tool curation cycles.\n\n"
        report += f"**Summary:**\n"
        report += f"- Improvements deployed: {total_deployed}\n"
        report += f"- Failed deployments: {total_failed}\n\n"

        if deployments:
            report += "**Recent Actions:**\n\n"
            for deployment in deployments[-5:]:  # Last 5
                timestamp = datetime.fromisoformat(deployment['timestamp'])
                report += f"• {timestamp.strftime('%Y-%m-%d %H:%M')}: "
                report += f"{deployment['deployed']} changes deployed\n"
                if deployment['actions']:
                    for action in deployment['actions'][:3]:  # Top 3 actions
                        report += f"  - {action}\n"
                report += "\n"

        return report

    def generate_reflection_summary(self) -> str:
        """Generate summary of recent reflection activities."""
        reflection_log = self.kloros_dir / "reflection.log"

        if not reflection_log.exists():
            return "No reflection data available."

        # Read last 100 lines
        try:
            with open(reflection_log) as f:
                lines = f.readlines()[-100:]
        except Exception as e:
            return f"Error reading reflection log: {e}"

        # Parse for insights
        report = "## Recent Reflection Activity\n\n"

        phases_found = set()
        for line in lines:
            if "[reflection] Phase" in line:
                # Extract phase name
                try:
                    phase_part = line.split("Phase")[1].split(":")[0].strip()
                    phases_found.add(phase_part)
                except:
                    pass

        if phases_found:
            report += f"I've been running {len(phases_found)} reflection phases during idle periods:\n\n"
            for phase in sorted(phases_found):
                report += f"- Phase {phase}\n"
            report += "\n"

        # Look for specific insights
        insights_count = sum(1 for line in lines if "insight" in line.lower())
        if insights_count > 0:
            report += f"Generated {insights_count} insights in recent reflection cycles.\n\n"

        return report

    def generate_memory_summary(self) -> str:
        """Generate summary of memory system status."""
        if not self.kloros or not hasattr(self.kloros, 'memory_enhanced'):
            return "Memory system not available."

        try:
            memory = self.kloros.memory_enhanced
            store = memory.memory_store

            # Get statistics
            total_events = store.count_events()
            episodes = store.get_recent_episodes(limit=10)

            report = "## Memory System Summary\n\n"
            report += f"**Total Events:** {total_events}\n"
            report += f"**Recent Episodes:** {len(episodes)}\n\n"

            if episodes:
                report += "**Latest Episodes:**\n\n"
                for ep in episodes[:5]:
                    timestamp = datetime.fromisoformat(ep.timestamp)
                    report += f"• {timestamp.strftime('%Y-%m-%d %H:%M')}: {ep.summary[:80]}...\n"

            return report

        except Exception as e:
            return f"Error accessing memory system: {e}"

    def generate_consciousness_report(self) -> str:
        """Generate summary of current consciousness state."""
        if not self.kloros or not hasattr(self.kloros, 'consciousness'):
            return "Consciousness system not available."

        try:
            consciousness = self.kloros.consciousness
            affect = consciousness.current_affect

            report = "## Current Consciousness State\n\n"
            report += f"**Affective State:**\n"
            report += f"- Valence: {affect.valence:.2f} (emotional positivity)\n"
            report += f"- Arousal: {affect.arousal:.2f} (activation level)\n"
            report += f"- Uncertainty: {affect.uncertainty:.2f}\n"
            report += f"- Curiosity: {affect.curiosity:.2f}\n"
            report += f"- Fatigue: {affect.fatigue:.2f}\n\n"

            # Interpret
            if affect.valence > 0.5:
                mood = "positive and engaged"
            elif affect.valence < -0.5:
                mood = "concerned or troubled"
            else:
                mood = "neutral"

            report += f"Overall mood: {mood}.\n"

            return report

        except Exception as e:
            return f"Error accessing consciousness: {e}"

    def generate_system_health_report(self) -> str:
        """Generate overall system health summary."""
        report = "## System Health Report\n\n"

        # Check service status
        try:
            import subprocess
            result = subprocess.run(
                ['systemctl', 'is-active', 'kloros.service'],
                capture_output=True,
                text=True
            )
            service_status = result.stdout.strip()

            if service_status == "active":
                report += "✅ KLoROS service is running normally\n\n"
            else:
                report += f"⚠️ KLoROS service status: {service_status}\n\n"
        except:
            report += "Unable to check service status\n\n"

        # Check recent errors
        error_log = self.kloros_dir / "errors.log"
        if error_log.exists():
            try:
                with open(error_log) as f:
                    recent_errors = f.readlines()[-10:]

                if recent_errors:
                    report += f"⚠️ Found {len(recent_errors)} recent errors\n"
                else:
                    report += "✅ No recent errors\n"
            except:
                pass

        return report

    def generate_comprehensive_report(self) -> str:
        """Generate a comprehensive report covering all major systems."""
        report = "# KLoROS Comprehensive System Report\n\n"
        report += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report += "---\n\n"

        # System health
        report += self.generate_system_health_report()
        report += "\n---\n\n"

        # Consciousness
        report += self.generate_consciousness_report()
        report += "\n---\n\n"

        # Memory
        report += self.generate_memory_summary()
        report += "\n---\n\n"

        # Reflection
        report += self.generate_reflection_summary()
        report += "\n---\n\n"

        # Tool curation
        report += self.generate_tool_curation_report()

        return report


def get_report_generator(kloros_instance=None) -> ReportGenerator:
    """Get report generator instance."""
    return ReportGenerator(kloros_instance)
