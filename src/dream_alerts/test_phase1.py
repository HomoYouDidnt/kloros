#!/usr/bin/env python3
"""
Comprehensive test suite for D-REAM Alert System Phase 1.
Tests the complete workflow from improvement detection to user approval.
"""

import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

# Add the dream_alerts directory to Python path
sys.path.insert(0, '/home/kloros/src')

try:
    from dream_alerts.alert_manager import DreamAlertManager
    from dream_alerts.next_wake_integration import NextWakeIntegrationAlert
    from dream_alerts.passive_indicators import PassiveIndicatorAlert, KLoROSIntrospectionIntegration
    from dream_alerts.alert_preferences import UserAlertPreferences
    from dream_alerts.alert_methods import ImprovementAlert
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all Phase 1 components are installed correctly.")
    sys.exit(1)


class Phase1TestSuite:
    """Comprehensive test suite for D-REAM Alert System Phase 1."""

    def __init__(self):
        self.test_results = []
        self.alert_manager = None
        self.test_improvement = {
            "task_id": "test_improvement_001",
            "component": "speech_recognition",
            "description": "Implement adaptive noise filtering to improve STT accuracy in noisy environments",
            "expected_benefit": "15-25% improvement in speech recognition accuracy",
            "risk_level": "low",
            "confidence": 0.82,
            "urgency": "medium",
            "detected_at": datetime.now().isoformat(),
            "implementation_details": {
                "files_to_modify": ["stt_backend.py", "audio_processing.py"],
                "estimated_lines": 45,
                "dependencies": ["scipy", "numpy"]
            }
        }

    def run_all_tests(self):
        """Run the complete Phase 1 test suite."""
        print("🧪 D-REAM Alert System Phase 1 Test Suite")
        print("=" * 50)

        self.test_alert_manager_initialization()
        self.test_user_preferences()
        self.test_next_wake_integration()
        self.test_passive_indicators()
        self.test_complete_workflow()
        self.test_user_response_parsing()
        self.test_error_handling()

        self.print_test_summary()

    def test_alert_manager_initialization(self):
        """Test 1: Alert Manager Initialization"""
        print("\n🔧 Test 1: Alert Manager Initialization")

        try:
            self.alert_manager = DreamAlertManager()

            # Register Phase 1 methods
            next_wake = NextWakeIntegrationAlert()
            passive = PassiveIndicatorAlert()

            self.alert_manager.register_alert_method("next_wake", next_wake)
            self.alert_manager.register_alert_method("passive", passive)

            # Verify registration
            registered_methods = list(self.alert_manager.alert_methods.keys())
            expected_methods = ["next_wake", "passive"]

            if all(method in registered_methods for method in expected_methods):
                self.log_test_result("Alert Manager Initialization", True, "All methods registered successfully")
            else:
                self.log_test_result("Alert Manager Initialization", False, f"Missing methods: {set(expected_methods) - set(registered_methods)}")

        except Exception as e:
            self.log_test_result("Alert Manager Initialization", False, f"Exception: {e}")

    def test_user_preferences(self):
        """Test 2: User Preferences System"""
        print("\n⚙️  Test 2: User Preferences System")

        try:
            prefs = UserAlertPreferences()

            # Test default preferences
            routing = prefs.get_routing_for_urgency("medium")
            expected_routing = ["next_wake", "passive"]

            if routing == expected_routing:
                self.log_test_result("Default Preferences", True, f"Medium urgency routing: {routing}")
            else:
                self.log_test_result("Default Preferences", False, f"Expected {expected_routing}, got {routing}")

            # Test quiet hours
            is_quiet = prefs.is_quiet_hours()  # Should work without throwing exception
            self.log_test_result("Quiet Hours Check", True, f"Quiet hours status: {is_quiet}")

            # Test preference updates
            success = prefs.update_preference("general_settings.max_pending", 10)
            if success:
                max_pending = prefs.get_max_pending_alerts()
                if max_pending == 10:
                    self.log_test_result("Preference Updates", True, f"Max pending updated to {max_pending}")
                else:
                    self.log_test_result("Preference Updates", False, f"Update failed, value is {max_pending}")
            else:
                self.log_test_result("Preference Updates", False, "Update operation failed")

        except Exception as e:
            self.log_test_result("User Preferences", False, f"Exception: {e}")

    def test_next_wake_integration(self):
        """Test 3: Next-Wake Integration"""
        print("\n🌅 Test 3: Next-Wake Integration")

        try:
            next_wake = NextWakeIntegrationAlert()

            # Create test alert
            alert = ImprovementAlert.from_improvement(self.test_improvement)

            # Test delivery
            result = next_wake.deliver_alert(alert)

            if result.success:
                self.log_test_result("Next-Wake Delivery", True, f"Alert queued: {alert.request_id}")

                # Test queue status
                queue_status = next_wake.get_queue_status()
                pending_count = queue_status["pending_count"]

                if pending_count == 1:
                    self.log_test_result("Next-Wake Queue", True, f"Queue has {pending_count} alert(s)")
                else:
                    self.log_test_result("Next-Wake Queue", False, f"Expected 1 alert, found {pending_count}")

                # Test message formatting
                pending_alerts = next_wake.get_pending_for_presentation()
                message = next_wake.format_next_wake_message(pending_alerts)

                if "APPROVE EVOLUTION" in message and alert.request_id in message:
                    self.log_test_result("Next-Wake Formatting", True, "Message contains approval commands")
                else:
                    self.log_test_result("Next-Wake Formatting", False, "Message formatting issues")

            else:
                self.log_test_result("Next-Wake Delivery", False, f"Delivery failed: {result.reason}")

        except Exception as e:
            self.log_test_result("Next-Wake Integration", False, f"Exception: {e}")

    def test_passive_indicators(self):
        """Test 4: Passive Indicators"""
        print("\n📊 Test 4: Passive Indicators")

        try:
            passive = PassiveIndicatorAlert()

            # Clear any existing indicators
            passive.clear_all_indicators()

            # Create test alert
            alert = ImprovementAlert.from_improvement(self.test_improvement)

            # Test delivery
            result = passive.deliver_alert(alert)

            if result.success:
                self.log_test_result("Passive Delivery", True, f"Status indicators updated")

                # Test status file creation
                status = passive.get_pending_status()
                pending_count = status.get("pending_count", 0)

                if pending_count == 1:
                    self.log_test_result("Passive Status File", True, f"Status file shows {pending_count} alert(s)")
                else:
                    self.log_test_result("Passive Status File", False, f"Expected 1 alert, found {pending_count}")

                # Test introspection data
                introspection = passive.get_introspection_data()
                if introspection["alert_system_active"] and introspection["pending_improvements"] == 1:
                    self.log_test_result("Passive Introspection", True, "Introspection data correct")
                else:
                    self.log_test_result("Passive Introspection", False, f"Introspection data: {introspection}")

                # Test status summary
                summary = passive.get_status_summary()
                if "1 improvement awaiting" in summary:
                    self.log_test_result("Passive Summary", True, f"Summary: {summary}")
                else:
                    self.log_test_result("Passive Summary", False, f"Unexpected summary: {summary}")

            else:
                self.log_test_result("Passive Delivery", False, f"Delivery failed: {result.reason}")

        except Exception as e:
            self.log_test_result("Passive Indicators", False, f"Exception: {e}")

    def test_complete_workflow(self):
        """Test 5: Complete End-to-End Workflow"""
        print("\n🔄 Test 5: Complete Workflow")

        try:
            if not self.alert_manager:
                self.log_test_result("Complete Workflow", False, "Alert manager not initialized")
                return

            # Test improvement notification
            result = self.alert_manager.notify_improvement_ready(self.test_improvement)

            if result["status"] == "processed":
                self.log_test_result("Improvement Processing", True, f"Alert ID: {result['alert_id']}")

                # Verify both methods received the alert
                methods_attempted = result["methods_attempted"]
                if methods_attempted >= 2:  # next_wake + passive
                    self.log_test_result("Multi-Method Delivery", True, f"{methods_attempted} methods attempted")
                else:
                    self.log_test_result("Multi-Method Delivery", False, f"Only {methods_attempted} methods attempted")

                # Test pending alerts retrieval
                pending = self.alert_manager.get_pending_alerts()
                if len(pending) >= 1:
                    self.log_test_result("Pending Alerts", True, f"{len(pending)} alert(s) pending")
                else:
                    self.log_test_result("Pending Alerts", False, "No pending alerts found")

            else:
                self.log_test_result("Improvement Processing", False, f"Processing failed: {result}")

        except Exception as e:
            self.log_test_result("Complete Workflow", False, f"Exception: {e}")

    def test_user_response_parsing(self):
        """Test 6: User Response Parsing"""
        print("\n💬 Test 6: User Response Parsing")

        try:
            if not self.alert_manager:
                self.log_test_result("User Response Parsing", False, "Alert manager not initialized")
                return

            # Test approval response
            approval_response = f"APPROVE EVOLUTION {self.test_improvement['task_id']}"
            result = self.alert_manager.process_user_response(approval_response, "test_channel")

            if result["success"] and result["action"] == "approved":
                self.log_test_result("Approval Response", True, f"Approved: {result['request_id']}")
            else:
                self.log_test_result("Approval Response", False, f"Approval failed: {result}")

            # Test status request
            status_response = "what improvements are pending?"
            result = self.alert_manager.process_user_response(status_response, "test_channel")

            if result["success"] and result["action"] == "status":
                self.log_test_result("Status Request", True, "Status request parsed correctly")
            else:
                self.log_test_result("Status Request", False, f"Status request failed: {result}")

        except Exception as e:
            self.log_test_result("User Response Parsing", False, f"Exception: {e}")

    def test_error_handling(self):
        """Test 7: Error Handling"""
        print("\n⚠️  Test 7: Error Handling")

        try:
            if not self.alert_manager:
                self.log_test_result("Error Handling", False, "Alert manager not initialized")
                return

            # Test invalid improvement data
            invalid_improvement = {"invalid": "data"}
            try:
                result = self.alert_manager.notify_improvement_ready(invalid_improvement)
                # Should handle gracefully without crashing
                self.log_test_result("Invalid Data Handling", True, "System handled invalid data gracefully")
            except Exception as e:
                self.log_test_result("Invalid Data Handling", False, f"System crashed on invalid data: {e}")

            # Test unknown response
            unknown_response = "this is not a valid command"
            result = self.alert_manager.process_user_response(unknown_response, "test_channel")

            if not result["success"] and "Could not parse response" in result["error"]:
                self.log_test_result("Unknown Response Handling", True, "Unknown response handled correctly")
            else:
                self.log_test_result("Unknown Response Handling", False, f"Unexpected result: {result}")

        except Exception as e:
            self.log_test_result("Error Handling", False, f"Exception: {e}")

    def log_test_result(self, test_name: str, success: bool, details: str):
        """Log a test result."""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {test_name} - {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def print_test_summary(self):
        """Print overall test summary."""
        print("\n" + "=" * 50)
        print("🏁 Test Summary")
        print("=" * 50)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")

        # Check Phase 1 completion status
        critical_components = [
            "Alert Manager Initialization",
            "Next-Wake Delivery",
            "Passive Delivery",
            "Improvement Processing"
        ]

        critical_passed = sum(1 for result in self.test_results
                            if result["test"] in critical_components and result["success"])

        print("\n🎯 Phase 1 Status:")
        if critical_passed == len(critical_components):
            print("✅ Phase 1 FULLY OPERATIONAL")
            print("   All critical components working correctly")
        else:
            print("⚠️  Phase 1 PARTIAL FUNCTIONALITY")
            print(f"   {critical_passed}/{len(critical_components)} critical components working")

        # Save test results
        self.save_test_results()

    def save_test_results(self):
        """Save test results to file."""
        results_file = Path("/home/kloros/.kloros/phase1_test_results.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)

        test_report = {
            "test_run_timestamp": datetime.now().isoformat(),
            "phase": "Phase 1",
            "total_tests": len(self.test_results),
            "passed_tests": sum(1 for r in self.test_results if r["success"]),
            "success_rate": f"{(sum(1 for r in self.test_results if r['success'])/len(self.test_results))*100:.1f}%",
            "test_results": self.test_results
        }

        with open(results_file, 'w') as f:
            json.dump(test_report, f, indent=2)

        print(f"\n📁 Test results saved to: {results_file}")


def main():
    """Run the Phase 1 test suite."""
    test_suite = Phase1TestSuite()
    test_suite.run_all_tests()


if __name__ == "__main__":
    main()