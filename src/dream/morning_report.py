#!/usr/bin/env python3
"""
D-REAM Evolution Morning Report
Analyzes overnight evolutionary optimization results.
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import numpy as np

# ANSI color codes for terminal output
RESET = '\033[0m'
BOLD = '\033[1m'
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'

def load_evolution_data(domain_path: Path):
    """Load all evolution data for a domain."""
    generations = []
    if domain_path.exists():
        with open(domain_path, 'r') as f:
            for line in f:
                try:
                    generations.append(json.loads(line))
                except:
                    pass
    return generations

def calculate_improvement(generations):
    """Calculate fitness improvement over generations."""
    if len(generations) < 2:
        return 0.0

    first_best = generations[0].get('best_fitness', -float('inf'))
    last_best = generations[-1].get('best_fitness', -float('inf'))

    if first_best == -float('inf') or last_best == -float('inf'):
        return 0.0

    if first_best != 0:
        return ((last_best - first_best) / abs(first_best)) * 100
    return 0.0

def get_convergence_rate(generations):
    """Calculate how quickly the population is converging."""
    if len(generations) < 2:
        return "N/A"

    # Look at variance in fitness over last 5 generations
    recent = generations[-5:] if len(generations) >= 5 else generations

    variances = []
    for gen in recent:
        avg_fitness = gen.get('avg_fitness', 0)
        best_fitness = gen.get('best_fitness', 0)
        if avg_fitness and best_fitness and avg_fitness != -float('inf'):
            variance = abs(best_fitness - avg_fitness)
            variances.append(variance)

    if variances:
        avg_variance = np.mean(variances)
        if avg_variance < 0.01:
            return "Converged"
        elif avg_variance < 0.05:
            return "Converging"
        else:
            return "Exploring"
    return "Unknown"

def format_time_ago(timestamp_str):
    """Format timestamp as time ago."""
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        delta = now - timestamp

        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())}s ago"
        elif delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m ago"
        else:
            return f"{int(delta.total_seconds() / 3600)}h ago"
    except:
        return "Unknown"

def print_domain_report(domain, generations):
    """Print detailed report for a domain."""
    if not generations:
        print(f"  {YELLOW}No data available{RESET}")
        return

    latest = generations[-1]
    improvement = calculate_improvement(generations)
    convergence = get_convergence_rate(generations)

    # Determine status color
    if improvement > 10:
        status_color = GREEN
        status = "✓ Improving"
    elif improvement < -10:
        status_color = RED
        status = "✗ Degrading"
    else:
        status_color = YELLOW
        status = "→ Stable"

    print(f"  {status_color}{status}{RESET}")
    print(f"  Generations Run: {BOLD}{len(generations)}{RESET}")
    print(f"  Latest Generation: {latest.get('generation', 0)} ({format_time_ago(latest.get('timestamp', ''))})")

    # Fitness metrics
    best = latest.get('best_fitness', 'N/A')
    avg = latest.get('avg_fitness', 'N/A')
    if isinstance(best, (int, float)) and best != -float('inf'):
        print(f"  Best Fitness: {GREEN}{best:.4f}{RESET}")
    else:
        print(f"  Best Fitness: {RED}Invalid/Unsafe{RESET}")

    if isinstance(avg, (int, float)) and avg != -float('inf'):
        print(f"  Avg Fitness: {avg:.4f}")

    print(f"  Valid Solutions: {latest.get('valid_individuals', 0)}/{latest.get('population_size', 20)}")

    # Improvement and convergence
    if improvement != 0:
        imp_color = GREEN if improvement > 0 else RED
        print(f"  Improvement: {imp_color}{improvement:+.1f}%{RESET}")
    else:
        print(f"  Improvement: {YELLOW}0.0%{RESET}")

    print(f"  Convergence: {CYAN}{convergence}{RESET}")

    # Find best configuration across all generations
    all_time_best = -float('inf')
    best_gen = 0
    for i, gen in enumerate(generations):
        if gen.get('best_fitness', -float('inf')) > all_time_best:
            all_time_best = gen['best_fitness']
            best_gen = gen.get('generation', i)

    if all_time_best != -float('inf') and all_time_best != best:
        print(f"  All-Time Best: {MAGENTA}{all_time_best:.4f}{RESET} (gen {best_gen})")

    print()

def print_summary_statistics(all_data):
    """Print overall summary statistics."""
    total_generations = sum(len(gens) for gens in all_data.values())
    total_evaluations = total_generations * 20  # Population size

    print(f"\n{BOLD}=== OVERNIGHT SUMMARY ==={RESET}")
    print(f"Total Generations: {BOLD}{total_generations}{RESET}")
    print(f"Total Evaluations: {BOLD}{total_evaluations:,}{RESET}")

    # Find best performing domain
    best_domain = None
    best_improvement = -float('inf')
    worst_domain = None
    worst_improvement = float('inf')

    for domain, gens in all_data.items():
        if gens:
            imp = calculate_improvement(gens)
            if imp > best_improvement:
                best_improvement = imp
                best_domain = domain
            if imp < worst_improvement:
                worst_improvement = imp
                worst_domain = domain

    if best_domain and best_improvement > 0:
        print(f"Best Improving Domain: {GREEN}{best_domain} (+{best_improvement:.1f}%){RESET}")

    if worst_domain and worst_improvement < 0:
        print(f"Worst Performing Domain: {RED}{worst_domain} ({worst_improvement:.1f}%){RESET}")

    # Count converged domains
    converged = 0
    converging = 0
    for domain, gens in all_data.items():
        status = get_convergence_rate(gens)
        if status == "Converged":
            converged += 1
        elif status == "Converging":
            converging += 1

    print(f"Convergence Status: {converged} converged, {converging} converging")

    # Estimate time to full convergence
    if converging > 0:
        print(f"Estimated Time to Full Convergence: {YELLOW}2-4 hours{RESET}")
    elif converged == len(all_data):
        print(f"Status: {GREEN}All domains converged!{RESET}")

def print_recommendations(all_data):
    """Print recommendations based on overnight results."""
    print(f"\n{BOLD}=== RECOMMENDATIONS ==={RESET}")

    recommendations = []

    # Check for domains with high fitness
    for domain, gens in all_data.items():
        if gens:
            latest = gens[-1]
            best = latest.get('best_fitness', -float('inf'))

            if isinstance(best, (int, float)) and best > 0.5:
                recommendations.append(f"• {GREEN}{domain}{RESET}: Consider applying best configuration (fitness > 0.5)")
            elif isinstance(best, (int, float)) and best < -0.5:
                recommendations.append(f"• {RED}{domain}{RESET}: Needs parameter range adjustment (fitness < -0.5)")

    # Check for stuck domains
    for domain, gens in all_data.items():
        if len(gens) > 10:
            # Check if fitness hasn't improved in last 5 generations
            if len(gens) >= 5:
                recent_bests = [g.get('best_fitness', -float('inf')) for g in gens[-5:]]
                if all(b == recent_bests[0] for b in recent_bests):
                    recommendations.append(f"• {YELLOW}{domain}{RESET}: Stuck - consider increasing mutation rate")

    # Safety constraints recommendation
    high_performing_domains = []
    for domain, gens in all_data.items():
        if gens:
            latest = gens[-1]
            best = latest.get('best_fitness', -float('inf'))
            valid = latest.get('valid_individuals', 0)

            if isinstance(best, (int, float)) and best > 0.3 and valid == 20:
                high_performing_domains.append(domain)

    if len(high_performing_domains) >= 3:
        recommendations.append(f"• {CYAN}Safety constraints{RESET}: Consider relaxing for: {', '.join(high_performing_domains)}")

    if recommendations:
        for rec in recommendations:
            print(rec)
    else:
        print(f"  {GREEN}✓ All domains operating normally{RESET}")

def load_best_configurations():
    """Load the best configurations found."""
    config_file = Path('/home/kloros/.kloros/dream_best_configs.json')
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def print_best_configurations(all_data):
    """Print the best configurations found for each domain."""
    print(f"\n{BOLD}=== BEST CONFIGURATIONS ==={RESET}")

    configs = load_best_configurations()

    for domain in sorted(all_data.keys()):
        if domain in configs:
            config = configs[domain]
            fitness = config.get('fitness', 'N/A')

            if isinstance(fitness, (int, float)) and fitness > 0:
                print(f"\n{GREEN}{domain}{RESET} (fitness: {fitness:.4f}):")
            else:
                print(f"\n{YELLOW}{domain}{RESET} (fitness: {fitness}):")

            # Show key configuration parameters
            if 'configuration' in config:
                params = config['configuration']
                # Show first 3 most important parameters
                shown = 0
                for key, value in params.items():
                    if shown >= 3:
                        break
                    if isinstance(value, float):
                        print(f"  • {key}: {value:.2f}")
                    else:
                        print(f"  • {key}: {value}")
                    shown += 1

                if len(params) > 3:
                    print(f"  ... and {len(params)-3} more parameters")

def main():
    """Generate morning report for D-REAM evolution."""
    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║    D-REAM EVOLUTION MORNING REPORT        ║{RESET}")
    print(f"{BOLD}{CYAN}║    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                 ║{RESET}")
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════╝{RESET}\n")

    # Load evolution data for all domains
    evolution_dir = Path('/home/kloros/src/dream/artifacts/domain_evolution')
    domains = ['cpu', 'gpu', 'audio', 'memory', 'storage', 'asr_tts', 'power_thermal', 'os_scheduler']

    all_data = {}
    for domain in domains:
        evolution_file = evolution_dir / f"{domain}_evolution.jsonl"
        all_data[domain] = load_evolution_data(evolution_file)

    # Print individual domain reports
    print(f"{BOLD}=== DOMAIN STATUS ==={RESET}\n")
    for domain in domains:
        print(f"{BOLD}{domain.upper()}{RESET}")
        print_domain_report(domain, all_data[domain])

    # Print summary statistics
    print_summary_statistics(all_data)

    # Print recommendations
    print_recommendations(all_data)

    # Print best configurations
    print_best_configurations(all_data)

    # Service status check
    print(f"\n{BOLD}=== SERVICE STATUS ==={RESET}")

    # Check if service is running
    import subprocess
    try:
        result = subprocess.run(['systemctl', 'is-active', 'dream-domains.service'],
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"Service: {GREEN}● Active{RESET}")

            # Get uptime
            result = subprocess.run(['systemctl', 'show', 'dream-domains.service', '-p', 'ActiveEnterTimestamp'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                # Parse timestamp
                timestamp_line = result.stdout.strip()
                if '=' in timestamp_line:
                    timestamp_str = timestamp_line.split('=', 1)[1].strip()
                    print(f"Uptime: {timestamp_str}")
        else:
            print(f"Service: {RED}○ Inactive{RESET}")
            print(f"  {YELLOW}Run: sudo systemctl start dream-domains.service{RESET}")
    except:
        print(f"Service: {YELLOW}Unknown{RESET}")

    print(f"\n{BOLD}=== NEXT STEPS ==={RESET}")
    print(f"1. Review domain-specific improvements above")
    print(f"2. Consider applying best configurations for high-fitness domains")
    print(f"3. Adjust safety constraints for well-performing domains")
    print(f"4. Switch back to daytime schedule if needed:")
    print(f"   {CYAN}sudo -u kloros cp /home/kloros/.kloros/dream_domain_schedules_daytime.json /home/kloros/.kloros/dream_domain_schedules.json{RESET}")
    print(f"   {CYAN}sudo systemctl restart dream-domains.service{RESET}")

    print(f"\n{GREEN}Report complete!{RESET}\n")

if __name__ == '__main__':
    main()