# HAIFA-REFINEMENT-T70 — Proposer inherits the requested context

## Outcome and scope

For an explicitly requested project or step, the proposer uses that container's inherited harness, model and thinking, completed with computer settings through T69. Automatic placement uses the computer defaults, even when the proposal eventually selects an existing container with other settings. Gate corrections and human refinement continue with the original selection and session. The intent job exposes the actual resolved selection as `agent: {harness, model, thinking}`.

Implement only in the allowed Python files and task documentation listed below. The CLI already calls `workflow.propose.propose()` → `run_proposer()`; no CLI or frontend source changes are needed. Do not change other agents, T69 helpers, engine session behavior, or configuration files. The task note describes the operator's run binding; it is not a requirement to hardcode Codex or medium thinking in the implementation.

## Existing behavior and reusable pieces

- `workflow/propose.py:context()` validates the target against `core.load_for_edit(repo)`. `run_proposer()` currently loads `RunConfig`, prepares engine config, then resolves the roster proposer without context overrides.
- `backlog.derived.harness_values(node)` from T69 handles container ancestry and removes an inherited model when a descendant changes harness. Use it rather than `focus.defaults` or a manual merge.
- `harness.settings.context_binding(values)` completes object settings from computer configuration; `{}` means repo scope. With no configured computer default it deliberately returns `{}`, preserving roster fallback. Preserve that behavior.
- `run.task.apply_agents_override(rc, binding)` takes a **RunConfig**, not the prepared engine config. Apply it before `prepare_cfg()` and `agents.resolve()`.
- `ensure_enabled()` and `check_harness()` must inspect the final resolved proposer. The engine reuses a stored session only for the same coding agent; `job_id`, runtime directory and isolated clone must stay stable across refinement.
- `web/intent.py:IntentManager._run()` calls a typed `Runner` and receives a three-item tuple. Keep that return shape and the existing proposal serialization contract.

## Implementation

### 1. Context selection and session binding — `aifactory/src/aifactory/workflow/propose.py`

1. After existing target validation, load the requested container from the editable backlog using `target.step or target.project`. For explicit targets, pass `harness_values(container)` to `context_binding`; for auto placement pass `{}`. Do not use the agent's eventual `resolve(proposal, target)` placement to choose its harness. Keep all original target validation and error codes.
2. Apply the resulting binding to `rc` with `apply_agents_override`, then call `prepare_cfg` and resolve `PROPOSER_AGENT` as today. Preserve missing-agent handling, read-only writes, validation, isolation, tracing and proposal gates.
3. Normalize selection failures into `TaskEditError` so CLI JSON and web jobs receive meaningful errors. Convert `ValueError` from binding/enable checks to `agent_unavailable`; convert `TaskRunError` from the override helper to `TaskEditError` using its code/message and applicable error details. Neither CLI's current catch list nor `_error_text` directly handles these new low-level exceptions. Do not fall back to the roster when an explicitly selected harness is disabled, unavailable or invalid.
4. Freeze the actual resolved trio for the session. Store a small JSON object in the existing ignored runtime directory, e.g. `.factory/data/backlog-propose/<job_id>/agent.json`, containing canonical `harness`, resolved `model` and `thinking`. On a refinement with that snapshot, apply the saved trio instead of recomputing selection from changed container/computer settings. On a first turn compute fresh selection; do not let an old snapshot affect an unrelated first call. A refinement without a snapshot can compute and store the selection for compatibility. Continue to validate enablement and availability on every turn; a disabled original harness fails rather than switching sessions.
5. Add an optional keyword callback `on_agent: Callable[[dict[str, str]], None] | None = None` to `run_proposer`. Once the final agent passes selection checks, emit a fresh dictionary containing the resolved trio before the agent call. Use the same object values for the session snapshot and callback. This exposes actual roster fallback values too and avoids predicting selection separately in the web layer. Keep the public `propose()` CLI wrapper and three-item return unchanged.
6. Gate correction remains inside the existing `Run.phase` and therefore automatically keeps the selected agent. Preserve runtime path, `job_id`, `workdir`, and session map behavior for human refinement.

The JSON snapshot is runtime state written only during actual proposer jobs, never a tracked repository artifact. No new source module or persistence service is needed.

### 2. Job metadata — `aifactory/src/aifactory/web/intent.py`

- Add nullable `agent: dict[str, str] | None` to `IntentJob` and include it in `json()`. It is null while queued before selection, then contains `harness`, `model` and `thinking` throughout running, ready, refined and applied states.
- Extend the `Runner` protocol with the optional `on_agent` keyword. In `_run`, provide a callback that copies the selection to `job.agent` under `self.lock`. Do not hold the lock during agent execution.
- Keep metadata when starting refinement and after a failed refinement. A selection failure before any agent is selected may leave it null. Preserve all current lifecycle, proposal and cleanup behavior.
- Use the callback as the single source of actual selection; do not resolve the agent again from web code or scrape progress text. POST may return null before the worker runs; subsequent GET exposes the selected agent.

### 3. Fake harness support — `aifactory/tests/intent_fixture.py`

Extend `install_fake` with an optional harness argument defaulting to `claude`, and patch that interface's `run`. Preserve its answers and returned request-list behavior so existing API/browser callers continue unchanged. New tests can wrap the selected fake to record which interface ran. The workflow file's local `fake` fixture can receive equivalent support locally. Stub harness availability and any model capability discovery to keep every test offline; do not patch selection or override helpers under test.

### 4. Workflow/CLI regressions — `aifactory/tests/workflow/test_backlog_propose.py`

Use isolated computer settings under the existing test `HAIFA_HOME` and fixture repositories. Modify fixture backlog index front matter with valid stored settings, committing fixture changes when the isolated clone needs them. Use valid models such as `gpt-6.1-sol` and distinguish thinking values from roster defaults.

Cover these observable cases:

- Parameterize project and step targets with Codex/model/thinking. Invoke the actual CLI `main(['backlog', 'propose', ... '--json'])`; assert successful output and that the Codex fake receives the expected model and thinking while Claude is not invoked. Capture `check_harness` calls to verify it checks Codex.
- Step inheritance from its project, including a lower container changing harness: rely on T69 to avoid carrying the ancestor's incompatible model. Assert the request's final values.
- Auto placement with computer defaults different from the proposed destination: proposer uses the computer trio, including on CLI invocation. The destination must not override it after the answer arrives.
- Unconfigured computer/default-null fallback preserves roster selection and real roster model/thinking.
- A gate correction uses the same interface, values and session ID across its requests.
- Call `run_proposer` initially and with `Refinement` using the same `job_id` and `workdir`. Change computer or target binding between turns; assert the original interface/model/thinking, session ID and cwd remain the same.
- Disabled selected harness and unavailable final harness produce structured failure without invoking either real interface. Include a binding/override failure assertion to guard error translation.

Keep preview/apply/read-only tests intact; no real model calls or writes to operator settings.

### 5. API regressions — `aifactory/tests/web/test_web_intent.py`

- For explicit project and step targets, run through the API with a Codex fake and verify GET after completion exposes `agent == {harness: codex, model: <used model>, thinking: <used thinking>}`. Compare model/thinking with the recorded request and assert the actual Codex interface ran.
- Verify auto placement reports the computer trio even if its eventual destination has different settings; verify roster fallback reports actual values rather than an empty binding.
- Extend a refinement/session scenario to assert metadata is retained, requests keep the same session/cwd, and changing computer settings between rounds does not switch harness/model/thinking.
- Ensure metadata is visible while the fake harness is blocked in a controlled running job (use a threading event with bounded waits and guaranteed release). This verifies the callback is delivered before completion, not just on the ready result.
- Preserve existing response fields, validation, proposal editing, apply and cleanup assertions. A queued POST may legitimately have `agent: null`.

### 6. Task documentation

Write the completed behavior and verification evidence in `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T70-novy-zamer-proposer-bezi-s-harnessem-mod.md`. Explain target inheritance, auto/computer behavior, roster fallback, frozen refinement selection, and the `agent` JSON field. No frontend changes or promises of frontend rendering.

## Verification and acceptance

Run from the repository root:

1. `just lint` and `just typecheck` (always required).
2. `just pytest tests/workflow/test_backlog_propose.py tests/web/test_web_intent.py` for the changed behavior and existing direct caller coverage.
3. If the shared intent fixture changes, run its existing browser caller: `just pytest tests/e2e/test_intent_browser.py -n0`. The screen itself is unchanged; do not add browser cases or change browser source files.

Use bounded command timeouts with margin (targeted Python files up to several minutes; the browser file up to 5 minutes). Do not run the entire suite or frontend build/tests, because no frontend source changes. Inspect diffs to confirm changes stay inside allowed paths and no runtime state is tracked. Report exact checks and outcomes. Planning itself requires no tests: this phase writes only this specification and the identical external handoff copy.

Acceptance is demonstrated by actual fake interface calls for project, step, auto and refinement, plus job metadata matching those calls. Both CLI and dashboard go through the same binding implementation; all existing proposal validation and session tests remain green.
