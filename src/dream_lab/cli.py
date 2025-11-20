"""CLI interface for chaos experiments."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def run_experiment(spec_id: str, specs_path: str = None):
    """Run a single chaos experiment by ID.

    Args:
        spec_id: ID of the scenario to run
        specs_path: Optional path to specs YAML (default: fixtures/example_specs.yaml)
    """
    from src.dream_lab import load_specs, ChaosOrchestrator
    from src.self_heal import HealBus

    if specs_path is None:
        specs_path = str(Path(__file__).parent / "fixtures" / "example_specs.yaml")

    # Load specs
    specs = load_specs(specs_path)
    target_spec = next((s for s in specs if s.id == spec_id), None)

    if not target_spec:
        print(f"❌ Scenario '{spec_id}' not found")
        print(f"\nAvailable scenarios:")
        for spec in specs:
            print(f"  • {spec.id}: {spec.target}/{spec.mode}")
        return None

    print(f"🧪 Running chaos experiment: {spec_id}")
    print(f"   Target: {target_spec.target}")
    print(f"   Mode: {target_spec.mode}")
    print(f"   Params: {target_spec.params}")
    print()

    # Create minimal heal bus
    heal_bus = HealBus()

    # Initialize RAG backend with heal_bus for synthesis timeout testing
    rag_backend = None
    if target_spec.target.startswith("rag."):
        try:
            from src.reasoning.local_rag_backend import LocalRagBackend
            rag_backend = LocalRagBackend(heal_bus=heal_bus)
            print(f"[chaos] RAG backend initialized for {target_spec.target}")
        except Exception as e:
            print(f"[chaos] Failed to initialize RAG backend: {e}")

    # Create minimal KLoROS instance wrapper for chaos testing
    class MinimalKLoROS:
        def __init__(self, reason_backend=None):
            self.reason_backend = reason_backend

    kloros_instance = MinimalKLoROS(reason_backend=rag_backend)

    # Create orchestrator with backend access
    orchestrator = ChaosOrchestrator(
        heal_bus=heal_bus,
        safe_mode=True,
        kloros_instance=kloros_instance
    )

    # Run experiment
    try:
        result = orchestrator.run(target_spec)

        print("\n" + "="*60)
        print("📊 EXPERIMENT RESULTS")
        print("="*60)
        print(f"Scenario: {result['spec_id']}")
        print(f"Healed: {result['outcome'].get('healed')}")
        print(f"Score: {result['score']}/100")
        print(f"Duration: {result['outcome'].get('duration_s', 0):.1f}s")

        if result['outcome'].get('reason'):
            print(f"Reason: {result['outcome']['reason']}")

        print(f"\nEvents captured: {len(result['events'])}")
        for evt in result['events']:
            print(f"  • {evt['source']}.{evt['kind']} ({evt['severity']})")

        summary = result.get('summary', {})
        print(f"\nSummary:")
        print(f"  Total events: {summary.get('total_events', 0)}")
        print(f"  Duration: {summary.get('duration_s', 0):.1f}s")
        if summary.get('events_by_source'):
            print(f"  Events by source: {summary['events_by_source']}")

        heal_bus.shutdown()
        return result

    except KeyboardInterrupt:
        print("\n\n⚠️  Experiment interrupted by user")
        heal_bus.shutdown()
        return None
    except Exception as e:
        print(f"\n\n❌ Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        heal_bus.shutdown()
        return None


def list_scenarios(specs_path: str = None):
    """List all available chaos scenarios.

    Args:
        specs_path: Optional path to specs YAML
    """
    from src.dream_lab import load_specs

    if specs_path is None:
        specs_path = str(Path(__file__).parent / "fixtures" / "example_specs.yaml")

    specs = load_specs(specs_path)

    print("📋 Available Chaos Scenarios")
    print("="*60)

    for spec in specs:
        print(f"\n{spec.id}")
        print(f"  Target: {spec.target}")
        print(f"  Mode: {spec.mode}")
        print(f"  Max Duration: {spec.guards.get('max_duration_s', 20)}s")

        if spec.expected.get("heal_event"):
            evt = spec.expected["heal_event"]
            print(f"  Expected: {evt.get('source')}.{evt.get('kind')}")


def run_curriculum(count: int = 5):
    """Run an evolving curriculum of experiments.

    Args:
        count: Number of rounds to run
    """
    from src.dream_lab import load_specs, ChaosOrchestrator
    from src.dream_lab.mutators import evolve_curriculum
    from src.self_heal import HealBus

    specs_path = str(Path(__file__).parent / "fixtures" / "example_specs.yaml")

    # Load initial pool
    pool = load_specs(specs_path)
    print(f"🎓 Starting curriculum with {len(pool)} scenarios")
    print(f"   Running {count} rounds\n")

    # Create minimal heal bus
    heal_bus = HealBus()

    # Initialize RAG backend for synthesis tests
    try:
        from src.reasoning.local_rag_backend import LocalRagBackend
        rag_backend = LocalRagBackend(heal_bus=heal_bus)
        print("[chaos] RAG backend initialized for curriculum")
    except Exception as e:
        print(f"[chaos] Failed to initialize RAG backend: {e}")
        rag_backend = None

    # Create minimal KLoROS instance wrapper
    class MinimalKLoROS:
        def __init__(self, reason_backend=None):
            self.reason_backend = reason_backend

    kloros_instance = MinimalKLoROS(reason_backend=rag_backend)

    # Create orchestrator with backend access
    orchestrator = ChaosOrchestrator(
        heal_bus=heal_bus,
        safe_mode=True,
        kloros_instance=kloros_instance
    )

    all_results = []

    try:
        for round_num in range(1, count + 1):
            print(f"\n{'='*60}")
            print(f"📚 ROUND {round_num}/{count}")
            print(f"{'='*60}")
            print(f"Pool size: {len(pool)}")

            # Run experiments for this round
            round_results = []
            for i, spec in enumerate(pool[:10], 1):  # Run top 10 per round
                print(f"\n[{i}/10] Running: {spec.id}")
                result = orchestrator.run(spec)
                round_results.append(result)
                all_results.append(result)

                print(f"   Healed: {result['outcome'].get('healed')} | Score: {result['score']}/100")

            # Evolve curriculum
            print(f"\n🧬 Evolving curriculum...")
            pool = evolve_curriculum(round_results, pool, max_pool_size=50)
            print(f"   New pool size: {len(pool)}")

        # Final summary
        print(f"\n\n{'='*60}")
        print(f"📈 CURRICULUM SUMMARY")
        print(f"{'='*60}")
        print(f"Total experiments: {len(all_results)}")

        healed_count = sum(1 for r in all_results if r['outcome'].get('healed'))
        avg_score = sum(r['score'] for r in all_results) / len(all_results) if all_results else 0

        print(f"Healed: {healed_count}/{len(all_results)} ({healed_count/len(all_results)*100:.1f}%)")
        print(f"Average score: {avg_score:.1f}/100")

        # Top scenarios by teaching value
        from src.dream_lab.grading import rank_scenarios
        ranked = rank_scenarios(all_results)

        print(f"\n🏆 Top Teaching Scenarios:")
        for i, result in enumerate(ranked[:5], 1):
            print(f"  {i}. {result['spec_id']}: score={result['score']}/100")

        heal_bus.shutdown()

    except KeyboardInterrupt:
        print("\n\n⚠️  Curriculum interrupted by user")
        heal_bus.shutdown()
    except Exception as e:
        print(f"\n\n❌ Curriculum failed: {e}")
        import traceback
        traceback.print_exc()
        heal_bus.shutdown()


def main():
    """CLI entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(
        description="D-REAM Chaos Lab - Self-healing testing framework"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List command
    list_parser = subparsers.add_parser('list', help='List available scenarios')
    list_parser.add_argument('--specs', help='Path to specs YAML')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run a single experiment')
    run_parser.add_argument('scenario_id', help='Scenario ID to run')
    run_parser.add_argument('--specs', help='Path to specs YAML')

    # Curriculum command
    curr_parser = subparsers.add_parser('curriculum', help='Run evolving curriculum')
    curr_parser.add_argument('--rounds', type=int, default=5, help='Number of rounds')

    args = parser.parse_args()

    if args.command == 'list':
        list_scenarios(args.specs)
    elif args.command == 'run':
        run_experiment(args.scenario_id, args.specs)
    elif args.command == 'curriculum':
        run_curriculum(args.rounds)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
