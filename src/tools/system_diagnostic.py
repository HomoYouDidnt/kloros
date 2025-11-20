#!/usr/bin/env python3
"""
System Diagnostic Tool for KLoROS
Performs comprehensive system diagnostics and logs all findings to a single file.
"""

import os
import sys
import json
import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple


class SystemDiagnostic:
    """Comprehensive system diagnostic tool for KLoROS."""

    def __init__(self, output_dir: str = "/home/kloros/logs/diagnostics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.findings = {
            'critical': [],
            'warning': [],
            'info': [],
            'success': []
        }
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.output_dir / f"diagnostic_{self.timestamp}.log"

    def log(self, message: str, level: str = 'info'):
        """Log a finding with severity level."""
        self.findings[level].append(message)

    def run_command(self, cmd: str, timeout: int = 10) -> Tuple[str, str, int]:
        """Run a shell command and return stdout, stderr, returncode."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", f"Command timeout after {timeout}s", -1
        except Exception as e:
            return "", str(e), -1

    def check_system_resources(self):
        """Check CPU, memory, disk usage."""
        self.log("=== System Resources ===", 'info')

        # Disk usage
        stdout, _, rc = self.run_command("df -h / /home /tmp | tail -n +2")
        if rc == 0:
            for line in stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 5:
                    usage_pct = int(parts[4].rstrip('%'))
                    mount = parts[5]
                    if usage_pct > 90:
                        self.log(f"CRITICAL: Disk {mount} at {usage_pct}% usage", 'critical')
                    elif usage_pct > 80:
                        self.log(f"WARNING: Disk {mount} at {usage_pct}% usage", 'warning')
                    else:
                        self.log(f"Disk {mount}: {usage_pct}% used", 'success')

        # Memory usage
        stdout, _, rc = self.run_command("free -h | grep Mem:")
        if rc == 0:
            parts = stdout.split()
            if len(parts) >= 3:
                self.log(f"Memory: {parts[2]} used of {parts[1]} total", 'info')

        # CPU load
        stdout, _, rc = self.run_command("uptime")
        if rc == 0:
            if 'load average:' in stdout:
                load = stdout.split('load average:')[1].strip()
                self.log(f"Load average: {load}", 'info')

    def check_systemd_services(self):
        """Check status of KLoROS-related systemd services."""
        self.log("\n=== Systemd Services ===", 'info')

        services = [
            'dream-runner.service',
            'dream-sync-promotions.service',
            'dream-sync-promotions.timer'
        ]

        for service in services:
            stdout, _, rc = self.run_command(f"sudo systemctl is-active {service}")
            status = stdout.strip()

            if status == 'active':
                self.log(f"Service {service}: active", 'success')
            elif status == 'inactive':
                self.log(f"Service {service}: inactive (may be oneshot)", 'warning')
            else:
                self.log(f"Service {service}: {status}", 'warning')

    def check_dream_status(self):
        """Check D-REAM evolution system status."""
        self.log("\n=== D-REAM Evolution System ===", 'info')

        # Check for recent experiments
        dream_logs = Path("/home/kloros/logs/dream")
        if dream_logs.exists():
            recent_logs = sorted(dream_logs.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if recent_logs:
                latest = recent_logs[0]
                age_hours = (datetime.now().timestamp() - latest.stat().st_mtime) / 3600
                self.log(f"Latest D-REAM log: {latest.name} ({age_hours:.1f} hours ago)", 'info')

                # Check for errors in recent log
                try:
                    with open(latest, 'r') as f:
                        content = f.read()
                        error_count = content.lower().count('error')
                        if error_count > 10:
                            self.log(f"D-REAM log contains {error_count} errors", 'warning')
                        else:
                            self.log(f"D-REAM log: {error_count} errors found", 'success')
                except Exception as e:
                    self.log(f"Failed to read D-REAM log: {e}", 'warning')
            else:
                self.log("No D-REAM logs found", 'warning')
        else:
            self.log("D-REAM logs directory not found", 'warning')

        # Check D-REAM database
        dream_db = Path("/home/kloros/.kloros/dream.db")
        if dream_db.exists():
            try:
                conn = sqlite3.connect(str(dream_db))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM experiments")
                exp_count = cursor.fetchone()[0]
                self.log(f"D-REAM database: {exp_count} experiments tracked", 'success')
                conn.close()
            except Exception as e:
                self.log(f"D-REAM database error: {e}", 'critical')
        else:
            self.log("D-REAM database not found", 'warning')

    def check_phase_results(self):
        """Check recent PHASE test results."""
        self.log("\n=== PHASE Test Results ===", 'info')

        test_runs = Path("/home/kloros/out/test_runs")
        if test_runs.exists():
            recent_runs = sorted(test_runs.glob("overnight-*"), key=lambda p: p.name, reverse=True)[:3]

            if recent_runs:
                for run_dir in recent_runs:
                    report = run_dir / "phase0_report.json"
                    if report.exists():
                        try:
                            with open(report, 'r') as f:
                                data = json.load(f)
                                total = data.get('total_tests', 0)
                                passed = data.get('passed_tests', 0)
                                failed = data.get('failed_tests', 0)
                                pass_rate = (passed / total * 100) if total > 0 else 0

                                if pass_rate >= 99.9:
                                    self.log(f"{run_dir.name}: {pass_rate:.2f}% pass rate ({passed}/{total})", 'success')
                                elif pass_rate >= 99.0:
                                    self.log(f"{run_dir.name}: {pass_rate:.2f}% pass rate ({passed}/{total})", 'warning')
                                else:
                                    self.log(f"{run_dir.name}: {pass_rate:.2f}% pass rate ({passed}/{total})", 'critical')
                        except Exception as e:
                            self.log(f"Failed to read {run_dir.name} report: {e}", 'warning')
                    else:
                        self.log(f"{run_dir.name}: No report found", 'warning')
            else:
                self.log("No recent PHASE test runs found", 'warning')
        else:
            self.log("PHASE test runs directory not found", 'info')

    def check_reflection_system(self):
        """Check idle reflection system status."""
        self.log("\n=== Reflection System ===", 'info')

        reflection_db = Path("/home/kloros/.kloros/reflection.db")
        if reflection_db.exists():
            try:
                conn = sqlite3.connect(str(reflection_db))
                cursor = conn.cursor()

                # Check recent reflections
                cursor.execute("""
                    SELECT COUNT(*) FROM reflections
                    WHERE timestamp > datetime('now', '-24 hours')
                """)
                recent_count = cursor.fetchone()[0]
                self.log(f"Reflections in last 24h: {recent_count}", 'info')

                # Check for errors
                cursor.execute("""
                    SELECT COUNT(*) FROM reflections
                    WHERE status = 'error' AND timestamp > datetime('now', '-7 days')
                """)
                error_count = cursor.fetchone()[0]
                if error_count > 10:
                    self.log(f"Reflection errors (7d): {error_count}", 'warning')
                elif error_count > 0:
                    self.log(f"Reflection errors (7d): {error_count}", 'info')
                else:
                    self.log("No reflection errors in last 7 days", 'success')

                conn.close()
            except Exception as e:
                self.log(f"Reflection database error: {e}", 'critical')
        else:
            self.log("Reflection database not found", 'warning')

    def check_audio_system(self):
        """Check audio system status."""
        self.log("\n=== Audio System ===", 'info')

        # Check PipeWire status
        stdout, _, rc = self.run_command("sudo -u kloros XDG_RUNTIME_DIR=/run/user/1001 pactl info 2>/dev/null | grep 'Server Name'")
        if rc == 0 and stdout:
            self.log(f"Audio server: {stdout.strip()}", 'success')
        else:
            self.log("Audio server status unknown", 'warning')

        # Check for audio device
        stdout, _, rc = self.run_command("aplay -l 2>/dev/null | grep -c 'card'")
        if rc == 0:
            card_count = stdout.strip()
            if card_count and int(card_count) > 0:
                self.log(f"Audio devices found: {card_count}", 'success')
            else:
                self.log("No audio devices found", 'warning')

    def check_database_integrity(self):
        """Check SQLite database integrity."""
        self.log("\n=== Database Integrity ===", 'info')

        databases = [
            Path("/home/kloros/.kloros/memory.db"),
            Path("/home/kloros/.kloros/dream.db"),
            Path("/home/kloros/.kloros/reflection.db")
        ]

        for db_path in databases:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()[0]
                    if result == 'ok':
                        self.log(f"{db_path.name}: OK", 'success')
                    else:
                        self.log(f"{db_path.name}: {result}", 'critical')
                    conn.close()
                except Exception as e:
                    self.log(f"{db_path.name}: Integrity check failed - {e}", 'critical')
            else:
                self.log(f"{db_path.name}: Not found", 'info')

    def check_recent_errors(self):
        """Check for recent errors in system logs."""
        self.log("\n=== Recent System Errors ===", 'info')

        # Check journalctl for KLoROS-related errors
        stdout, _, rc = self.run_command(
            "sudo journalctl -u 'dream-*' --since '24 hours ago' -p err --no-pager | wc -l"
        )
        if rc == 0:
            error_count = int(stdout.strip())
            if error_count > 10:
                self.log(f"Systemd errors (24h): {error_count}", 'warning')
            elif error_count > 0:
                self.log(f"Systemd errors (24h): {error_count}", 'info')
            else:
                self.log("No systemd errors in last 24h", 'success')

    def check_synthesis_queue(self):
        """Check autonomous synthesis queue status."""
        self.log("\n=== Autonomous Synthesis Queue ===", 'info')

        queue_file = Path("/home/kloros/.kloros/synthesis_queue.jsonl")
        if queue_file.exists():
            try:
                pending_count = 0
                with open(queue_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            proposal = json.loads(line)
                            if proposal.get('status') == 'pending':
                                pending_count += 1

                if pending_count > 0:
                    self.log(f"Pending synthesis proposals: {pending_count}", 'info')
                else:
                    self.log("No pending synthesis proposals", 'success')
            except Exception as e:
                self.log(f"Failed to read synthesis queue: {e}", 'warning')
        else:
            self.log("Synthesis queue file not found (may not have been used yet)", 'info')

    def generate_report(self) -> str:
        """Generate final diagnostic report and write to file."""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append(f"KLoROS System Diagnostic Report")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Summary
        report_lines.append("SUMMARY")
        report_lines.append("-" * 80)
        report_lines.append(f"Critical issues: {len(self.findings['critical'])}")
        report_lines.append(f"Warnings:        {len(self.findings['warning'])}")
        report_lines.append(f"Info items:      {len(self.findings['info'])}")
        report_lines.append(f"Successful:      {len(self.findings['success'])}")
        report_lines.append("")

        # Critical issues (if any)
        if self.findings['critical']:
            report_lines.append("CRITICAL ISSUES")
            report_lines.append("-" * 80)
            for finding in self.findings['critical']:
                report_lines.append(f"❌ {finding}")
            report_lines.append("")

        # Warnings (if any)
        if self.findings['warning']:
            report_lines.append("WARNINGS")
            report_lines.append("-" * 80)
            for finding in self.findings['warning']:
                report_lines.append(f"⚠️  {finding}")
            report_lines.append("")

        # Info items
        if self.findings['info']:
            report_lines.append("INFORMATION")
            report_lines.append("-" * 80)
            for finding in self.findings['info']:
                report_lines.append(f"ℹ️  {finding}")
            report_lines.append("")

        # Success items
        if self.findings['success']:
            report_lines.append("SUCCESSFUL CHECKS")
            report_lines.append("-" * 80)
            for finding in self.findings['success']:
                report_lines.append(f"✅ {finding}")
            report_lines.append("")

        report_lines.append("=" * 80)
        report_lines.append(f"End of diagnostic report")
        report_lines.append("=" * 80)

        # Write to file
        report_content = "\n".join(report_lines)
        with open(self.log_file, 'w') as f:
            f.write(report_content)

        return str(self.log_file)

    def run_full_diagnostic(self) -> str:
        """Run all diagnostic checks and generate report."""
        print(f"[diagnostic] Starting full system diagnostic...")

        self.check_system_resources()
        self.check_systemd_services()
        self.check_dream_status()
        self.check_phase_results()
        self.check_reflection_system()
        self.check_audio_system()
        self.check_database_integrity()
        self.check_recent_errors()
        self.check_synthesis_queue()

        log_path = self.generate_report()
        print(f"[diagnostic] Report generated: {log_path}")

        return log_path


def main():
    """CLI entry point."""
    diagnostic = SystemDiagnostic()
    log_path = diagnostic.run_full_diagnostic()

    # Print summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"Critical issues: {len(diagnostic.findings['critical'])}")
    print(f"Warnings:        {len(diagnostic.findings['warning'])}")
    print(f"Info items:      {len(diagnostic.findings['info'])}")
    print(f"Successful:      {len(diagnostic.findings['success'])}")
    print("=" * 80)
    print(f"\nFull report: {log_path}")

    return 0 if len(diagnostic.findings['critical']) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
