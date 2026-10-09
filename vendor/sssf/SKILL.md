---
name: sssf
description: Super Simple Software Factory — deploy and operate repeatable agents+code workflows (ADWs) in any codebase. Use when the user says /sssf install, wants to create/run/update an ADW, manage the agent roster in sssf.config.yaml, or observe running agent workflows. Keywords - sssf, software factory, ADW, AI developer workflow, agent pipeline, install factory.
argument-hint: "[install | create adw | run adw | update config | ...]"
---

# Super Simple Software Factory (SSSF)

Reusable combination of **agents plus code**: deterministic Python ADW scripts own sequencing, retries, and acceptance; coding agents (pi and Claude Code) work inside bounded phases; typed JSON envelopes carry context between them; everything streams into SQLite for the polled visualizer. Agent proposes, code disposes.

## Startup

Three steps. Then stop.

1. Read [cookbooks/sssf_overview.md](cookbooks/sssf_overview.md) — the system map.
2. `ls adws/adw_*.py` and read each file's `Phases:` docstring line.
3. Print the ADWs as a table — name, the chain, one line on when to reach for it — and **wait for the engineer's request.**

```
| ADW | Chain | Use when |
|---|---|---|
| adw_scout | engineer → scout | read-only recon; nothing changes |
| adw_simple_sdlc | plan → build → test → review → document, 3 commits | the work is real and its shape is not obvious |
```

**Nothing else.** No trace-db queries, no reading the config or the ADW scripts' bodies, no repo inventory, no last-runs summary, no diagnosing an old failure, no "current state" dashboard. None of it was asked for, and it is not free:

- **Volunteered state is guessed state.** An orchestrator that improvised a status board queried a `runs` table and a `payload` column — neither exists (`sessions`, `payload_json`). The spec that would have said so is `references/observability.md`, one lazy read away. Probing to look prepared is how you end up confidently wrong in your first message.
- **It spends the context the real task needs**, before you know what the task is.
- **It is stale on arrival.** State printed before the request describes a system that the very next run changes.

Everything else — the db schema, the roster, the handoff contract — is lazy-loaded through the routing table below, when a request actually calls for it. Reading it early defeats the mechanism.

Two exceptions, both narrow: if the engineer's first message already contains a request, skip the waiting and route it; and if the factory is plainly not installed (no `adws/`, no config), say that in one line instead of the table.

## Orchestrator rules

You run the system, observe the system, and help the user interact with it. **You do no ADW work yourself:**

- Never implement, plan, or test in an agent's place — launch the ADW and watch it.
- Never edit files inside `adws/adw_data/sessions/` — that is the run record.
- Observe by querying `adws/adw_data/sssf.db` (WAL — reads never block writers) **when observing is the task**. This is a capability, not a startup step: query it to follow a run you launched or one the engineer asked about, never to volunteer a status report nobody requested.
- Report phase status plainly: name, owner, status, error if any.

## Multi-level planning workflow

For large projects, a single plan is insufficient. Use nested planning:

1. **High-level phase plan**: `adw_plan.py` to identify 4–8 major phases with clear deliverables and dependency ordering.
2. **Detailed step plan per phase**: `adw_plan.py` again for each phase, breaking it into individual implementation steps. Each step must specify: files to create/modify, what the code does, how to verify (exact test commands), and the deliverable.
3. **No forward dependencies**: Each step builds only on previous steps within its phase. Steps across phases never cross-depend.
4. **Parallelization**: Where the dependency graph allows (e.g., Phase 3 and Phase 4 both depend only on Phase 2), run them in parallel.

Pattern:
```bash
# Level 1: High-level phases
uv run adws/adw_plan.py "Identify major implementation phases for <project>..."

# Level 2: Detailed steps per phase (run sequentially or in parallel)
uv run adws/adw_plan.py "Create detailed implementation plan for Phase N: <title>. Context: <full project context>. Break into steps with files, commands, verification."
```

**Done when**: each phase plan has numbered steps with concrete verification commands, and the total step count across all phases gives the engineer a clear implementation roadmap.

## Backlog automation for multi-task projects

When a project involves many sequential tasks (30+), a `BACKLOG.md` with automated status tracking prevents manual update errors.

### Backlog structure

```markdown
# Project — Master Backlog

| # | Task | Status | adw_id | Commit | Docs |
|---|---|---|---|---|---|
| 1.1 | Description | 🔲 | — | — | — |
| 1.2 | Description | ✅ | abc1234 | 1c83c9a | — |

---
## Current Position
**Active task:** 1.2 (DONE)
**Completed:** 2 / 58
**Next up:** 1.3 — Description
```

Status legend: 🔲 TODO · 🔄 IN PROGRESS · ✅ DONE · ❌ FAILED

### Automation scripts

**`scripts/next-task.sh`** — picks first 🔲 task, generates spec from phase plan, runs SDLC. On start, marks task `IN_PROGRESS`; on completion, marks `DONE` with adw_id and commit SHA.

**`scripts/backlog-update.sh <task> <status> <adw_id> <commit>`** — updates a single task row in BACKLOG.md, refreshes completed count and current position. Use `perl -i -pe` for table row replacement (sed loses multi-line context on markdown pipes).

### Critical: verify success before marking done

The `next-task.sh` script MUST verify the SDLC run succeeded before updating the backlog to DONE. Capture the exit code of `uv run adws/adw_simple_sdlc.py` and only update on success. On failure:
1. Mark the task as FAILED in the backlog
2. Clean up the generated spec file (`rm -f specs/tasks/task-X.Y.md`)
3. Report the failure and STOP — do not proceed to the next task
4. The engineer must fix the issue and re-run manually

```bash
# In next-task.sh:
if uv run adws/adw_simple_sdlc.py "$SPEC_FILE"; then
    SDLC_EXIT=0
else
    SDLC_EXIT=1
fi

if [ "$SDLC_EXIT" -ne 0 ]; then
    bash "$SCRIPT_DIR/backlog-update.sh" "$TASK_NUM" FAILED "" ""
    rm -f "$SPEC_FILE"
    echo "❌ FAILED — fix and re-run"
    exit 1
fi
```

### Critical: clean up failed runs

Failed SDLC runs leave behind:
- Generated spec files in `specs/tasks/`
- Untracked files from partial implementations
- Stale `IN_PROGRESS` entries in the backlog

Before re-running a failed task, clean up:
```bash
rm -f specs/tasks/task-X.Y.md
# Remove any untracked files the failed run created
git status --short | grep '^??' | awk '{print $2}' | xargs rm -f
# Reset backlog status from IN_PROGRESS back to TODO
sed -i '' 's/| X.Y | .* | 🔄/| X.Y | DESCRIPTION | 🔲/' BACKLOG.md
```

### Critical: kill stale background processes

Background SDLC processes from failed runs accumulate and interfere. Before starting a new task, kill any running ADW processes:
```bash
pkill -f adw_simple_sdlc 2>/dev/null
pkill -f "adws/adw_plan" 2>/dev/null
sleep 1
```

### Planner writes: config

The planner agent's `writes:` list in `sssf.config.yaml` MUST include every path it needs to modify. For backlog-driven projects, this includes:
```yaml
writes:
  - specs/
  - tests/
  - BACKLOG.md
```

If the planner modifies a file outside its `writes:` list, the permission enforcement rolls back the change and kills the phase with `PermissionBreach`.

```bash
# Mark task IN_PROGRESS at start of next-task.sh
bash scripts/backlog-update.sh 1.3 IN_PROGRESS "" ""

# Mark task DONE with metadata at end of next-task.sh
bash scripts/backlog-update.sh 1.3 DONE abc1234 1c83c9a
```

**Justfile integration:**
```justfile
backlog:
	@TODO=$(grep -c '🔲' BACKLOG.md); DONE=$(grep -c '✅' BACKLOG.md); echo "TODO: $TODO / DONE: $DONE"

next:
	bash scripts/next-task.sh

done TASK:
	bash scripts/backlog-update.sh {{TASK}} DONE
```

## Request routing (lazy-load the cookbook, then follow it)

| Request | Cookbook |
|---|---|
| `/sssf install`, set up the factory in this repo | [cookbooks/install.md](cookbooks/install.md) |
| create a new ADW / workflow | [cookbooks/create_adw.md](cookbooks/create_adw.md) |
| modify an existing ADW chain | [cookbooks/update_adw.md](cookbooks/update_adw.md) |
| create the config / agent roster | [cookbooks/create_config.md](cookbooks/create_config.md) |
| add or retune an agent (model, thinking, tools, prompts) | [cookbooks/update_config.md](cookbooks/update_config.md) |
| extend adw_modules with new low-level logic | [cookbooks/update_modules.md](cookbooks/update_modules.md) |
| run / monitor an ADW | [cookbooks/how_to_prompt_for_the_eng.md](cookbooks/how_to_prompt_for_the_eng.md) **first**, then [cookbooks/run_adw.md](cookbooks/run_adw.md) |
| turn a request into an ADW prompt | [cookbooks/how_to_prompt_for_the_eng.md](cookbooks/how_to_prompt_for_the_eng.md) |
| compose a chain ad hoc, or save one as a recipe | `adws/adw_recipes/README.md` in the stamped repo — `adw_compose.py "plan@longcat -> build@opus -> test"` |

Deep specs, when needed: [references/config.md](references/config.md) · [references/handoff.md](references/handoff.md) · [references/observability.md](references/observability.md) · [references/pitfalls.md](references/pitfalls.md)

## Hard rules (enforced across everything the factory generates)

1. **Validate before running** — every ADW declares `REQUIRED_AGENTS` and calls `agents.validate()` first; a missing/misnamed agent fails before anything spawns.
2. **Typed outputs only** — every agent call pairs with a concrete `EnvelopeBase` subclass in `adw_modules/data_types.py`; parse failures re-prompt the same session (context intact), never restart.
   **The output contract is a synced triad**: (a) the type in `data_types.py`, (b) the JSON example in the agent's `user.md` `## Report` section, (c) `output_type=` at every call site. These are ONE contract — change any one, update all three in the same edit (grep the type name to find every call site).
3. **Gates validate claims, not guesses** — `gate(envelope, run) -> list[str]` violations; failures return to the same session as corrections.
4. **Four-param rule** — any function with more than 4 parameters takes one concrete data type instead (`AgentCall`, `PhaseParams` are the pattern).
5. **One agent, one prompt, one purpose** — identity lives in `system.md`; task shape (user prompt + output type) lives at the call site.
6. **ADW scripts stay thin** — all low-level logic lives in `adw_modules/`.
7. **Every phase earns a description** — one sentence on what it does and why, never a restatement of its name. It is the only intent the trace, the console, and the UI ever show; `commit_plan: "Commit the plan"` is rejected at construction, blank is too.
8. **A known command is code, not an agent** — if you can write the invocation down (`bun test`, `ruff check`), it belongs in a `kind="code"` phase via `adw_modules/quality.py`. Agents are for the parts that need reading and deciding; failures come back to the builder as an envelope either way.
9. **`tools:` is a capability list, `writes:` is the boundary** — `bash` runs anything (including `git checkout`) and `write` reaches any path, so a tool list can never make "this agent changes nothing" true. `writes:` per agent and `protected_files` in defaults are enforced in `adw_modules/permissions.py` after every agent call: unauthorized changes are rolled back and the phase dies. The session runtime under `data_dir` is always writable — a read-only agent is read-only with respect to the REPO, never mute.
10. **Every ADW ends in `run.finish()`** — phases passing is not the same as the run being accepted. A test phase that ran a red suite succeeded at its job. Pass `accepted=` so the exit code, the session status, and the banner are decided together and cannot disagree.

## Two coding agents

`coding_agent:` picks the harness per agent, and the model name is what decides it:

| | `pi` | `claude_code` |
|---|---|---|
| model | `provider/id` — `nousresearch/meituan/longcat-2.0:free` | alias or id — `opus`, `sonnet`, `haiku`, `fable`, `claude-opus-5` |
| thinking | `off`…`max` | mapped to `--effort` |
| extensions | `harness_engineering:` ts files | none — pi extensions are pi's |
| isolation | — | `--safe-mode`, MCP off: the operator's own CLAUDE.md, hooks and MCP roster never reach a factory agent (that roster cost ~67k prompt tokens a turn) |

`tools:` stays written in pi's vocabulary for both; `agent_cc.py` translates (`read`→`Read`, `find`→`Glob`) and passes unknown names through, so a Claude agent can also name `Task` or `WebSearch`.

**The model is a per-run choice, not a roster fact.** Every ADW takes `--model [AGENT=]MODEL`, and because the name says which harness runs it, one flag moves an agent between models, harnesses and price points:

```bash
uv run adws/adw_simple_sdlc.py "add /health" --model haiku          # whole chain
uv run adws/adw_simple_sdlc.py "add /health" --model builder=opus   # one lane
uv run adws/adw_models.py                                           # what this machine can run
```
