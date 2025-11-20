"""CLI tool to run browser automation plans from files."""
import asyncio
import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from browser_agent.agent.executor import BrowserExecutor
from browser_agent.agent.petri_policy import PetriPolicy
from browser_agent.plan_loader import load_plan

async def main():
    """Run plan from file."""
    parser = argparse.ArgumentParser(description="Execute browser automation plan")
    parser.add_argument("plan_file", help="Path to plan file (YAML or JSON)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with visible browser")
    parser.add_argument("--domains", nargs="+", help="Allowed domains")
    parser.add_argument("--max-actions", type=int, default=40, help="Maximum actions")
    parser.add_argument("--no-screenshots", action="store_false", dest="screenshots", default=True,
                        help="Disable per-step screenshots")

    args = parser.parse_args()

    print("🌐 KLoROS Browser Agent - Plan Executor")
    print("=" * 50)

    # Load plan
    try:
        plan = load_plan(args.plan_file)
        print(f"📋 Loaded plan: {args.plan_file}")
    except Exception as e:
        print(f"❌ Error loading plan: {e}")
        return 1

    # Create policy
    policy = PetriPolicy()
    policy.max_actions = args.max_actions
    policy.screenshot_every_step = args.screenshots

    # Set allowed domains
    if args.domains:
        policy.allow_domains = args.domains
    else:
        # Extract domain from start_url if present
        start_url = plan.get("meta", {}).get("start_url")
        if start_url:
            from urllib.parse import urlparse
            parsed = urlparse(start_url)
            if parsed.hostname:
                policy.allow_domains = [parsed.hostname]

    print(f"🎯 Target: {plan.get('meta', {}).get('start_url', 'N/A')}")
    print(f"🔧 Actions: {len(plan.get('actions', []))}")
    print(f"🔒 Allowed domains: {', '.join(policy.allow_domains)}")
    print(f"👁️  Headless: {args.headless}")
    print()

    # Execute plan
    async with BrowserExecutor(policy=policy, headless=args.headless) as executor:
        try:
            result = await executor.run_plan(plan)

            print(f"\n✅ Execution Complete")
            print(f"📁 Trace Directory: {result['trace_dir']}")
            print(f"📊 Steps Executed: {len(result['steps'])}")

            # Show success rate
            successes = sum(1 for s in result['steps'] if s.get('success'))
            print(f"✨ Success Rate: {successes}/{len(result['steps'])}")
            print()

            # Print extracted variables
            if result.get("vars"):
                print("📦 Extracted Variables:")
                for key, value in result["vars"].items():
                    preview = str(value)[:100]
                    if len(str(value)) > 100:
                        preview += "..."
                    print(f"  {key}: {preview}")
                print()

            # Print step results
            print("🔍 Step Results:")
            for step in result["steps"]:
                status = "✅" if step.get("success") else "❌"
                action = step.get("action", "unknown")
                step_num = step.get("step", 0)
                print(f"  {status} Step {step_num}: {action}")
                if step.get("error"):
                    print(f"     Error: {step['error']}")

            print()
            print("=" * 50)
            return 0

        except Exception as e:
            print(f"\n❌ Execution Failed: {e}")
            return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
