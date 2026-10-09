---
id: HAIFA-S08-T01
title: "Codex GPT-6.1-Sol, přepínání rosteru a živé limity dashboardu"
status: done
depends_on: []
writes: [aifactory/, app_docs/]
auto_merge: false
---

## Zadání
Implement the requested Codex/GPT-6.1-Sol support and useful switching for this existing backlog, plus current dashboard Codex 5h/week limits. Existing harness codex.py and web/limits.py already exist; extend them instead of duplicating workflows.

Where: aifactory/src/aifactory/config/, cli.py, harness/, web/limits.py, skill/, aifactory/web/src/, aifactory/tests/, app_docs/.

Done means:
- Add `factory config roster show` showing effective agent harness/model/thinking and `factory config roster set` to change the roster defaults or one named agent (`--agent NAME`). Accept a preset codex (gpt-6.1-sol, medium) or claude (claude-opus-5-5, medium), with explicit --harness/--model/--thinking overrides. Set all three together for preset switching so models are not accidentally inherited from a different harness. Whole-roster preset should intentionally reset existing per-agent harness/model/thinking overrides, retaining purposes, prompts, writes and other settings; role-specific preset affects only that role. Show resulting diff/change information; --dry-run, --json, --repo work. Validate all effective models/harnesses offline before writing, write atomically, reject unknown agents/invalid arguments without modifying files, preserve unrelated YAML fields. Preserve YAML comments if practical with existing dependencies. Avoid a new YAML format or new dependency unless necessary. Updates stay local until existing factory config commit; task/workflow read committed base as before. Document CLI help/skill and examples for all-Codex, all-Claude, mixed Codex builder + Claude reviewer. No backlog migrations and no duplicated workflows. Existing step overrides stay authoritative.
- Verify GPT-6.1-Sol medium command construction; add correct 1,050,000 context metadata and modern reasoning effort handling as appropriate without breaking existing adapters. Check Windows launch/argument compatibility with locally installed codex 0.160.0.
- Read live Codex subscription limits through `codex app-server` stdio JSON-RPC initialize/initialized then account/rateLimits/read, with bounded timeout, child cleanup and Windows hidden process behavior. Ignore user config/MCP if supported; do not start model turns or access/display auth tokens. Normalize camelCase primary/secondary windows (usedPercent, windowDurationMins, resetsAt) to existing dashboard shape; select the codex bucket from rateLimitsByLimitId when available. Only label actual 300-min and 10080-min windows 5h/week. Use existing LimitsSource TTL/stale fallback. Existing session-log fallback may remain but do not present old logs as freshly measured or pretend expired old windows are a new live measurement. If no current limits available, show explicit unavailable status in topbar with helpful tooltip instead of silently hiding Codex. Display both providers when configured, remaining percentage, reset, and stale status. Add frontend tests for Codex/both/unavailable and backend tests with fake process/RPC only, no models/network in tests.
- Write a short app_docs guide explaining roster vs workflow precedence and commands and the Codex limits source/fallback.
- Regression tests plus relevant mypy/Ruff/frontend checks pass. Do not change vendor/, prototype/, adws/, .factory/, CLAUDE.md or product brief. No unrelated backlog tasks.

Official references: https://developers.openai.com/api/docs/models/gpt-6.1-sol and https://learn.chatgpt.com/docs/app-server (account/rateLimits/read schema). Use local Codex help/schema if needed.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/63 · náklady $0.00
