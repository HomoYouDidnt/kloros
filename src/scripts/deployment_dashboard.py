#!/usr/bin/env python3
"""
Simple, Reliable Deployment Dashboard for Cohort 1
Monitors shadow validation metrics in real-time
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

METRICS_DIR = Path("/home/kloros/.kloros/metrics")
COHORT_1_NICHES = ["maintenance_housekeeping", "observability_logging"]

# Alert thresholds
WARN_DRIFT = 5.0  # %
FREEZE_DRIFT = 10.0  # %
ROLLBACK_DRIFT = 20.0  # %


def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')


def colorize(text, color):
    """Simple ANSI color codes"""
    colors = {
        'green': '\033[92m',
        'yellow': '\033[93m',
        'red': '\033[91m',
        'blue': '\033[94m',
        'gray': '\033[90m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"


def load_shadow_metrics(niche):
    """Load shadow metrics for a niche"""
    metrics_file = METRICS_DIR / f"shadow_{niche}.json"

    if not metrics_file.exists():
        return None

    try:
        with open(metrics_file) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def format_duration(hours):
    """Format hours as human-readable duration"""
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m"


def get_status_color(drift, errors):
    """Determine status color based on drift and errors"""
    if errors > 0:
        return 'red'
    elif drift >= ROLLBACK_DRIFT:
        return 'red'
    elif drift >= FREEZE_DRIFT:
        return 'red'
    elif drift >= WARN_DRIFT:
        return 'yellow'
    else:
        return 'green'


def render_niche_panel(metrics):
    """Render a single niche monitoring panel"""
    if metrics is None:
        return colorize("  [NO DATA]", 'gray')

    if "error" in metrics:
        return colorize(f"  [ERROR: {metrics['error']}]", 'red')

    niche = metrics.get("niche", "unknown")
    elapsed = metrics.get("elapsed_hours", 0)
    total_exec = metrics.get("total_executions", 0)
    success = metrics.get("successful_executions", 0)
    failed = metrics.get("failed_executions", 0)

    max_drift = metrics.get("max_drift_percentage", 0)
    avg_drift = metrics.get("avg_drift_percentage", 0)
    curr_drift = metrics.get("current_drift_percentage", 0)

    legacy_errors = metrics.get("legacy_error_count", 0)
    wrapper_errors = metrics.get("wrapper_error_count", 0)

    rollback = metrics.get("rollback_triggered", False)
    eligible = metrics.get("promotion_eligible", False)

    # Progress
    target_hours = 24.0
    progress_pct = min(100, (elapsed / target_hours) * 100)
    remaining = max(0, target_hours - elapsed)

    # Status color
    total_errors = legacy_errors + wrapper_errors
    status_color = get_status_color(max_drift, total_errors)

    # Build panel
    lines = []
    lines.append(colorize(f"┌─ {niche.upper().replace('_', ' ')} ", 'bold') + "─" * (60 - len(niche)))
    lines.append(f"│")

    # Progress bar
    bar_width = 50
    filled = int((progress_pct / 100) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    lines.append(f"│  Progress: [{colorize(bar, status_color)}] {progress_pct:.1f}%")
    lines.append(f"│  Elapsed:  {format_duration(elapsed)} / 24h  ({colorize(format_duration(remaining), 'blue')} remaining)")
    lines.append(f"│")

    # Execution stats
    success_rate = (success / total_exec * 100) if total_exec > 0 else 0
    lines.append(f"│  Executions: {total_exec:,}  (✓ {success:,}  ✗ {failed:,}  {success_rate:.1f}%)")
    lines.append(f"│")

    # Drift stats
    drift_color = get_status_color(max_drift, 0)
    lines.append(f"│  Drift:  Max {colorize(f'{max_drift:.4f}%', drift_color)}  Avg {avg_drift:.4f}%  Current {curr_drift:.4f}%")
    lines.append(f"│")

    # Error counts
    error_color = 'red' if total_errors > 0 else 'green'
    lines.append(f"│  Errors:  Legacy {colorize(str(legacy_errors), error_color)}  Wrapper {colorize(str(wrapper_errors), error_color)}")
    lines.append(f"│")

    # Status flags
    rollback_status = colorize("YES", 'red') if rollback else colorize("NO", 'green')
    eligible_status = colorize("YES", 'green') if eligible else colorize("NO", 'gray')
    lines.append(f"│  Rollback Triggered: {rollback_status}    Promotion Eligible: {eligible_status}")

    lines.append("└" + "─" * 65)

    return "\n".join(lines)


def render_dashboard():
    """Render the complete dashboard"""
    clear_screen()

    # Header
    print(colorize("=" * 70, 'bold'))
    print(colorize(" COHORT 1 DEPLOYMENT DASHBOARD - Shadow Validation Monitor ", 'bold'))
    print(colorize("=" * 70, 'bold'))
    print()

    # System time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  {colorize('System Time:', 'gray')} {now}")
    print()

    # Render each niche
    for niche in COHORT_1_NICHES:
        metrics = load_shadow_metrics(niche)
        print(render_niche_panel(metrics))
        print()

    # Alert summary
    all_metrics = [load_shadow_metrics(n) for n in COHORT_1_NICHES]
    valid_metrics = [m for m in all_metrics if m and "error" not in m]

    if valid_metrics:
        max_drift_overall = max(m.get("max_drift_percentage", 0) for m in valid_metrics)
        total_errors = sum(m.get("legacy_error_count", 0) + m.get("wrapper_error_count", 0) for m in valid_metrics)
        any_rollback = any(m.get("rollback_triggered", False) for m in valid_metrics)
        all_eligible = all(m.get("promotion_eligible", False) for m in valid_metrics)

        print(colorize("─" * 70, 'gray'))
        print()

        # Alert status
        if any_rollback:
            print(colorize("  🚨 ALERT: Rollback triggered!", 'red'))
        elif total_errors > 0:
            print(colorize(f"  ⚠️  WARNING: {total_errors} errors detected", 'yellow'))
        elif max_drift_overall >= WARN_DRIFT:
            print(colorize(f"  ⚠️  WARNING: Drift {max_drift_overall:.4f}% exceeds threshold", 'yellow'))
        elif all_eligible:
            print(colorize("  ✅ READY: All niches eligible for promotion", 'green'))
        else:
            print(colorize("  ⏳ VALIDATING: Shadow deployment in progress...", 'blue'))

        print()
        print(colorize("─" * 70, 'gray'))

    # Footer
    print()
    print(colorize("  Press Ctrl+C to exit  |  Refreshing every 5 seconds", 'gray'))
    print()


def main():
    """Main dashboard loop"""
    try:
        while True:
            render_dashboard()
            time.sleep(5)
    except KeyboardInterrupt:
        clear_screen()
        print(colorize("\n  Dashboard stopped.\n", 'gray'))
        sys.exit(0)


if __name__ == "__main__":
    main()
