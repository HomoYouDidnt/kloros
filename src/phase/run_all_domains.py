#!/usr/bin/env python3
"""
PHASE Multi-Domain Test Runner

Runs all PHASE domain tests: TTS, Conversation, RAG
Results written to phase_report.jsonl for D-REAM evolution
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/home/kloros')

from src.phase.domains.tts_domain import TTSDomain, TTSTestConfig
from src.phase.domains.conversation_domain import ConversationDomain, ConversationTestConfig
from src.phase.domains.rag_context_domain import RAGDomain, RAGTestConfig
from src.phase.domains.code_repair import run_single_epoch_test
from src.phase.domains.system_health_domain import SystemHealthDomain, SystemHealthTestConfig
from src.phase.domains.mcp_domain import run_mcp_domain
from src.dev_agent.llm_integration import create_llm_callable

def main():
    """Run all PHASE domain tests."""
    epoch_id = f"phase_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("=" * 80)
    print("PHASE Multi-Domain Test Suite")
    print("=" * 80)
    print(f"Epoch ID: {epoch_id}")
    print()

    total_tests = 0
    total_passed = 0
    repo_root = Path('/home/kloros')

    # Initialize LLM for code repair (if available)
    try:
        llm = create_llm_callable()
        print("✓ LLM initialized for code repair domain")
    except Exception as e:
        llm = None
        print(f"⚠ LLM unavailable, code repair will run validation only: {e}")

    # 1. TTS Domain
    print("\n[1/6] TTS Domain Tests...")
    try:
        tts_config = TTSTestConfig(
            backends=["mock"],  # Expand to ["piper", "xtts_v2"] when models available
            test_texts=["Hello, this is a PHASE test."]
        )
        tts_domain = TTSDomain(tts_config)
        tts_results = tts_domain.run_all_tests(epoch_id=epoch_id)
        tts_summary = tts_domain.get_summary()

        print(f"  ✓ {tts_summary['total_tests']} tests, {tts_summary['pass_rate']*100:.0f}% pass rate")
        total_tests += tts_summary['total_tests']
        total_passed += int(tts_summary['pass_rate'] * tts_summary['total_tests'])
    except Exception as e:
        print(f"  ✗ TTS domain failed: {e}")

    # 2. Conversation Domain
    print("\n[2/6] Conversation Domain Tests...")
    try:
        conv_config = ConversationTestConfig()
        conv_domain = ConversationDomain(conv_config)
        conv_results = conv_domain.run_all_tests(epoch_id=epoch_id)
        conv_summary = conv_domain.get_summary()

        print(f"  ✓ {conv_summary['total_tests']} tests, {conv_summary['pass_rate']*100:.0f}% pass rate")
        total_tests += conv_summary['total_tests']
        total_passed += int(conv_summary['pass_rate'] * conv_summary['total_tests'])
    except Exception as e:
        print(f"  ✗ Conversation domain failed: {e}")

    # 3. RAG Domain
    print("\n[3/6] RAG Context Domain Tests...")
    try:
        rag_config = RAGTestConfig()
        rag_domain = RAGDomain(rag_config)
        rag_results = rag_domain.run_all_tests(epoch_id=epoch_id)
        rag_summary = rag_domain.get_summary()

        print(f"  ✓ {rag_summary['total_tests']} tests, {rag_summary['pass_rate']*100:.0f}% pass rate")
        total_tests += rag_summary['total_tests']
        total_passed += int(rag_summary['pass_rate'] * rag_summary['total_tests'])
    except Exception as e:
        print(f"  ✗ RAG domain failed: {e}")

    # 4. Code Repair Domain
    print("\n[4/6] Code Repair Domain Tests...")
    try:
        repair_result = run_single_epoch_test(
            repo_root=repo_root,
            epoch_id=epoch_id,
            llm_callable=llm
        )

        status_icon = "✓" if repair_result['status'] == 'pass' else "✗"
        print(f"  {status_icon} Tests: {'PASS' if repair_result['tests_passed'] else 'FAIL'}, "
              f"Lint: {'PASS' if repair_result['lint_passed'] else 'FAIL'}, "
              f"Bugs fixed: {repair_result['bugs_fixed']}")

        total_tests += 1
        if repair_result['status'] == 'pass':
            total_passed += 1
    except Exception as e:
        print(f"  ✗ Code repair domain failed: {e}")
        import traceback
        traceback.print_exc()

    # 5. System Health Domain
    print("\n[5/6] System Health Domain Tests...")
    try:
        health_config = SystemHealthTestConfig()
        health_domain = SystemHealthDomain(health_config)
        health_results = health_domain.run_all_tests(epoch_id=epoch_id)
        health_summary = health_domain.get_summary()

        print(f"  ✓ {health_summary['total_tests']} tests, {health_summary['pass_rate']*100:.0f}% pass rate, "
              f"{health_summary['remediations_successful']}/{health_summary['issues_detected']} issues remediated")
        total_tests += health_summary['total_tests']
        total_passed += int(health_summary['pass_rate'] * health_summary['total_tests'])
    except Exception as e:
        print(f"  ✗ System health domain failed: {e}")
        import traceback
        traceback.print_exc()

    # 6. MCP Domain
    print("\n[6/6] MCP Domain Tests...")
    try:
        mcp_result = run_mcp_domain(epoch_id)

        status_icon = "✓" if mcp_result['status'] == 'pass' else "✗"
        print(f"  {status_icon} {mcp_result['tests_passed']}/{mcp_result['total_tests']} tests, "
              f"{mcp_result['tests_passed']/mcp_result['total_tests']*100:.0f}% pass rate")

        total_tests += mcp_result['total_tests']
        total_passed += mcp_result['tests_passed']
    except Exception as e:
        print(f"  ✗ MCP domain failed: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print("\n" + "=" * 80)
    print("PHASE Test Suite Complete")
    print("=" * 80)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {total_passed}")
    print(f"Pass rate: {total_passed/total_tests*100:.1f}%")
    print(f"\nResults written to: ~/kloros_loop/phase_report.jsonl")
    print("Run bridge to feed D-REAM:")
    print("  /home/kloros/src/phase/bridge_phase_to_dream.py")

    # Emit completion signals for orchestration
    try:
        import hashlib
        import json
        import time
        import os

        report_path = Path("/home/kloros/kloros_loop/phase_report.jsonl").resolve()
        signal_home = Path("/home/kloros/.kloros/signals")
        signal_home.mkdir(parents=True, exist_ok=True)

        # Touch file to /tmp (simple existence check)
        touch_file = Path(f"/tmp/klr_phase_complete_{epoch_id}")
        touch_file.touch()

        # Write JSON payload to protected location with SHA256
        if report_path.exists():
            sha256_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
        else:
            sha256_hash = "no_report"

        payload = {
            "epoch_id": epoch_id,
            "ts": int(time.time()),
            "report": str(report_path),  # Absolute path
            "sha256": sha256_hash
        }

        payload_file = signal_home / f"klr_phase_complete_{epoch_id}.json"
        payload_file.write_text(json.dumps(payload, indent=2))
        os.chmod(payload_file, 0o640)  # Restricted permissions

        print(f"\n✓ Orchestration signals emitted: {epoch_id}")

    except Exception as e:
        print(f"\n⚠ Warning: Failed to emit orchestration signals: {e}")

if __name__ == "__main__":
    main()
