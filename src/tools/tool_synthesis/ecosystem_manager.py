"""
Tool Ecosystem Manager for KLoROS

Analyzes synthesized tools to identify opportunities for:
- Combining related tools into more powerful unified tools
- Pruning redundant tools by comparing performance
"""

import json
import sqlite3
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import requests


class ToolEcosystemManager:
    """Manages the ecosystem of synthesized tools."""

    def __init__(
        self,
        storage_dir: str = "/home/kloros/.kloros/synthesized_tools",
        ollama_url: Optional[str] = None
    ):
        self.storage_dir = Path(storage_dir)
        self.db_path = self.storage_dir / "tools.db"

        # Get default from SSOT config
        if ollama_url is None:
            from src.config.models_config import get_ollama_url
            ollama_url = get_ollama_url() + "/api/generate"
        self.ollama_url = ollama_url
        
    def analyze_ecosystem(self) -> Dict[str, any]:
        """
        Analyze the entire tool ecosystem for optimization opportunities.
        
        Returns:
            Dictionary with combination and pruning recommendations
        """
        tools = self._get_all_tools()
        
        if len(tools) < 2:
            return {
                "total_tools": len(tools),
                "recommendations": [],
                "status": "insufficient_tools"
            }
        
        recommendations = []
        
        # Find combinable tools
        combinable = self._find_combinable_tools(tools)
        for combo in combinable:
            recommendations.append({
                "type": "combine",
                "tools": combo["tools"],
                "rationale": combo["rationale"],
                "proposed_name": combo["proposed_name"],
                "priority": combo["priority"]
            })
        
        # Find redundant tools
        redundant = self._find_redundant_tools(tools)
        for redundancy in redundant:
            recommendations.append({
                "type": "prune",
                "tools": redundancy["tools"],
                "keep": redundancy["recommended_keeper"],
                "remove": redundancy["recommended_removal"],
                "rationale": redundancy["rationale"],
                "priority": redundancy["priority"]
            })
        
        return {
            "total_tools": len(tools),
            "recommendations": recommendations,
            "analysis_timestamp": self._get_timestamp(),
            "status": "complete"
        }
    
    def _get_all_tools(self) -> List[Dict]:
        """Get all active synthesized tools from database."""
        if not self.db_path.exists():
            return []
            
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT tool_name, analysis_data, use_count, 
                       performance_metrics, created_at, last_used
                FROM synthesized_tools
                WHERE status = 'active'
                ORDER BY use_count DESC
            ''')
            
            tools = []
            for row in cursor:
                analysis = json.loads(row['analysis_data']) if row['analysis_data'] else {}
                metrics = json.loads(row['performance_metrics']) if row['performance_metrics'] else {}
                
                tools.append({
                    "name": row['tool_name'],
                    "purpose": analysis.get('purpose', ''),
                    "category": analysis.get('category', 'utility'),
                    "data_sources": analysis.get('data_sources', []),
                    "use_count": row['use_count'],
                    "performance": metrics,
                    "created_at": row['created_at'],
                    "last_used": row['last_used']
                })
            
            return tools
    
    def _find_combinable_tools(self, tools: List[Dict]) -> List[Dict]:
        """Find tools that could be combined into more powerful unified tools."""
        combinable = []
        
        # Group tools by category
        by_category = {}
        for tool in tools:
            category = tool['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(tool)
        
        # Analyze each category for combination opportunities
        for category, category_tools in by_category.items():
            if len(category_tools) < 2:
                continue
            
            # Use LLM to analyze if tools should be combined
            analysis = self._llm_analyze_combination(category_tools, category)
            
            if analysis and analysis.get('should_combine', False):
                combinable.append({
                    "tools": [t['name'] for t in category_tools],
                    "rationale": analysis.get('rationale', 'Related functionality'),
                    "proposed_name": analysis.get('proposed_name', f"unified_{category}_control"),
                    "priority": analysis.get('priority', 5)
                })
        
        return combinable
    
    def _find_redundant_tools(self, tools: List[Dict]) -> List[Dict]:
        """Find redundant tools and recommend which to keep."""
        redundant = []
        checked_pairs = set()
        
        for i, tool1 in enumerate(tools):
            for tool2 in tools[i+1:]:
                pair_key = tuple(sorted([tool1['name'], tool2['name']]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # Use LLM to analyze if tools are redundant
                analysis = self._llm_analyze_redundancy(tool1, tool2)
                
                if analysis and analysis.get('are_redundant', False):
                    # Compare performance to decide which to keep
                    keeper, removal = self._compare_performance(tool1, tool2)
                    
                    redundant.append({
                        "tools": [tool1['name'], tool2['name']],
                        "recommended_keeper": keeper['name'],
                        "recommended_removal": removal['name'],
                        "rationale": analysis.get('rationale', 'Duplicate functionality'),
                        "priority": analysis.get('priority', 7)  # Higher priority for redundancy
                    })
        
        return redundant
    
    def _compare_performance(self, tool1: Dict, tool2: Dict) -> Tuple[Dict, Dict]:
        """Compare two tools and determine which performs better."""
        score1 = self._calculate_tool_score(tool1)
        score2 = self._calculate_tool_score(tool2)
        
        if score1 >= score2:
            return tool1, tool2
        else:
            return tool2, tool1
    
    def _calculate_tool_score(self, tool: Dict) -> float:
        """Calculate overall quality score for a tool."""
        score = 0.0
        
        # Usage frequency (40% weight)
        score += (tool['use_count'] / 100.0) * 0.4
        
        # Performance metrics (30% weight)
        perf = tool.get('performance', {})
        if perf.get('avg_execution_time_ms'):
            # Lower execution time is better
            time_score = max(0, 1.0 - (perf['avg_execution_time_ms'] / 1000.0))
            score += time_score * 0.3
        
        if perf.get('success_rate'):
            score += perf['success_rate'] * 0.3
        
        # Recency (30% weight)
        if tool['last_used']:
            # More recent usage is better
            from datetime import datetime
            try:
                last_used = datetime.fromisoformat(tool['last_used'])
                now = datetime.now()
                days_ago = (now - last_used).days
                recency_score = max(0, 1.0 - (days_ago / 30.0))
                score += recency_score * 0.3
            except:
                pass
        
        return min(1.0, score)
    
    def _llm_analyze_combination(self, tools: List[Dict], category: str) -> Optional[Dict]:
        """Use LLM to analyze if tools should be combined."""
        tool_descriptions = "\n".join([
            f"- {t['name']}: {t['purpose']}" for t in tools
        ])
        
        prompt = f"""Analyze these {category} tools and determine if they should be combined:

{tool_descriptions}

Should these tools be combined into a single unified tool? Consider:
1. Do they operate on related functionality?
2. Would combining them provide better user experience?
3. Is there significant overlap in their data sources?

Respond with ONLY a JSON object:
{{
    "should_combine": true/false,
    "rationale": "brief explanation",
    "proposed_name": "suggested_name_if_combining",
    "priority": 1-10
}}"""
        
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": "qwen2.5:14b-instruct-q4_0",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=20
            )
            
            if response.status_code == 200:
                llm_response = response.json().get("response", "").strip()
                # Extract JSON
                import re
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
        except:
            pass
        
        return None
    
    def _llm_analyze_redundancy(self, tool1: Dict, tool2: Dict) -> Optional[Dict]:
        """Use LLM to analyze if two tools are redundant."""
        prompt = f"""Analyze if these two tools are redundant:

Tool 1: {tool1['name']}
Purpose: {tool1['purpose']}
Category: {tool1['category']}

Tool 2: {tool2['name']}
Purpose: {tool2['purpose']}
Category: {tool2['category']}

Are these tools redundant (doing essentially the same thing)? Consider:
1. Do they have the same core purpose?
2. Do they access the same data sources?
3. Would users ever need both?

Respond with ONLY a JSON object:
{{
    "are_redundant": true/false,
    "rationale": "brief explanation",
    "priority": 1-10
}}"""
        
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": "qwen2.5:14b-instruct-q4_0",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=20
            )
            
            if response.status_code == 200:
                llm_response = response.json().get("response", "").strip()
                import re
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
        except:
            pass
        
        return None
    
    def _get_timestamp(self) -> str:
        """Get current ISO timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def submit_recommendations_to_dream(self, recommendations: List[Dict]) -> bool:
        """Submit ecosystem optimization recommendations to D-REAM."""
        try:
            from shared_dream_instance import SharedDreamManager
            from datetime import datetime
            
            shared = SharedDreamManager()
            submitted_count = 0
            
            for rec in recommendations:
                improvement = {
                    "task_id": f"tool_ecosystem_{rec['type']}_{int(datetime.now().timestamp())}",
                    "component": "tool_ecosystem",
                    "description": f"{rec['type'].title()} tools: {', '.join(rec['tools'])}",
                    "details": rec,
                    "expected_benefit": "Streamlined tool ecosystem with better performance and less redundancy",
                    "risk_level": "low",
                    "confidence": 0.70,
                    "urgency": "low",
                    "detected_at": datetime.now().isoformat(),
                    "evidence": "tool_synthesis_analysis"
                }
                
                if shared.inject_improvement(improvement):
                    submitted_count += 1
            
            return submitted_count > 0
            
        except Exception as e:
            print(f"[ecosystem] Failed to submit to D-REAM: {e}")
            return False
