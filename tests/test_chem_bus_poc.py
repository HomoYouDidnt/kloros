#!/usr/bin/env python3
"""
Proof of Concept: Chemical Signal Bus
Tests that signals broadcast correctly and zooids can self-select to respond.
"""
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from kloros.orchestration.chem_bus import ChemPub, ChemSub
from kloros.orchestration.signal_router import SignalRouter

def test_direct_broadcast():
    """Test 1: Direct signal broadcast and subscription"""
    print("=" * 60)
    print("TEST 1: Direct Chemical Signal Broadcast")
    print("=" * 60)

    received_signals = []

    def on_signal(msg):
        print(f"  📡 Received: {msg['signal']} (intensity={msg['intensity']:.2f})")
        received_signals.append(msg)

    # Create publisher first (Unix socket needs this)
    print("\n1. Creating publisher...")
    pub = ChemPub(ipc_path="/tmp/test_chem.ipc")
    time.sleep(0.1)  # Let publisher socket be created

    # Create subscriber
    print("2. Creating subscriber for Q_LATENCY_SPIKE signals...")
    sub = ChemSub("Q_LATENCY_SPIKE", on_signal, ipc_path="/tmp/test_chem.ipc")
    time.sleep(0.1)  # Let subscriber initialize

    # Emit signal
    print("3. Broadcasting Q_LATENCY_SPIKE signal...")
    pub.emit(
        "Q_LATENCY_SPIKE",
        ecosystem="queue_management",
        intensity=0.73,
        facts={"p95_ms": 420, "queue_depth": 1800}
    )

    # Wait for delivery
    time.sleep(0.5)

    # Verify
    if received_signals:
        print(f"\n✅ SUCCESS: Received {len(received_signals)} signal(s)")
        print(f"   Signal: {received_signals[0]['signal']}")
        print(f"   Ecosystem: {received_signals[0]['ecosystem']}")
        print(f"   Facts: {received_signals[0]['facts']}")
    else:
        print("\n❌ FAILED: No signals received")

    # Cleanup
    sub.close()
    pub.close()

    return len(received_signals) > 0

def test_signal_router():
    """Test 2: Intent → Signal translation via SignalRouter"""
    print("\n" + "=" * 60)
    print("TEST 2: Intent → Signal Translation")
    print("=" * 60)

    received_signals = []

    def on_signal(msg):
        print(f"  📡 Received: {msg['signal']} from ecosystem {msg['ecosystem']}")
        received_signals.append(msg)

    # Create signal router first (contains publisher)
    print("\n1. Creating SignalRouter...")
    router = SignalRouter(chem_path="/tmp/test_router.ipc")
    time.sleep(0.1)

    # Create subscriber
    print("2. Creating subscriber for Q_ORPHANED_QUEUE signals...")
    sub = ChemSub("Q_ORPHANED_QUEUE", on_signal, ipc_path="/tmp/test_router.ipc")
    time.sleep(0.1)

    # Route intent
    print("3. Routing intent: queue.orphaned → Q_ORPHANED_QUEUE signal...")
    success = router.route_intent(
        "queue.orphaned",
        intensity=0.9,
        facts={"queue_name": "wake_phrases", "producer": "vosk_http_mode.py"},
        incident_id="inc-2025-11-07-001"
    )

    if success:
        print("   ✅ Intent successfully routed to signal")
    else:
        print("   ❌ Intent routing failed")

    # Wait for delivery
    time.sleep(0.5)

    # Verify
    if received_signals:
        print(f"\n✅ SUCCESS: Signal received from intent routing")
        print(f"   Original intent: queue.orphaned")
        print(f"   Signal emitted: {received_signals[0]['signal']}")
        print(f"   Incident ID: {received_signals[0]['incident_id']}")
    else:
        print("\n❌ FAILED: No signals received from intent routing")

    # Cleanup
    sub.close()
    router.close()

    return len(received_signals) > 0 and success

def test_multi_subscriber():
    """Test 3: Multiple zooids respond to same signal (colony behavior)"""
    print("\n" + "=" * 60)
    print("TEST 3: Multi-Zooid Response (Colony Behavior)")
    print("=" * 60)

    zooid_responses = {"latency_monitor": [], "backpressure_controller": []}

    def make_handler(zooid_name):
        def handler(msg):
            print(f"  🦠 {zooid_name} responding to {msg['signal']}")
            zooid_responses[zooid_name].append(msg)
        return handler

    # Create publisher first
    print("\n1. Creating signal broadcaster...")
    pub = ChemPub(ipc_path="/tmp/test_multi.ipc")
    time.sleep(0.1)

    # Simulate two zooids subscribing to same signal
    print("2. Spawning LatencyMonitor zooid...")
    sub1 = ChemSub("Q_LATENCY_SPIKE", make_handler("latency_monitor"), ipc_path="/tmp/test_multi.ipc")

    print("3. Spawning BackpressureController zooid...")
    sub2 = ChemSub("Q_LATENCY_SPIKE", make_handler("backpressure_controller"), ipc_path="/tmp/test_multi.ipc")

    time.sleep(0.1)

    # Broadcast signal
    print("4. Broadcasting Q_LATENCY_SPIKE signal...")
    pub.emit(
        "Q_LATENCY_SPIKE",
        ecosystem="queue_management",
        intensity=0.85,
        facts={"p95_ms": 550, "queue_depth": 2100}
    )

    # Wait for both zooids to respond
    time.sleep(0.5)

    # Verify
    monitor_responded = len(zooid_responses["latency_monitor"]) > 0
    controller_responded = len(zooid_responses["backpressure_controller"]) > 0

    if monitor_responded and controller_responded:
        print(f"\n✅ SUCCESS: Both zooids responded to signal")
        print(f"   LatencyMonitor: {len(zooid_responses['latency_monitor'])} responses")
        print(f"   BackpressureController: {len(zooid_responses['backpressure_controller'])} responses")
    else:
        print(f"\n❌ FAILED: Not all zooids responded")
        print(f"   LatencyMonitor: {'✅' if monitor_responded else '❌'}")
        print(f"   BackpressureController: {'✅' if controller_responded else '❌'}")

    # Cleanup
    sub1.close()
    sub2.close()
    pub.close()

    return monitor_responded and controller_responded

def main():
    print("\n🧬 KLoROS Chemical Signal Bus - Proof of Concept")
    print("Testing biological colony coordination via chemical signals\n")

    results = {
        "direct_broadcast": test_direct_broadcast(),
        "signal_router": test_signal_router(),
        "multi_subscriber": test_multi_subscriber()
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}  {test}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed! Chemical signal bus is functional.")
        print("\nThis proves:")
        print("  1. KLoROS can broadcast chemical signals")
        print("  2. Intents translate to signals correctly")
        print("  3. Multiple zooids self-select and respond")
        print("  4. Colony coordination emerges without RPC")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
