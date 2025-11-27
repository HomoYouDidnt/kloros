"""Demo script for browser agent."""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from browser_agent.agent.executor import BrowserExecutor
from browser_agent.agent.petri_policy import PetriPolicy

async def main():
    """Run browser agent demo."""
    print("🌐 KLoROS Browser Agent Demo")
    print("=" * 50)

    # Create policy
    policy = PetriPolicy()
    policy.allow_domains = ["example.com", "www.example.com"]

    # Create plan
    plan = {
        "meta": {
            "name": "Example.com Demo",
            "start_url": "https://example.com"
        },
        "actions": [
            {
                "type": "wait",
                "time_ms": 1000
            },
            {
                "type": "extract",
                "selector": "h1",
                "args": {"var_name": "page_title"}
            },
            {
                "type": "extract",
                "selector": "p",
                "args": {"var_name": "page_description"}
            },
            {
                "type": "evaluate",
                "script": "document.URL",
                "args": {"var_name": "current_url"}
            },
            {
                "type": "screenshot",
                "path": "example_page.png"
            }
        ]
    }

    # Execute plan
    print(f"\n📋 Plan: {plan['meta']['name']}")
    print(f"🎯 Target: {plan['meta']['start_url']}")
    print(f"🔧 Actions: {len(plan['actions'])}")
    print()

    async with BrowserExecutor(policy=policy, headless=True) as executor:
        result = await executor.run_plan(plan)

        print(f"\n✅ Execution Complete")
        print(f"📁 Trace Directory: {result['trace_dir']}")
        print(f"📊 Steps Executed: {len(result['steps'])}")
        print()

        # Print extracted variables
        if result.get("vars"):
            print("📦 Extracted Variables:")
            for key, value in result["vars"].items():
                preview = str(value)[:80]
                if len(str(value)) > 80:
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
        print("🎉 Demo Complete!")

if __name__ == "__main__":
    asyncio.run(main())
