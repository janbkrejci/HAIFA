# HAIFA-S03-T10: Task bez workflow se nespustí — plán

## Cíl
Task, jehož efektivní `workflow` chybí nebo je `null` (na kterékoli úrovni: projekt, step, task — nejbližší úroveň vyhrává, i když vyšší úroveň workflow má), se nesmí spustit:
- `factory task run` (i s `--force`, `--auto`) skončí chybou `no_workflow` (exit 2) a nic nezaloží (worktree, větev, řádek v `task_runs`).
- Auto-continue takový task přeskočí s důvodem `no_workflow` / detail „bez workflow“ a pokračuje dalším.
- API `POST /api/backlog/tasks/{id}/run` vrátí stejnou chybu (HTTP 422, `error.code == "no_workflow"`).
- Dashboard: tlačítko Spustit v detailu tasku je zakázané a má tooltip s důvodem.

Out of scope: přejmenování stavu „K přípravě“ (HAIFA-S01-T24). `vendor/`, `prototype/` neměnit. Testy bez modelu a sítě.

## Současný stav (zjištěno)
- `backlog/derived.py::effective()` už skládá hodnoty shora dolů přes `dict.update`, takže `workflow: null` na nižší úrovni přepíše vyšší (loader `null` hodnoty v `container.defaults` i `task.own` zachovává). `effective_workflow(task)` tedy vrací `None`. Chybí jen test a pojmenovaný helper.
- `run/task.py::resolve_workflow` už hází `TaskRunError("no_workflow", ...)`, ALE až po kontrole `depends_on` (`unmet_dependencies`) a `no_writes`. Kód `no_workflow` je už registrovaný v `skill/codes.py` (exit "2") a v `web/app.py` mapovaný na 422.
- `run/queue.py::select_next` workflow nekontroluje → task bez workflow je vybrán, `run_task` selže → dnes skončí jako `cannot_start` skip (nebo, pokud by se chyba projevila až v běhu, řetěz zastaví).
- Dashboard `web/src/components/backlog/TaskDetail.vue` — tlačítko `data-test="run"` (ř. ~116–126) je zakázané jen při `busy || run?.busy || run?.open`. `task.workflow` je efektivní workflow (`null` = bez workflow), viz `backlog/render.py` ř. 86.

## Změny

### 1. `aifactory/src/aifactory/backlog/derived.py`
Přidat helper hned pod `effective_workflow`:
```python
def has_workflow(task: Task) -> bool:
    """False when the effective ``workflow`` is unset or ``null`` (the nearest level wins)."""
    return effective_workflow(task) is not None
```
Pokud `backlog/__init__.py` re-exportuje `effective_workflow`, přidat i `has_workflow` (a do `__all__`, pokud existuje).

### 2. `aifactory/src/aifactory/run/task.py`
- Přidat funkci:
```python
def no_workflow_error(task: Task) -> TaskRunError:
    return TaskRunError(
        "no_workflow", f"task {task.id} has no workflow, set `workflow:` on it or a container"
    )
```
  a použít ji v `resolve_workflow` (místo inline konstrukce).
- V `run_task` přesunout kontrolu dopředu: hned po `busy`/`already_running` kontrole (a PŘED `if not force: _unmet_error(...)` a `no_writes`) vložit
```python
if resolve_onto is None and not has_workflow(task):
    raise no_workflow_error(task)
```
  Tím `--force` kontrolu neobejde a chyba je `no_workflow` i u tasku s nesplněnými závislostmi / bez writes. Vše je stále před `store.claim`, `gitops.next_branch` a vytvořením worktree → nic se nezaloží. Docstring `run_task` doplnit: „``force`` … never overrides a running task, a task without ``writes`` or a task without a workflow.“
- `resolve_workflow` ponechat se stávající kontrolou (obrana do hloubky).

### 3. `aifactory/src/aifactory/run/queue.py`
- `SKIP_REASONS` rozšířit o `"no_workflow"` (např. `("no_workflow", "waits_on_pr", "blocked", "in_review", "running", "cannot_start")`).
- Konstanta `NO_WORKFLOW_DETAIL = "bez workflow"`.
- V `select_next` v cyklu hned po `exclude` kontrole:
```python
if not has_workflow(task):
    skipped.append(Skip(task.id, "no_workflow", NO_WORKFLOW_DETAIL))
    continue
```
- Docstring modulu doplnit větu: task bez workflow (efektivní `workflow` chybí nebo je `null`) se přeskočí jako `no_workflow` a řetěz jde dál.
- Pozn.: ve výsledku řetězu se přeskočené hlásí v `ChainResult.waiting` (při `STOP_EXHAUSTED` z posledního `select_next`); task bez workflow tam bude, protože zůstává `todo` a není v `exclude`. Textový výstup CLI už formátuje `waiting: <id> <reason>: <detail>` → `waiting: X no_workflow: bez workflow`. Nic dalšího v CLI netřeba měnit — ověřit grepem, že v CLI ani skill dokumentaci není tvrdý seznam skip důvodů (pokud je, doplnit `no_workflow`).

### 4. CLI `task run`
Žádná změna logiky nutná (run_chain → první `run_task` vyhodí `TaskRunError`, CLI ji převede na envelope s exit 2). Jen ověřit testem.

### 5. API
`web/launcher.py` spouští `factory task run` jako proces a chybu z envelope propaguje; `web/app.py` mapuje `no_workflow` → 422. Žádná změna kódu nutná; pokrýt testy (viz níže).

### 6. Dashboard — `aifactory/web/src/components/backlog/TaskDetail.vue`
- `const noWorkflow = computed(() => !props.detail.task.workflow)` (nebo přes existující `task` computed).
- Konstanta textu: `const NO_WORKFLOW_HINT = 'Task nemá workflow – nastav ho na tasku, stepu nebo projektu.'`
- Tlačítko `data-test="run"`:
  - `:disabled="busy || run?.busy || run?.open || noWorkflow"`
  - `:title="noWorkflow ? NO_WORKFLOW_HINT : undefined"`
- (Pozor: existující test na ř. ~54–56 v `TaskDetail.test.ts` kontroluje, že bez důvodu neexistuje žádný `[title]` — s výchozí fixture `workflow: 'plan-build'` zůstane splněn, title musí být `undefined`, ne prázdný string.)
- Pokud `RunDialog.vue` jde otevřít i jinou cestou než tímto tlačítkem (zkontrolovat `views/BacklogView.vue`, handler `open-run`), v handleru zabránit otevření pro task bez workflow. Jinak RunDialog neměnit.

## Testy

### Python — `aifactory/tests/run/test_task_run.py`
- Do parametrizace `test_checks_before_start` přidat případy (využít existující setup mechanismus, `write` + `commit_all`, modul M01 má `workflow: plan-commit` v `backlog/M01-core/index.md`):
  - `("M01-S01-T04", "task_workflow_null", "no_workflow")` — task s `workflow: null` v frontmatteru (projekt má `plan-commit`).
  - `("M01-S02-T01", "step_workflow_null", "no_workflow")` — `backlog/M01-core/S02-api/index.md` s `workflow: null` a `writes: [src/api/]`, task bez vlastního workflow.
  - Test asserts `assert_nothing_created(repo)` a `script.calls == []` už obsahuje.
- Nový test `test_no_workflow_even_with_force`: task bez workflow, který má i nesplněné `depends_on` a/nebo žádné writes → `run_task(repo, id, force=True)` hází `no_workflow`, `assert_nothing_created`.
- Nový test pro projekt-level null: `backlog/M01-core/index.md` přepsat na `workflow: null`, ale step `S01-model/index.md` nastaví `workflow: plan-commit` → task běží (nejbližší vyhrává) — a obráceně task `workflow: null` přebije. (Může být spíš unit test v backlog testech, viz níže.)

### Python — `aifactory/tests/backlog/` (např. nový `test_backlog_workflow_null.py` nebo do `test_backlog_load.py`)
Unit test `effective_workflow` / `has_workflow` nad malým backlogem (použít helpery z `backlog_repo.py`): kombinace
- projekt `wf-a`, step bez klíče, task bez klíče → `wf-a`, `has_workflow` True;
- projekt `wf-a`, step `null` → `None`, False;
- projekt `wf-a`, step `wf-b`, task `null` → `None`, False;
- projekt `null`, step `wf-b` → `wf-b`, True;
- nikde nic → `None`, False.

### Python — `aifactory/tests/run/test_auto_continue.py`
- `test_select_next_rules`: přidat task (např. `M01-S01-T06` s `workflow: null` — upravit `_task` helper o volitelný `extra` frontmatter, nebo napsat soubor přes `write`) zařazený před `M01-S01-T09`; očekávat `("M01-S01-T06", "no_workflow")` ve `skipped` s `detail == "bez workflow"` a `next` stále `M01-S01-T09`.
- Nový test řetězu `test_task_without_workflow_is_skipped`: `setup_chain(repo)` + step S02 (nebo T02) s `workflow: null`, `run_chain(repo, T01, auto=True)` → běhy pokračují dalším taskem (task bez workflow mezi nimi chybí), `chain.stop == STOP_EXHAUSTED`, `(id, "no_workflow")` v `chain.waiting`, žádný `TaskRunRow` pro task bez workflow (`runs_of(...) == []`). Podívat se na `setup_chain` parametry (`s02_writes`, `t02_depends`) a případně přidat parametr `s02_extra`/`t02_workflow_null`.
- CLI test: `main(["task", "run", <no-wf-id>, "--repo", str(repo), "--auto", "--force", "--json"])` → exit code 2, `env["error"]["code"] == "no_workflow"`, žádné běhy/větve (`runs_of == []`, `git branch --list 'factory/*'` prázdné). Případně do `test_task_run.py`, pokud je tam CLI helper.
- Textový CLI test (volitelný): `waiting: <id> no_workflow: bez workflow` ve výstupu.

### Python — API
- `tests/web/test_web_launcher.py::test_run_errors_before_claim`: přidat parametr `("no_workflow", 422)`.
- `tests/web/test_web_task_run.py`: nový test s reálným workerem — commitnout task s `workflow: null` (vzor `write` + `git add/commit` jako jinde v souboru / `commit_all` z `run_repo`), `_run(client, id, {}, 422)` i `_run(client, id, {"force": True}, 422)` → `error.code == "no_workflow"`, `wait(app)`, `runs_of(repo, id) == []`, `worker.calls() == []`.

### Vitest — `aifactory/web/src/components/backlog/TaskDetail.test.ts`
- Nový test: `taskDetail()` fixture s `task.workflow: null` (podívat se na tvar `taskDetail` v `web/src/test/backlogFixtures.ts`, jak předat override vnořeného `task`) → `[data-test="run"]` má atribut `disabled` a `title` obsahuje „nemá workflow“; klik neemituje `open-run`.
- Existující test s workflow: tlačítko není disabled a nemá `title`.

## Ověření
- `just test` (pytest + web-test/vitest), `just typecheck`, `just lint` musí projít (exit 0). Pokud `ruff format --check` selže, spustit `cd aifactory && uv run ruff format .` na změněné soubory.
- Pokud web má vlastní typecheck (`vue-tsc`, viz `aifactory/web/package.json`), spustit i ten.

## Dokumentace
`app_docs/HAIFA-S03-T10-task-bez-workflow-se-nespusti.md`: krátce popsat chování (`no_workflow` v CLI/API, skip `no_workflow` v auto-continue, disabled tlačítko, sémantika `workflow: null`).
