---
doc_type: capability
capability_id: agent.browser
status: enabled
last_updated: '2025-11-22T18:32:26.484083'
drift_status: missing_module
---
# agent.browser

## Purpose

Provides: web_navigate, extract_content, web_automation

Kind: tool
## Scope

Documentation: docs/browser_agent.md

Tests:
- browser_agent_test

## Implementations

Referenced modules:

### playwright (NOT FOUND)

Preconditions:
- module:playwright importable
- path:/home/kloros/.venv/bin/playwright executable

## Telemetry

Health check: `python:playwright_browser_check`

Cost:
- CPU: 20
- Memory: 512 MB
- Risk: medium

## Drift Status

**Status:** MISSING_MODULE

One or more required modules are not found in the index.

Details:
- Module 'playwright' referenced but not found in index

