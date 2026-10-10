# HAIFA-REFINEMENT-T07: Harness for the task-parameter advice agent

## Problem

The "Navrhnout parametry tasku" block in the task form (`aifactory/web/src/components/backlog/TaskAdvice.vue`) offers only roster agents of the repo (`GET /api/backlog/task-advice/options` returns `rc.config.agents.agents`). A repo whose roster has one codex agent shows only codex. The user wants every harness (claude, codex, pi) and its models to choose from, plus an option that takes the default from the computer-wide harness settings (`$HAIFA_HOME/harnesses.json`, `aifactory.harness.settings`).

## Goal

1. The advice selector has two selects: harness and model.
2. Harness options: "Systémový default (<harness> · <model>)" (value `''`, first, preselected) followed by every harness that is enabled in machine settings and whose CLI is available.
3. Model options for a chosen harness: "Default harnessu (<model>)" (value `''`) followed by the catalog models of that harness. Hidden or disabled while harness is `''`.
4. The advice agent runs the repo's `plan` role agent (prompt engineering unchanged) with the roster overridden to the chosen harness/model, using the same override mechanism as a task run (`effective_override` + `apply_agents_override`).
5. Workflow advice (`WorkflowAdvice.vue`, `AdviceManager(task_parameters=False)`) keeps its current behavior.

Out of scope: the task's own `harness`/`model` parameter fields in `TaskForm.vue`, the run dialog, roster editing.

## Backend changes

### `aifactory/src/aifactory/web/workflow_advice.py`

1. Replace `AdviceManager.options(repo)` result with:

   ```python
   {
     "default": {"harness": str, "model": str} | None,
     "harnesses": [{"name": str, "default_model": str, "models": [str, ...]}, ...],
   }
   ```

   Build it from `aifactory.harness.settings.catalog(haifa_home())` (import `haifa_home` from `aifactory.home`):
   - `harnesses`: for each name in `HARNESSES` order where `catalog["settings"]["harnesses"][name]["enabled"]` and `catalog["available"][name]` are true. `default_model` is that harness's settings `model` (fall back to `_HARNESS_MODELS`-style preset is not needed, empty string is allowed). `models` is `catalog["models"][name]`.
   - `default`: the result of `_resolve(repo, {})` below reduced to `harness`/`model`, or `None` when it resolves to nothing.
   - The `repo` argument stays (signature used by `app.py`), it is used for the roster fallback in `_resolve`.

2. Add a private helper `_resolve(repo, explicit: dict[str, str]) -> dict[str, str]`:
   - `selection = effective_override({}, explicit)` from `aifactory.harness.settings`. Convert `ValueError` to `UsageError(str(exc))`.
   - If `selection` has no `harness` (no machine settings and nothing chosen): load `load_run_config(repo)`, take `rc.config.roles.roles.get("plan")`, find the roster agent with that name and set `selection = {"harness": canonical(agent.coding_agent), "model": agent.model}`. If the role or agent is missing, return `{}` (the runner reports the missing plan role as today).
   - Return `selection` (may contain `thinking` from machine settings).

3. `start()` for `task_parameters=True`:
   - Allowed body keys become `{"task_id", "draft", "harness", "model"}` (drop `"agent"`). Workflow advice keys are unchanged.
   - `harness` and `model` are optional strings. Reject non-strings with `UsageError`.
   - If `harness` is given it must be one of `options(repo)["harnesses"]` names, else `UsageError("choose an enabled harness")`. If `model` is given, `harness` must be given and `model` must be in that harness's `models`, else `UsageError("choose a model of the selected harness")`.
   - `ctx["advisor"] = _resolve(repo, {k: v for k, v in (("harness", harness), ("model", model)) if v})`. Remove `ctx["agent"]`. The advisor dict is part of the fingerprint, which is intended.

4. `_run()` `finally` block: replace the roster lookup for `provider` with `job.context.get("advisor", {}).get("harness")` passed through `canonical` when present.

### `aifactory/src/aifactory/workflow/adaptive.py` (`recommend`)

1. Replace
   ```python
   rc = apply_agents_override(rc, effective_override(ctx.get("effective", {}), None))
   ```
   with: if `task_parameters`, `rc = apply_agents_override(rc, ctx.get("advisor") or {})`, else keep the existing line.
2. Replace `agent = agents.resolve(cfg, ctx.get("agent", role.agent))` with `agent = agents.resolve(cfg, role.agent)`.
3. Nothing else changes. `ensure_enabled` and `check_harness` already run on the resolved agent.

`aifactory/src/aifactory/web/app.py` needs no change (routes pass the body through).

## Frontend changes

### `aifactory/web/src/components/backlog/TaskAdvice.vue`

1. Types:
   ```ts
   interface AdvisorHarness { name: string; default_model: string; models: string[] }
   interface AdvisorOptions { default: { harness: string; model: string } | null; harnesses: AdvisorHarness[] }
   ```
2. State: `options = ref<AdvisorOptions | null>(null)`, `harness = ref('')`, `model = ref('')`. Remove `choices`, `agent`.
3. `harnessOptions` computed: first `{ value: '', label: default ? `Systémový default (${default.harness} · ${default.model || 'model harnessu'})` : 'Systémový default' }`, then each harness `{ value: name, label: name }`.
4. `modelOptions` computed for the selected harness: `{ value: '', label: `Default harnessu (${default_model || 'nenastaven'})` }` then `models.map(m => ({ value: m, label: m }))`.
5. Watch `harness`: reset `model` to `''` when it changes by user action (do not reset during restore).
6. Persistence: key `haifa.task-advice.choice.<scope>`, JSON `{harness, model}`. On load, restore only if the harness is still in `options.harnesses` and the model is `''` or in its models, else `''`/`''`. Save on start. Wrap storage in try/catch as today.
7. `start()`: enabled when not busy/disabled and `canStart` (options loaded and either `default` is not null or `harness` is set). POST body `{ task_id?, draft, ...(harness ? { harness } : {}), ...(model ? { model } : {}) }`.
8. Template:
   - Replace the roster-empty note with: when loaded and `!options.default && !options.harnesses.length`, show `data-test="advice-no-agents"` text "Návrh potřebuje povolený harness. Nastav harnessy počítače v nastavení harnessů." (no link needed).
   - Otherwise two labels: "Harness pro návrh" with `SelectMenu v-model="harness" data-test="advice-harness"`, and "Model pro návrh" with `SelectMenu v-model="model" data-test="advice-model"`, rendered only when `harness` is set. Both disabled while busy.
   - Keep `scopeChanged` logic, resetting `options`, `harness`, `model`.

### `aifactory/web/src/components/backlog/TaskAdvice.test.ts`

Rewrite the option mocks to the new shape and cover:
1. Default is preselected and the POST body has no `harness`/`model`.
2. Choosing a harness shows its models with the "Default harnessu" first, choosing a model sends both in the body and stores `{harness, model}` under `haifa.task-advice.choice.haifa`.
3. A stored choice is restored when valid and dropped when the harness is no longer offered.
4. Changing the harness resets the model.
5. Empty options (`default: null, harnesses: []`) show `advice-no-agents` and disable start.

Update `TaskForm.test.ts` only if it mocks `/backlog/task-advice/options` with the old `agents` shape (grep for it).

## Backend tests: `aifactory/tests/web/test_web_task_advice.py`

1. `test_repeat_select_cost_and_save`: replace `agent` in the payload with `harness`/`model`. Write a machine settings file first so the test is deterministic: `aifactory.harness.settings.write(...)` would run model validation and harness tests, so instead write `$HAIFA_HOME/harnesses.json` directly with `HarnessSettings(...).model_dump_json()` (all three harnesses, claude enabled with `default_harness="claude"`), and monkeypatch `shutil.which` in `aifactory.harness.settings` (or `catalog`'s `found`) so availability does not depend on the machine. Assert:
   - `options["default"] == {"harness": "claude", "model": <configured>}` and `options["harnesses"]` lists the enabled+available harnesses.
   - `seen[0]["advisor"]["harness"]` equals the posted harness and `["model"]` the posted model.
   - Posting an unknown harness or a model not in the harness's list returns 400.
   - Posting `agent` returns 400.
2. Add a test: without `harnesses.json` and without harness choice, `ctx["advisor"]` falls back to the roster `plan` agent (`claude`/`sonnet` per `advice_fixture`).
3. `test_selected_agent_uses_proposal_schema_and_reports_usage`: replace `ctx.update(..., agent="builder", ...)` with `advisor={"harness": "claude", "model": "opus"}` (any model the claude harness accepts, check `harness/claude.py` `resolve_model`) and assert `seen[0].model` is that model, proving the override reaches the plan agent.

The `HAIFA_HOME` fixture in `tests/conftest.py` already isolates the settings file per test.

## Shipped frontend

Run `just web-build` so `aifactory/src/aifactory/web/static` matches the source.

## Verification

1. `just check` passes.
2. `just e2e` passes (no e2e test targets task advice today, it must not regress).
3. Manual: `just dash`, open a task form, the harness select lists claude, codex and pi (those enabled and installed), the default option shows the machine default harness and model, a proposal runs with each choice.

## Documentation

Write `app_docs/HAIFA-REFINEMENT-T07-harness-pro-agenta-ktery-pomaha-s-parame.md` (Czech, short): what the selector offers, that the default comes from the computer harness settings, the fallback to the roster `plan` agent, and the API shape of `/backlog/task-advice/options` and the `harness`/`model` body fields.
