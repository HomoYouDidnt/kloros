"""Browser executor with Playwright automation."""
import asyncio
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright
from .petri_policy import PetriPolicy
from .trace import TraceLogger
from .actions import parse_action, BrowserAction

class BrowserExecutor:
    """Execute browser automation plans with PETRI security."""

    def __init__(self, policy: Optional[PetriPolicy] = None, headless: bool = True):
        """Initialize browser executor.

        Args:
            policy: PETRI security policy (default: PetriPolicy())
            headless: Run browser in headless mode
        """
        self.policy = policy or PetriPolicy()
        self.policy.ensure_dirs()
        self.trace = TraceLogger(self.policy.trace_dir)
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()

    async def start(self):
        """Start browser."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()
            self.trace.log({"type": "browser_started", "headless": self.headless})

    async def stop(self):
        """Stop browser."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self.trace.log({"type": "browser_stopped"})

    async def run_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute browser automation plan.

        Args:
            plan: Plan dict with 'meta' and 'actions' keys

        Returns:
            Execution result with trace_dir, meta, and steps
        """
        meta = plan.get("meta", {})
        actions = plan.get("actions", [])
        start_url = meta.get("start_url")

        self.trace.log({
            "type": "plan_started",
            "plan_name": meta.get("name", "unnamed"),
            "num_actions": len(actions),
            "start_url": start_url
        })

        # Ensure browser is running
        if self._page is None:
            await self.start()

        # Navigate to start URL if provided
        if start_url:
            if not self.policy.check_domain(start_url):
                raise PermissionError(f"Domain not allowed: {start_url}")
            await self._page.goto(start_url)
            self.trace.log({"type": "navigation", "url": start_url})

        # Execute actions
        steps = []
        action_count = 0

        for i, action_dict in enumerate(actions):
            # Check action limit
            action_count += 1
            if action_count > self.policy.max_actions:
                self.trace.log({"type": "error", "message": f"Action limit exceeded ({self.policy.max_actions})"})
                break

            try:
                action = parse_action(action_dict)
                result = await self._execute_action(action, i)
                steps.append(result)

                # Screenshot on every step if configured
                if self.policy.screenshot_every_step:
                    screenshot_path = f"step_{i:03d}.png"
                    await self.trace.save_screenshot(self._page, screenshot_path)

            except Exception as e:
                error_msg = f"Action {i} failed: {str(e)}"
                self.trace.log({"type": "error", "step": i, "message": error_msg})
                steps.append({
                    "step": i,
                    "action": action_dict.get("type", "unknown"),
                    "success": False,
                    "error": error_msg
                })
                break

        # Save final variables
        self.trace.save_vars("final_vars.json")

        self.trace.log({
            "type": "plan_completed",
            "steps_executed": len(steps),
            "success": all(s.get("success", False) for s in steps)
        })

        return {
            "trace_dir": self.trace.run_dir,
            "meta": meta,
            "steps": steps,
            "vars": self.trace.vars
        }

    async def _execute_action(self, action: BrowserAction, step_num: int) -> Dict[str, Any]:
        """Execute single action.

        Args:
            action: Action to execute
            step_num: Step number

        Returns:
            Execution result
        """
        action_type = action.type
        timeout = action.timeout_ms or self.policy.action_timeout_s * 1000

        self.trace.log({
            "type": "action_start",
            "step": step_num,
            "action": action_type,
            "args": action.args
        })

        result = {
            "step": step_num,
            "action": action_type,
            "success": False
        }

        try:
            if action_type == "navigate":
                url = action.args.get("url") or getattr(action, "url", None)
                if not self.policy.check_domain(url):
                    raise PermissionError(f"Domain not allowed: {url}")
                await self._page.goto(url, timeout=timeout)
                result["url"] = url

            elif action_type == "click":
                selector = action.args.get("selector") or getattr(action, "selector", None)
                await self._page.click(selector, timeout=timeout)
                result["selector"] = selector

            elif action_type == "type":
                selector = action.args.get("selector") or getattr(action, "selector", None)
                text = action.args.get("text") or getattr(action, "text", "")
                await self._page.fill(selector, text, timeout=timeout)
                result["selector"] = selector
                result["text"] = text

            elif action_type == "wait":
                selector = action.args.get("selector") or getattr(action, "selector", None)
                time_ms = action.args.get("time_ms") or getattr(action, "time_ms", None)
                if selector:
                    await self._page.wait_for_selector(selector, timeout=timeout)
                    result["selector"] = selector
                elif time_ms:
                    await asyncio.sleep(time_ms / 1000)
                    result["time_ms"] = time_ms

            elif action_type == "extract":
                selector = action.args.get("selector") or getattr(action, "selector", None)
                attribute = action.args.get("attribute") or getattr(action, "attribute", None)
                element = await self._page.query_selector(selector)
                if element:
                    if attribute:
                        value = await element.get_attribute(attribute)
                    else:
                        value = await element.text_content()
                    result["value"] = value
                    # Store in vars
                    var_name = action.args.get("var_name", f"extract_{step_num}")
                    self.trace.vars[var_name] = value
                result["selector"] = selector

            elif action_type == "screenshot":
                path = action.args.get("path") or getattr(action, "path", None)
                if not path:
                    path = f"screenshot_{step_num}.png"
                full_path = await self.trace.save_screenshot(self._page, path)
                result["path"] = full_path

            elif action_type == "scroll":
                direction = action.args.get("direction") or getattr(action, "direction", "down")
                amount = action.args.get("amount") or getattr(action, "amount", 500)

                if direction == "down":
                    await self._page.evaluate(f"window.scrollBy(0, {amount})")
                elif direction == "up":
                    await self._page.evaluate(f"window.scrollBy(0, -{amount})")
                elif direction == "top":
                    await self._page.evaluate("window.scrollTo(0, 0)")
                elif direction == "bottom":
                    await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                result["direction"] = direction

            elif action_type == "evaluate":
                script = action.args.get("script") or getattr(action, "script", "")
                value = await self._page.evaluate(script)
                result["value"] = value
                # Store in vars
                var_name = action.args.get("var_name", f"eval_{step_num}")
                self.trace.vars[var_name] = value

            else:
                raise ValueError(f"Unknown action type: {action_type}")

            result["success"] = True
            self.trace.log({
                "type": "action_success",
                "step": step_num,
                "action": action_type
            })

        except Exception as e:
            result["error"] = str(e)
            self.trace.log({
                "type": "action_error",
                "step": step_num,
                "action": action_type,
                "error": str(e)
            })

        return result

    async def navigate(self, url: str):
        """Navigate to URL.

        Args:
            url: URL to navigate to
        """
        if not self.policy.check_domain(url):
            raise PermissionError(f"Domain not allowed: {url}")
        if self._page:
            await self._page.goto(url)

    async def get_content(self) -> str:
        """Get page content.

        Returns:
            Page HTML content
        """
        if self._page:
            return await self._page.content()
        return ""

    async def get_title(self) -> str:
        """Get page title.

        Returns:
            Page title
        """
        if self._page:
            return await self._page.title()
        return ""
