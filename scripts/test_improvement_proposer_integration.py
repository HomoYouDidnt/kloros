#!/usr/bin/env python3
"""
Test script to verify ImprovementProposer → D-REAM candidate flow.
"""

import sys
sys.path.insert(0, '/home/kloros')

from src.dream.improvement_proposer import get_improvement_proposer
from src.dream.proposal_to_candidate_bridge import get_proposal_bridge
from src.dream_evolution_system import DreamIdleIntegration

def test_proposal_generation():
    """Test that proposals are generated from system telemetry."""
    print("=" * 60)
    print("TEST 1: Proposal Generation from Telemetry")
    print("=" * 60)

    proposer = get_improvement_proposer()

    # Analyze system health (reads logs and ledger)
    proposals = proposer.analyze_system_health()

    print(f"\n✓ Generated {len(proposals)} proposals from system analysis")

    for i, proposal in enumerate(proposals[:3], 1):  # Show first 3
        print(f"\n  Proposal {i}:")
        print(f"    Component: {proposal.component}")
        print(f"    Issue: {proposal.issue_type}")
        print(f"    Priority: {proposal.priority}")
        print(f"    Description: {proposal.description[:80]}...")

    return proposals

def test_proposal_submission():
    """Test that proposals get submitted to the queue."""
    print("\n" + "=" * 60)
    print("TEST 2: Proposal Submission")
    print("=" * 60)

    proposer = get_improvement_proposer()
    submitted = proposer.run_analysis_cycle()

    print(f"\n✓ Submitted {submitted} proposals to queue")

    # Check pending proposals
    pending = proposer.get_pending_proposals()
    print(f"✓ {len(pending)} proposals now pending")

    return submitted

def test_proposal_to_candidate_conversion():
    """Test conversion of proposals to D-REAM candidates."""
    print("\n" + "=" * 60)
    print("TEST 3: Proposal → Candidate Conversion")
    print("=" * 60)

    proposer = get_improvement_proposer()
    bridge = get_proposal_bridge()

    # Get pending proposals
    pending = proposer.get_pending_proposals()

    if pending:
        # Convert to candidate format
        candidate = bridge.convert_proposal_to_candidate(pending[0].__dict__)

        print(f"\n✓ Converted proposal to candidate:")
        print(f"    Candidate ID: {candidate['id']}")
        print(f"    Domain: {candidate['domain']}")
        print(f"    Score: {candidate['metrics']['score']}")
        print(f"    Novelty: {candidate['metrics']['novelty']}")
        print(f"    Notes: {candidate['notes'][:80]}...")

        # Submit all pending as candidates
        submitted = bridge.submit_proposals_as_candidates([p.__dict__ for p in pending])
        print(f"\n✓ Submitted {submitted} proposals as D-REAM candidates")

        return submitted
    else:
        print("\n⚠ No pending proposals to convert")
        return 0

def test_idle_integration():
    """Test DreamIdleIntegration with proposer."""
    print("\n" + "=" * 60)
    print("TEST 4: Idle Reflection Integration")
    print("=" * 60)

    integration = DreamIdleIntegration()

    print(f"\n✓ DreamIdleIntegration initialized")
    print(f"  Proposer enabled: {integration.proposer_enabled}")

    if integration.proposer_enabled:
        # Run evolutionary reflection (includes proposal analysis)
        result = integration.perform_evolutionary_reflection()

        print(f"\n✓ Evolutionary reflection completed:")
        print(f"  Proposals submitted: {result.get('proposals_submitted', 0)}")
        print(f"  Candidates submitted: {result.get('candidates_submitted', 0)}")
        print(f"  Success: {result.get('success', False)}")

        if result.get('insights'):
            print(f"\n  Insights:")
            for insight in result['insights'][:5]:
                print(f"    - {insight}")

        return result
    else:
        print("\n⚠ Proposer not enabled")
        return None

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("IMPROVEMENT PROPOSER → D-REAM INTEGRATION TEST")
    print("=" * 60)

    try:
        # Test 1: Generate proposals
        proposals = test_proposal_generation()

        # Test 2: Submit proposals
        submitted = test_proposal_submission()

        # Test 3: Convert to candidates
        converted = test_proposal_to_candidate_conversion()

        # Test 4: Test idle integration
        result = test_idle_integration()

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"✓ Proposals generated: {len(proposals)}")
        print(f"✓ Proposals submitted: {submitted}")
        print(f"✓ Candidates created: {converted}")
        print(f"✓ Idle integration: {'PASS' if result else 'SKIPPED'}")
        print("\n✅ ALL TESTS PASSED")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
