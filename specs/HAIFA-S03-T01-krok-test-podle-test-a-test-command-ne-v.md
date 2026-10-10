# HAIFA-S03-T01 — Krok test podle `test` a `test_command`, ne vždy `just test`

## Problém

`aifactory/src/aifactory/engine/quality.py::test()` má natvrdo `argv=["just", "test"]`.
`EngineCodeRunner.test()` (workflow/interpreter.py) volá `engine_quality.run_tests(run)`, což
volá `test(run)`. Pole `test` z backlogu (je v `INHERITED_KEYS`, ale nikdo ho nečte) ani
`ProjectSettings.test_command` (config/settings.py, už se parsuje na `tuple[str, ...] | None`)
se nikdy nepoužijí.

## Pořadí rozlišení (cílové chování)

1. `test` tasku (`task.own["test"]`),
2. `test` z nejbližšího `index.md` nad ním (step, pak modul, …), přeskakují se úrovně bez
   klíče nebo s hodnotou `null`,
3. `test_command` z `.factory/config.yaml` (z base, `rc.config.settings`),
4. jinak `("just", "test")`.

Hodnota je buď řetězec (dělí se `shlex.split`), nebo seznam neprázdných řetězců. Prázdný
řetězec / prázdný seznam / seznam s neřetězcem nebo prázdným prvkem / jiný typ = neplatné.

## Změny

### 1. Sdílený parser příkazu — `aifactory/src/aifactory/config/settings.py`

Přidej veřejnou funkci (a exportuj ji z `aifactory/config/__init__.py`, pokud tam jsou
exporty):

```python
def split_command(value: object) -> tuple[str, ...]:
    """A command as argv: a string is split like a shell, a list must hold strings.

    Raises ValueError when the result is empty or has an empty or non-string part.
    """
    if isinstance(value, str):
        try:
            parts = tuple(shlex.split(value))
        except ValueError as exc:   # neuzavřená uvozovka
            raise ValueError(f"cannot split {value!r}: {exc}") from exc
    elif isinstance(value, (list, tuple)) and all(isinstance(p, str) for p in value):
        parts = tuple(value)
    else:
        raise ValueError("must be a string or a list of strings")
    if not parts or any(not p.strip() for p in parts):
        raise ValueError("must be a non-empty list of non-empty strings")
    return parts
```

Validátory `test_command` v `ProjectSettings` nech chovat stejně (zprávy, které testují
`tests/config`, neměň); případně `_split_command` může dál dělat jen `shlex.split` pro
řetězec. Nepřepisuj je, pokud by se změnily chybové zprávy — stačí, že `split_command` má
stejná pravidla. (Spusť `just test` → `tests/config` a `tests/web/test_web_settings.py`.)

### 2. Validace v loaderu — `aifactory/src/aifactory/backlog/loader.py`

`factory backlog check` hlásí `backlog.issues` z loaderu, takže kontrola patří sem (stejný
vzor jako `writes`/`auto_continue`):

- V `load_container`: pro `key == "test"` a `value is not None` zavolej `split_command(value)`;
  při `ValueError` přidej issue `invalid_field` se zprávou
  `f"field 'test' must be a command string or a list of strings: {exc}"` (cesta `index`,
  id `container.id`). **Hodnotu NEZAHAZUJ** — dál ji ulož do `container.defaults["test"]`
  (aby běh tasku, který ji dědí, skončil chybou, místo aby tiše spadl na rodiče /
  `test_command`).
- V `load_task`: totéž pro `own.get("test")` (issue na `path`, id `task_id`); hodnotu v `own`
  ponech.
- Pomocná funkce `_test_issue(value) -> str | None` sdílená oběma místy, ať se kód neopakuje.

### 3. Rozlišení příkazu — `aifactory/src/aifactory/backlog/derived.py` + `run/task.py`

V `derived.py` přidej:

```python
def effective_test(task: Task) -> object:
    """The nearest `test`: the task's own, then index.md upwards; None when nobody sets it."""
    for values in (task.own, *(c.defaults for c in ancestors(task))):
        value = values.get("test")
        if value is not None:
            return value
    return None
```

(Exportuj z `aifactory/backlog/__init__.py` vedle `effective_workflow`.)

V `run/task.py`:

```python
DEFAULT_TEST_COMMAND: tuple[str, ...] = ("just", "test")

def test_command(task: Task, settings: ProjectSettings) -> tuple[str, ...]:
    """argv of the test step: task `test`, nearest index.md `test`, `test_command`, `just test`."""
    value = effective_test(task)
    if value is not None:
        try:
            return split_command(value)
        except ValueError as exc:
            raise TaskRunError("invalid_test", f"task {task.id}: test {value!r} {exc}") from exc
    if settings.test_command is not None:
        return tuple(settings.test_command)
    return DEFAULT_TEST_COMMAND
```

(Pozor na pytest: funkce s prefixem `test_` v modulu `src` nevadí, ale v testech ji importuj
jako `from aifactory.run.task import test_command as resolve_test_command`, ať ji pytest
nesbírá. Alternativně ji pojmenuj `resolve_test_command` — doporučeno, vyhne se to riziku.)

V `run_task`, uvnitř bloku s `base_copy` po kontrole `no_writes` a před výběrem workflow
(tj. před `store.claim`, nic se ještě nevytvořilo): `test_argv = resolve_test_command(task,
settings)`. Platí i pro `resolve_onto` (workflow `resolve` má krok test). Přidej pole
`test_argv: tuple[str, ...]` do `_Job` a v `_execute` předej `run_workflow(...,
test_command=job.test_argv)`.

### 4. Interpreter — `aifactory/src/aifactory/workflow/interpreter.py`

- `run_workflow` dostane kwarg `test_command: Sequence[str] | None = None`; po
  `run.prompt_variables = ...` nastav `run.test_argv = list(test_command) if test_command
  else None`. Docstring: „``test_command`` (argv of every ``test`` step; default
  ``just test``)“.
- `CodeRunner` protokol a `EngineCodeRunner.test` beze změny podpisu — příkaz jede přes
  `run`, takže všechny kroky s akcí `test` (`test`, `retest` v simple-sdlc, test v `resolve`)
  ho dostanou automaticky.
- Aktualizuj modul docstring jednou větou (odkud `test` bere příkaz).

### 5. Engine — `aifactory/src/aifactory/engine/quality.py`

V `test(run)`:

```python
        # aifactory 2.9: a task run sets run.test_argv (task `test`, index.md, test_command);
        # without it the step keeps the old default.
        argv=list(getattr(run, "test_argv", None) or ["just", "test"]),
```

Značka `# aifactory` je povinná u každé změny logiky v `engine/`. Událost `quality:test`
už v `payload["command"]` nese `shlex.join(spec.argv)`, takže po této změně nese skutečně
spuštěný příkaz — nic dalšího netřeba. Banner nahoře můžeš doplnit o řádek (s `# aifactory`
netřeba, je to docstring), ale není to nutné.

### 6. Chybový kód — `aifactory/src/aifactory/skill/codes.py`

Do sekce „Runs“ přidej `("invalid_test", "2", "the task's test command (own or inherited) is
not a string or a list of strings")`. `tests/test_skill.py::test_skill_lists_error_codes`
vyžaduje, aby každý kód byl ve skillu — generuje se z `ERROR_CODES`, ověř.

### 7. Skill — `aifactory/src/aifactory/skill/skill.md`

- V „Task header“ přidej odrážku za `workflow`:
  „- `test` is the command of the workflow's `test` steps (own or inherited): a string split
  like a shell (`"uv run pytest -q"`) or a list of strings (`[uv, run, pytest]`). An invalid
  value is reported by `factory backlog check` and stops `factory task run` with
  `invalid_test`.“
- V „Workflow format“ u code steps: „A `test` step (also with another `id`, e.g. `retest`)
  runs the task's `test`, else the nearest `index.md` `test` (step, then module), else
  `test_command` from `.factory/config.yaml`, else `just test`; the step passes when the
  command exits 0. The trace event `quality:test` records the command that ran.“

## Testy (žádný model, žádný `FakeCodeRunner` v nových testech chování příkazu)

Příkazy v testech: `sys.executable -c "..."` (exit 0 / `raise SystemExit(3)`), různé
značky v kódu (např. `print('task')`, `print('index')`, `print('config')`), aby šly rozlišit
podle `command` v trace. Pro řetězcovou formu použij `shlex.join([sys.executable, "-c", ...])`
a v YAML ho dej do uvozovek (nebo `json.dumps`), pro seznamovou formu YAML flow list s
`json.dumps(list)`.

### `aifactory/tests/backlog/` — nový soubor `test_backlog_test_field.py`

- `split_command`: řetězec se dělí jako shell (`"uv run 'a b'"` → `("uv","run","a b")`),
  seznam projde, `""`, `[]`, `[""]`, `[1]`, `5`, `"a 'b"` → `ValueError`.
- `load_backlog` + `factory backlog check --json` (viz `test_backlog_check.py` pro vzor
  fixture/CLI): `test: 5` v tasku i `test: []` v `index.md` → issue `invalid_field`
  zmiňující `test`, `ok` je false. Platný řetězec i seznam → žádný issue.
- `effective_test`: task přebije step, step přebije modul, `null` se přeskočí.

### `aifactory/tests/run/` — nový soubor `test_task_test_command.py`

Na `make_run_repo` + `fake_env` (viz `test_task_run.py`). Do repa přidej workflow
`.factory/workflows/plan-test.yaml`:
```yaml
name: plan-test
description: Plan the task, then run the suite
steps: [plan, test]
accept: test.passed
```
a nastav `workflow: plan-test` (v `M01-core/index.md` nebo na tasku), commitni
(`commit_all`). `run_task(repo, T01)` volej **bez** `code=` → jede `EngineCodeRunner`, tedy
skutečný podproces. `script.add("planner", ok())` pro planner.

Helper `test_commands(repo, run_id) -> list[str]`: z `.factory/trace.db` (sqlite3)
`SELECT payload_json FROM events WHERE adw_id=? AND name='quality:test'` → `json.loads(...)
["command"]`. (Tracer zapisuje během běhu; po návratu `run_task` jsou data v DB — pokud ne,
podívej se, jak ostatní testy čtou trace, např. `test_parallel_runs.py`.)

Případy (každý jako samostatný test nebo parametrizace):
1. task `test` (řetězec) + step `index.md` `test` + config `test_command` → běží příkaz
   tasku; `result.ok`, command == `shlex.join(task_argv)`.
2. bez task `test`, step `index.md` `test` (seznam) + config `test_command` → běží
   příkaz z `index.md`.
3. jen config `test_command` → běží `test_command`.
4. nic nenastaveno → command == `"just test"` (neověřuj úspěch; `just` v temp repu bez
   receptu / bez binárky selže, stačí command a že krok proběhl).
5. nenulový návratový kód (`raise SystemExit(3)`) → `result.run.state == "failed"`,
   `result.run.error == "accept not met"` (ověř přesnou hodnotu podle `_execute`),
   envelope `test` má `passed is False`.
6. neplatný `test` na tasku (`test: 5`) → `TaskRunError` s `code == "invalid_test"`,
   `assert_nothing_created`-style kontrola (žádný worktree, žádná větev `factory/`),
   `script.calls == []`.
7. (volitelně) workflow `simple-sdlc`-like se `retest`: stačí jednoduchý vlastní workflow
   `steps: [plan, test, {test: {id: retest}}]`, ověř dva `quality:test` se stejným
   příkazem.

Pozor: config se čte z base, takže změny `.factory/config.yaml` i backlogu commitni před
během. `ProjectSettings` je `extra="forbid"` — `test_command` je platný klíč.

### `aifactory/tests/workflow/` — rozšíř/nový `test_workflow_test_command.py`

S `workflow_env` fixture (viz `test_workflow_command.py`) a `run_workflow(workflow(text),
"do it", workflow_env.cfg)` **bez** `code` (EngineCodeRunner):
- `test_command=[sys.executable, "-c", "raise SystemExit(0)"]` → `results["test"]["passed"]
  is True`, `accepted`.
- `test_command=[..., "raise SystemExit(3)"]` → `passed is False`, `accepted is False`.
- Bez `test_command` přímo zavolej `engine_quality.test(run)` ve fázi (jako `_command`
  helper) s `run` bez `test_argv` a ověř `check.command == "just test"` (výchozí zůstává).

Ověř, že stávající testy s `FakeCodeRunner` dál procházejí (podpis `CodeRunner` se nemění).

## Ověření

```
just test
just typecheck
just lint
```
Vše musí projít (exit 0). `ruff format --check` — formátuj nové soubory (`cd aifactory && uv
run ruff format .` lokálně, pokud je potřeba).

## Neměnit

`vendor/`, `prototype/`, dashboard nastavení (`web/`), `workdir`, samostatné kroky
lint/typecheck. Dokumentační soubor `app_docs/HAIFA-S03-T01-...md` píše documenter, ne
builder.
