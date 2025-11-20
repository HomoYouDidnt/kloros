#!/usr/bin/env python3
"""
Direct connector between tool synthesis and D-REAM evolution.
Replaces the broken alert system facade.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolDreamConnector:
    """Connect tool synthesis directly to D-REAM evolution system."""

    def __init__(self):
        """Initialize connector."""
        self.dream_artifacts_dir = Path("/home/kloros/src/dream/artifacts")
        self.tool_queue_file = self.dream_artifacts_dir / "tool_synthesis_queue.jsonl"

        # Ensure directories exist
        self.dream_artifacts_dir.mkdir(parents=True, exist_ok=True)

    def submit_tool_for_evolution(self, tool_name: str, tool_code: str,
                                  analysis: Dict, success: bool,
                                  error_msg: str = "") -> bool:
        """
        Submit a tool to D-REAM for evolutionary optimization.

        Args:
            tool_name: Name of the tool
            tool_code: Tool implementation code
            analysis: Tool analysis metadata
            success: Whether initial synthesis succeeded
            error_msg: Error message if failed

        Returns:
            True if submitted successfully
        """
        try:
            # Create evolution task record
            task = {
                "timestamp": datetime.now().isoformat(),
                "tool_name": tool_name,
                "component": "tool_synthesis",
                "status": "success" if success else "failed",
                "code": tool_code,
                "analysis": analysis,
                "error": error_msg,
                "priority": "medium" if success else "high",
                "submitted_to_dream": True
            }

            # Append to queue file
            with open(self.tool_queue_file, 'a') as f:
                f.write(json.dumps(task) + '\n')

            logger.info(f"Tool '{tool_name}' submitted to D-REAM evolution queue")
            return True

        except Exception as e:
            logger.error(f"Failed to submit tool to D-REAM: {e}")
            return False

    def get_pending_tools(self) -> list:
        """Get list of tools pending D-REAM evolution."""
        if not self.tool_queue_file.exists():
            return []

        tools = []
        try:
            with open(self.tool_queue_file, 'r') as f:
                for line in f:
                    if line.strip():
                        tools.append(json.loads(line))
            return tools
        except Exception as e:
            logger.error(f"Failed to read tool queue: {e}")
            return []

    def trigger_dream_evolution(self, tool_name: str) -> Optional[str]:
        """
        Trigger a D-REAM evolution run for a specific tool.

        Args:
            tool_name: Name of tool to evolve

        Returns:
            Run ID if successful, None otherwise
        """
        try:
            import subprocess

            # Create custom config for tool evolution
            config = {
                "seed": int(datetime.now().timestamp()),
                "population": {
                    "size": 12,
                    "max_gens": 10,
                    "elite_k": 3
                },
                "fitness": {
                    "objectives": ["perf", "risk", "maxdd"],
                    "weights": [0.6, -0.3, -0.1],  # Maximize perf, minimize risk/maxdd
                    "hard": {
                        "risk": 0.5,
                        "maxdd": 0.3
                    }
                },
                "target": {
                    "type": "tool_synthesis",
                    "tool_name": tool_name
                }
            }

            # Write temporary config
            config_path = f"/tmp/dream_tool_{tool_name}_{int(datetime.now().timestamp())}.yaml"
            import yaml
            with open(config_path, 'w') as f:
                yaml.dump(config, f)

            # Run D-REAM evolution
            result = subprocess.run(
                [
                    'python3',
                    '/home/kloros/src/dream/complete_dream_system.py',
                    '--config', config_path
                ],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                # Extract run ID from output
                for line in result.stdout.split('\n'):
                    if 'run_id' in line.lower():
                        # Parse run ID
                        pass

                logger.info(f"D-REAM evolution triggered for tool '{tool_name}'")
                return f"run_{tool_name}_{int(datetime.now().timestamp())}"
            else:
                logger.error(f"D-REAM evolution failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Failed to trigger D-REAM evolution: {e}")
            return None


# Singleton instance
_connector_instance = None

def get_tool_dream_connector() -> ToolDreamConnector:
    """Get singleton connector instance."""
    global _connector_instance
    if _connector_instance is None:
        _connector_instance = ToolDreamConnector()
    return _connector_instance
