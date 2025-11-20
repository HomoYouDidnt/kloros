"""
Reflective Tool Curator - Meta-cognitive tool management for KLoROS

This module provides deliberate, self-aware tool management capabilities:
- Examines existing tools for quality, redundancy, naming
- Proposes improvements, removals, and reorganizations
- Takes action to deploy changes back to the system
- Maintains tool catalog health

Unlike automatic evolution, this is reflective and deliberate.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ToolAnalysis:
    """Analysis result for a single tool."""
    tool_name: str
    description: str
    parameters: List[str]
    usage_count: int = 0
    last_used: Optional[str] = None

    # Quality assessment
    has_clear_purpose: bool = True
    naming_quality: str = "good"  # good, unclear, redundant
    suggested_name: Optional[str] = None

    # Redundancy detection
    similar_tools: List[str] = None
    is_redundant: bool = False

    # Recommendations
    action: str = "keep"  # keep, improve, rename, merge, remove
    rationale: str = ""

    def __post_init__(self):
        if self.similar_tools is None:
            self.similar_tools = []


@dataclass
class CurationReport:
    """Report from tool curation analysis."""
    timestamp: str
    total_tools: int
    tools_analyzed: List[ToolAnalysis]

    # Summary statistics
    tools_to_keep: int = 0
    tools_to_improve: int = 0
    tools_to_rename: int = 0
    tools_to_merge: int = 0
    tools_to_remove: int = 0

    # Proposed actions
    actions: List[Dict] = None

    def __post_init__(self):
        if self.actions is None:
            self.actions = []


class ReflectiveToolCurator:
    """
    Reflective tool management system for KLoROS.

    Provides meta-cognitive awareness of tool catalog health
    and enables deliberate self-improvement.
    """

    def __init__(self, tool_registry=None):
        """
        Initialize reflective curator.

        Args:
            tool_registry: IntrospectionToolRegistry instance
        """
        self.registry = tool_registry
        self.tools_dir = Path("/home/kloros/src/synthesized_tools")
        self.usage_log = Path("/home/kloros/.kloros/tool_usage.jsonl")
        self.curation_history = Path("/home/kloros/.kloros/tool_curation_history.jsonl")

        # Ensure directories exist
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)

    def analyze_tools(self) -> CurationReport:
        """
        Perform reflective analysis of all tools in registry.

        Returns:
            CurationReport with analysis and proposed actions
        """
        if not self.registry:
            raise RuntimeError("No tool registry available for analysis")

        print("[curator] 🔍 Beginning reflective tool analysis...")

        # Get all tools
        tools = self.registry.tools
        analyses = []

        # Load usage statistics
        usage_stats = self._load_usage_stats()

        # Analyze each tool
        for tool_name, tool in tools.items():
            analysis = self._analyze_tool(tool, usage_stats)
            analyses.append(analysis)

        # Detect redundancies across tools
        self._detect_redundancies(analyses)

        # Generate report
        report = self._generate_report(analyses)

        # Save report
        self._save_report(report)

        print(f"[curator] ✓ Analysis complete: {len(analyses)} tools examined")
        print(f"[curator]   Keep: {report.tools_to_keep}, Improve: {report.tools_to_improve}, "
              f"Rename: {report.tools_to_rename}, Merge: {report.tools_to_merge}, Remove: {report.tools_to_remove}")

        return report

    def _analyze_tool(self, tool, usage_stats: Dict) -> ToolAnalysis:
        """Analyze a single tool for quality and utility."""
        tool_name = tool.name
        description = tool.description
        parameters = tool.parameters or []

        # Get usage data
        usage = usage_stats.get(tool_name, {})
        usage_count = usage.get('count', 0)
        last_used = usage.get('last_used')

        # Assess naming quality
        naming_quality, suggested_name = self._assess_naming(tool_name, description)

        # Assess purpose clarity
        has_clear_purpose = self._assess_purpose_clarity(description)

        # Initialize analysis
        analysis = ToolAnalysis(
            tool_name=tool_name,
            description=description,
            parameters=parameters,
            usage_count=usage_count,
            last_used=last_used,
            has_clear_purpose=has_clear_purpose,
            naming_quality=naming_quality,
            suggested_name=suggested_name
        )

        # Determine action
        self._determine_action(analysis)

        return analysis

    def _assess_naming(self, name: str, description: str) -> Tuple[str, Optional[str]]:
        """
        Assess tool naming quality.

        Returns:
            (quality_rating, suggested_name)
        """
        # Good naming patterns
        if re.match(r'^[a-z_]+$', name) and len(name.split('_')) >= 2:
            # Check if name matches description intent
            name_words = set(name.split('_'))
            desc_words = set(re.findall(r'\b\w+\b', description.lower()))

            overlap = name_words & desc_words
            if len(overlap) >= 1:
                return ("good", None)

        # Suggest improvement
        # Extract key words from description
        key_words = self._extract_key_words(description)
        if key_words:
            suggested = '_'.join(key_words[:3])
            return ("unclear", suggested)

        return ("unclear", None)

    def _assess_purpose_clarity(self, description: str) -> bool:
        """Check if tool purpose is clearly described."""
        # Heuristics for clear purpose
        if len(description) < 20:
            return False

        # Should have action verbs
        action_verbs = ['get', 'analyze', 'check', 'monitor', 'update', 'create', 'delete', 'modify']
        has_action = any(verb in description.lower() for verb in action_verbs)

        return has_action

    def _extract_key_words(self, text: str) -> List[str]:
        """Extract key words from description for naming."""
        # Remove common stopwords
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with'}
        words = re.findall(r'\b[a-z]+\b', text.lower())
        return [w for w in words if w not in stopwords and len(w) > 3][:3]

    def _detect_redundancies(self, analyses: List[ToolAnalysis]) -> None:
        """Detect redundant tools across the catalog."""
        # Simple semantic similarity based on description overlap
        for i, analysis_a in enumerate(analyses):
            words_a = set(self._extract_key_words(analysis_a.description))

            for j, analysis_b in enumerate(analyses[i+1:], start=i+1):
                words_b = set(self._extract_key_words(analysis_b.description))

                # Jaccard similarity
                if words_a and words_b:
                    overlap = len(words_a & words_b)
                    union = len(words_a | words_b)
                    similarity = overlap / union if union > 0 else 0

                    if similarity > 0.5:  # High similarity threshold
                        analysis_a.similar_tools.append(analysis_b.tool_name)
                        analysis_b.similar_tools.append(analysis_a.tool_name)
                        analysis_a.is_redundant = True
                        analysis_b.is_redundant = True

    def _determine_action(self, analysis: ToolAnalysis) -> None:
        """Determine recommended action for a tool."""
        # Priority 1: Remove if unused and redundant
        if analysis.usage_count == 0 and analysis.is_redundant:
            analysis.action = "remove"
            analysis.rationale = f"Unused and redundant with: {', '.join(analysis.similar_tools)}"
            return

        # Priority 2: Merge if redundant but used
        if analysis.is_redundant and analysis.usage_count > 0:
            analysis.action = "merge"
            analysis.rationale = f"Redundant with: {', '.join(analysis.similar_tools)}"
            return

        # Priority 3: Rename if naming is poor
        if analysis.naming_quality != "good" and analysis.suggested_name:
            analysis.action = "rename"
            analysis.rationale = f"Unclear naming - suggest: {analysis.suggested_name}"
            return

        # Priority 4: Improve if purpose unclear
        if not analysis.has_clear_purpose:
            analysis.action = "improve"
            analysis.rationale = "Description lacks clarity about tool purpose"
            return

        # Default: Keep
        analysis.action = "keep"
        analysis.rationale = "Tool is well-designed and useful"

    def _generate_report(self, analyses: List[ToolAnalysis]) -> CurationReport:
        """Generate curation report with statistics and actions."""
        report = CurationReport(
            timestamp=datetime.now().isoformat(),
            total_tools=len(analyses),
            tools_analyzed=analyses
        )

        # Count actions
        for analysis in analyses:
            if analysis.action == "keep":
                report.tools_to_keep += 1
            elif analysis.action == "improve":
                report.tools_to_improve += 1
            elif analysis.action == "rename":
                report.tools_to_rename += 1
            elif analysis.action == "merge":
                report.tools_to_merge += 1
            elif analysis.action == "remove":
                report.tools_to_remove += 1

            # Add to actions list if not keep
            if analysis.action != "keep":
                report.actions.append({
                    "tool": analysis.tool_name,
                    "action": analysis.action,
                    "rationale": analysis.rationale,
                    "details": {
                        "usage_count": analysis.usage_count,
                        "similar_tools": analysis.similar_tools,
                        "suggested_name": analysis.suggested_name
                    }
                })

        return report

    def _load_usage_stats(self) -> Dict:
        """Load tool usage statistics."""
        if not self.usage_log.exists():
            return {}

        stats = {}
        try:
            with open(self.usage_log) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        tool_name = entry.get('tool_name')
                        if tool_name:
                            if tool_name not in stats:
                                stats[tool_name] = {'count': 0}
                            stats[tool_name]['count'] += 1
                            stats[tool_name]['last_used'] = entry.get('timestamp')
        except Exception as e:
            print(f"[curator] Warning: Failed to load usage stats: {e}")

        return stats

    def _save_report(self, report: CurationReport) -> None:
        """Save curation report to history."""
        try:
            with open(self.curation_history, 'a') as f:
                # Save summary only (not full analyses)
                summary = {
                    "timestamp": report.timestamp,
                    "total_tools": report.total_tools,
                    "tools_to_keep": report.tools_to_keep,
                    "tools_to_improve": report.tools_to_improve,
                    "tools_to_rename": report.tools_to_rename,
                    "tools_to_merge": report.tools_to_merge,
                    "tools_to_remove": report.tools_to_remove,
                    "actions_count": len(report.actions)
                }
                f.write(json.dumps(summary) + '\n')
        except Exception as e:
            print(f"[curator] Warning: Failed to save report: {e}")

    def log_tool_usage(self, tool_name: str) -> None:
        """Log tool usage for future analysis."""
        try:
            with open(self.usage_log, 'a') as f:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "tool_name": tool_name
                }
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"[curator] Warning: Failed to log usage: {e}")

    def deploy_improvements(self, report: CurationReport) -> Dict[str, int]:
        """
        Deploy tool improvements autonomously.

        Args:
            report: CurationReport with proposed actions

        Returns:
            Dictionary with deployment statistics
        """
        result = {
            "deployed": 0,
            "failed": 0,
            "actions": []
        }

        print("[curator] 🚀 Beginning autonomous tool deployment...")

        for action_item in report.actions:
            tool_name = action_item['tool']
            action = action_item['action']

            try:
                if action == "rename":
                    self._deploy_rename(tool_name, action_item)
                    result["deployed"] += 1
                    result["actions"].append(f"Renamed {tool_name}")

                elif action == "improve":
                    self._deploy_improve(tool_name, action_item)
                    result["deployed"] += 1
                    result["actions"].append(f"Improved {tool_name}")

                elif action == "remove":
                    self._deploy_remove(tool_name, action_item)
                    result["deployed"] += 1
                    result["actions"].append(f"Removed {tool_name}")

                elif action == "merge":
                    # Merge is complex - just log for now, needs user guidance
                    print(f"[curator] ⚠️ Merge action for {tool_name} requires manual intervention")
                    result["actions"].append(f"Merge {tool_name} (manual)")

            except Exception as e:
                print(f"[curator] ❌ Failed to deploy {action} for {tool_name}: {e}")
                result["failed"] += 1

        # Save deployment record
        self._save_deployment_record(result)

        return result

    def _deploy_rename(self, tool_name: str, action_item: Dict) -> None:
        """Rename a tool in the registry."""
        new_name = action_item['details'].get('suggested_name')
        if not new_name:
            raise ValueError("No suggested name provided")

        tool = self.registry.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        # Create new tool with new name
        from introspection_tools import IntrospectionTool
        new_tool = IntrospectionTool(
            name=new_name,
            description=tool.description,
            func=tool.func,
            parameters=tool.parameters
        )

        # Register new tool and remove old
        self.registry.register(new_tool)
        del self.registry.tools[tool_name]

        print(f"[curator] ✓ Renamed '{tool_name}' → '{new_name}'")

    def _deploy_improve(self, tool_name: str, action_item: Dict) -> None:
        """Improve tool description for clarity."""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        # Generate improved description
        old_desc = tool.description

        # Simple improvement: Add action verb if missing
        if not any(verb in old_desc.lower() for verb in ['get', 'analyze', 'check', 'monitor', 'update']):
            improved_desc = f"Get {old_desc.lower()}"
        else:
            improved_desc = old_desc

        # Make first letter uppercase
        improved_desc = improved_desc[0].upper() + improved_desc[1:]

        tool.description = improved_desc
        print(f"[curator] ✓ Improved description for '{tool_name}'")
        print(f"[curator]   Old: {old_desc}")
        print(f"[curator]   New: {improved_desc}")

    def _deploy_remove(self, tool_name: str, action_item: Dict) -> None:
        """Remove unused/redundant tool from registry."""
        if tool_name not in self.registry.tools:
            raise ValueError(f"Tool {tool_name} not found")

        del self.registry.tools[tool_name]
        print(f"[curator] ✓ Removed unused tool '{tool_name}'")

    def _save_deployment_record(self, result: Dict) -> None:
        """Save deployment record for tracking."""
        try:
            deployment_log = Path("/home/kloros/.kloros/tool_deployments.jsonl")
            with open(deployment_log, 'a') as f:
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "deployed": result["deployed"],
                    "failed": result["failed"],
                    "actions": result["actions"]
                }
                f.write(json.dumps(record) + '\n')
        except Exception as e:
            print(f"[curator] Warning: Failed to save deployment record: {e}")

    def generate_curation_prompt(self, report: CurationReport, deployed: bool = False) -> str:
        """
        Generate natural language prompt for KLoROS to review curation report.

        Args:
            report: CurationReport with analysis
            deployed: Whether changes were already deployed

        Returns:
            Formatted prompt describing findings and actions
        """
        if deployed:
            prompt = f"""## 🔧 Tool Catalog Curation - Actions Taken

I've examined my tool catalog and deployed improvements autonomously.

**Summary:**
- Total tools: {report.total_tools}
- Well-designed tools: {report.tools_to_keep}
- Improvements deployed: {len(report.actions)}

"""
            if report.actions:
                prompt += "**Actions Taken:**\n\n"
                for action in report.actions:
                    prompt += f"• **{action['tool']}** - {action['action'].upper()}\n"
                    prompt += f"  Reason: {action['rationale']}\n"
                    if action['details'].get('suggested_name'):
                        prompt += f"  New name: `{action['details']['suggested_name']}`\n"
                    prompt += "\n"
            else:
                prompt += "All tools were well-organized. No changes needed.\n"

            prompt += "\nThese changes are now active in my tool catalog."
        else:
            prompt = f"""## 🔧 Tool Catalog Curation Report

I've examined my tool catalog and found opportunities for improvement.

**Summary:**
- Total tools: {report.total_tools}
- Well-designed tools: {report.tools_to_keep}
- Tools needing attention: {len(report.actions)}

"""
            if report.actions:
                prompt += "**Proposed Actions:**\n\n"
                for action in report.actions:
                    prompt += f"• **{action['tool']}** - {action['action'].upper()}\n"
                    prompt += f"  Reason: {action['rationale']}\n"
                    if action['details'].get('suggested_name'):
                        prompt += f"  Suggested name: `{action['details']['suggested_name']}`\n"
                    prompt += "\n"
            else:
                prompt += "All tools are well-organized and useful. No changes recommended.\n"

            prompt += "\nWould you like me to proceed with these improvements?"

        return prompt


def get_tool_curator(tool_registry=None) -> ReflectiveToolCurator:
    """Get tool curator instance."""
    return ReflectiveToolCurator(tool_registry)
