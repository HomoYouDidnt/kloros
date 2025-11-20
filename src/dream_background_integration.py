#!/usr/bin/env python3
"""
D-REAM Background System Integration
Connects the background monitoring system to the production D-REAM evolution engine.
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add D-REAM source to path
sys.path.insert(0, '/home/kloros/src/dream')
sys.path.insert(0, '/home/kloros/src')

logger = logging.getLogger('dream_integration')

class DreamEvolutionTrigger:
    """Trigger production D-REAM evolution runs based on detected opportunities."""

    def __init__(self):
        self.last_evolution_run = None
        self.min_evolution_interval = timedelta(hours=1)  # Don't run more than once per hour
        self.evolution_results_path = Path('/home/kloros/src/dream/artifacts/manifests')
        self.evolution_log_path = Path('/home/kloros/.kloros/dream_evolution_trigger.log')

        # Configure evolution run parameters
        self.evolution_config = {
            'config_path': '/home/kloros/src/dream/configs/default.yaml',
            'max_generations': 10,  # Reduced for background runs
            'population_size': 12,  # Smaller population for faster runs
            'timeout': 300  # 5 minute timeout
        }

    def should_trigger_evolution(self, optimization: Dict) -> bool:
        """Determine if an optimization warrants triggering evolution."""
        # Check time constraint
        now = datetime.now()
        if self.last_evolution_run:
            if now - self.last_evolution_run < self.min_evolution_interval:
                logger.info(f"Skipping evolution: too soon since last run ({self.last_evolution_run})")
                return False

        # Check optimization criteria
        confidence = optimization.get('confidence', 0)
        risk_level = optimization.get('risk_level', 'high')
        opt_type = optimization.get('type', '')

        # Trigger criteria
        trigger = False
        reason = ""

        if confidence >= 0.8 and risk_level in ['low', 'medium']:
            trigger = True
            reason = f"High confidence ({confidence:.0%}) with acceptable risk ({risk_level})"
        elif opt_type == 'evolutionary_optimization' and confidence >= 0.7:
            trigger = True
            reason = f"Evolutionary optimization detected with confidence {confidence:.0%}"
        elif 'performance' in opt_type.lower() and confidence >= 0.75:
            trigger = True
            reason = f"Performance optimization needed: {opt_type}"
        elif 'accuracy' in opt_type.lower() and confidence >= 0.7:
            trigger = True
            reason = f"Accuracy improvement opportunity: {opt_type}"

        if trigger:
            logger.info(f"✅ Evolution trigger approved: {reason}")
        else:
            logger.info(f"⏸️ Evolution not triggered for {opt_type} (confidence: {confidence:.0%}, risk: {risk_level})")

        return trigger

    def create_evolution_config(self, optimization: Dict) -> Dict:
        """Create a custom configuration for this evolution run."""
        config = self.evolution_config.copy()

        # Customize based on optimization type
        opt_type = optimization.get('type', '')

        if 'memory' in opt_type.lower():
            # Focus on memory efficiency
            config['fitness_weights'] = {
                'perf': 0.5,
                'memory': 2.0,
                'stability': 1.0
            }
        elif 'response' in opt_type.lower() or 'latency' in opt_type.lower():
            # Focus on speed
            config['fitness_weights'] = {
                'perf': 2.0,
                'latency': 1.5,
                'stability': 0.5
            }
        elif 'accuracy' in opt_type.lower():
            # Focus on accuracy
            config['fitness_weights'] = {
                'accuracy': 2.0,
                'perf': 1.0,
                'stability': 1.0
            }
        else:
            # Balanced approach
            config['fitness_weights'] = {
                'perf': 1.0,
                'stability': 1.0,
                'risk': 0.5
            }

        # Add metadata about the trigger
        config['metadata'] = {
            'trigger_reason': optimization.get('description', 'Background optimization'),
            'expected_benefit': optimization.get('expected_benefit', 'Unknown'),
            'confidence': optimization.get('confidence', 0),
            'triggered_at': datetime.now().isoformat()
        }

        return config

    def trigger_evolution(self, optimization: Dict) -> Optional[Dict]:
        """Trigger a D-REAM evolution run."""
        try:
            if not self.should_trigger_evolution(optimization):
                return None

            logger.info("🚀 Triggering D-REAM evolution run...")

            # Create custom config
            config = self.create_evolution_config(optimization)

            # Save custom config
            custom_config_path = Path('/tmp/dream_auto_config.json')
            with open(custom_config_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Build command
            cmd = [
                sys.executable,
                '/home/kloros/src/dream/complete_dream_system.py',
                '--config', config['config_path']
            ]

            # Add custom parameters if needed
            if config.get('dry_run', False):
                cmd.append('--dry-run')

            # Run evolution in subprocess with timeout
            logger.info(f"Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd='/home/kloros/src/dream',
                capture_output=True,
                text=True,
                timeout=config.get('timeout', 300)
            )

            # Parse results
            if result.returncode == 0:
                logger.info("✅ Evolution run completed successfully")

                # Find the latest manifest
                manifests = sorted(self.evolution_results_path.glob('run_*.json'))
                if manifests:
                    latest_manifest = manifests[-1]
                    with open(latest_manifest) as f:
                        manifest_data = json.load(f)

                    # Extract key results
                    evolution_result = {
                        'success': True,
                        'run_id': manifest_data.get('run_id'),
                        'timestamp': manifest_data.get('timestamp'),
                        'trigger': optimization,
                        'best_fitness': None,  # Will be in event logs
                        'improvements': []
                    }

                    # Log the run
                    self._log_evolution_run(evolution_result)

                    # Update last run time
                    self.last_evolution_run = datetime.now()

                    return evolution_result

            else:
                logger.error(f"Evolution run failed with code {result.returncode}")
                logger.error(f"Error output: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"Evolution run timed out after {config.get('timeout')} seconds")
            return None
        except Exception as e:
            logger.error(f"Failed to trigger evolution: {e}")
            return None

    def _log_evolution_run(self, result: Dict):
        """Log the evolution run for auditing."""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'run_id': result.get('run_id'),
                'trigger': result.get('trigger', {}).get('type'),
                'success': result.get('success'),
                'description': result.get('trigger', {}).get('description')
            }

            # Append to log file
            with open(self.evolution_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')

        except Exception as e:
            logger.error(f"Failed to log evolution run: {e}")


def integrate_with_background_service():
    """Integrate D-REAM evolution triggering into the background service."""

    # This function would be called from the modified background service
    # to replace the old evolutionary_optimization.py integration

    trigger = DreamEvolutionTrigger()

    def enhanced_run_evolutionary_detection(issues: List[Dict], metrics: Dict) -> List[Dict[str, Any]]:
        """Enhanced version that triggers real D-REAM evolution."""
        optimizations = []

        # Analyze issues and metrics to create optimization opportunities
        for issue in issues:
            if issue.get('severity') in ['high', 'medium']:
                optimization = {
                    'type': f"evolutionary_{issue['type']}",
                    'component': 'system',
                    'description': issue['description'],
                    'expected_benefit': issue.get('suggested_improvement'),
                    'risk_level': 'medium' if issue['severity'] == 'high' else 'low',
                    'confidence': issue.get('confidence', 0.7),
                    'issue_data': issue
                }

                # Try to trigger evolution for this optimization
                result = trigger.trigger_evolution(optimization)

                if result and result.get('success'):
                    optimizations.append({
                        'type': 'evolutionary_optimization',
                        'component': 'dream_evolution',
                        'description': f"D-REAM evolution triggered for {issue['type']}",
                        'expected_benefit': issue.get('suggested_improvement'),
                        'risk_level': 'low',
                        'confidence': 0.9,
                        'evolution_run_id': result.get('run_id')
                    })

        return optimizations

    return enhanced_run_evolutionary_detection


if __name__ == "__main__":
    # Test the integration
    logging.basicConfig(level=logging.INFO)

    trigger = DreamEvolutionTrigger()

    # Test optimization
    test_optimization = {
        'type': 'slow_response_times',
        'severity': 'high',
        'description': 'Average pipeline response time 5.2s (target: <3s)',
        'suggested_improvement': 'Response time optimization',
        'confidence': 0.85,
        'risk_level': 'medium'
    }

    result = trigger.trigger_evolution(test_optimization)

    if result:
        print(f"Evolution triggered successfully: {result['run_id']}")
    else:
        print("Evolution not triggered or failed")