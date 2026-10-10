# HAIFA-S06-T01: Časový limit kroku test (`test_timeout`)

## Cíl

Krok `test` má dnes pevný limit 600 s (`engine/quality.py::test`). Zavádíme klíč
`test_timeout` (celé sekundy > 0), který jde nastavit:

1. v tasku (front matter),
2. v `index.md` (dědí se stejně jako `test`: nejbližší úroveň nahoře vyhrává, `null` se přeskakuje),
3. v `.factory/config.yaml` (`ProjectSettings.test_timeout`),
4. jinak výchozích 600 s.

Každý krok s akcí `test` (i `retest`, i test ve workflow `resolve`) použije limit podle
tohoto pořadí; trace událost `quality:test` nese limit. Zároveň opravit pád
`TypeError: can't concat str to bytes` při `TimeoutExpired`.

Vzor: commit `9031611` (implementace `test` / `test_command`). Postup je zrcadlový —
kde se řeší `test_argv`, přidej vedle `test_timeout`.

## Změny po souborech (vše relativně k `aifactory/`)

### 1. `src/aifactory/config/settings.py`
- Do `ProjectSettings` přidat hned za `test_command`:
  `test_timeout: int | None = Field(default=None, gt=0, strict=True)`
  (`Field` je už importovaný – ověř; `strict=True` odmítne `True`, `"600"`, `1.5`).
  `parse_project_settings`/`load_config` pak neplatnou hodnotu ohlásí jako `ConfigIssue`
  samy (pydantic) – ověř testem, že `load_config` vyhodí `ConfigError` s `test_timeout` ve zprávě.
- Přidat veřejnou pomocnou funkci (a exportovat ji v `config/__init__.py` vedle `split_command`):
  ```python
  def check_timeout(value: object) -> int:
      """A time limit in whole seconds: an int > 0 (not a bool). Raises ValueError otherwise."""
      if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
          raise ValueError("must be a whole number of seconds greater than 0")
      return value
  ```
  (Používá ji loader backlogu i `resolve_test_timeout`.)

### 2. `src/aifactory/backlog/model.py`
- `INHERITED_KEYS`: přidat `"test_timeout"` (za `"test"`). `FIELD_ORDER` v `taskfile.py`
  NEMĚNIT (`test` v něm také není).

### 3. `src/aifactory/backlog/derived.py` (+ export v `backlog/__init__.py`)
- Zobecnit `effective_test` na interní `_nearest(task, key)` a přidat
  `effective_test_timeout(task) -> object` (vlastní hodnota tasku, pak `index.md` nahoru;
  `None`/chybějící se přeskakuje; `None` když nikde). `effective_test` zachovat beze změny chování.
  Exportovat `effective_test_timeout` v `__all__` balíčku `aifactory.backlog`.

### 4. `src/aifactory/backlog/loader.py`
- Přidat `_timeout_issue(value) -> str | None`: `None` pro `None`, jinak `check_timeout`;
  při `ValueError` vrátí
  `f"field 'test_timeout' must be a whole number of seconds greater than 0, got {value!r}"`.
- V `load_container` (smyčka přes klíče `index.md`) hned vedle kontroly `test`:
  `if key == "test_timeout" and (problem := _timeout_issue(value)) is not None: self.issue("invalid_field", problem, index, container.id)`
  – hodnotu PONECHAT v `defaults` (stejně jako u `test`: zděděná neplatná hodnota musí run shodit, ne tiše spadnout na 600).
- V `load_task` vedle kontroly `test` totéž pro `own.get("test_timeout")` (hodnotu ponechat v `own`).
- `validate.py`: kontroly polí jsou v loaderu (stejně jako u `test`), `validate.py` neměň,
  pokud k tomu nenajdeš důvod. `factory backlog check` hlásí issue z loaderu automaticky.

### 5. `src/aifactory/run/task.py`
- Vedle `DEFAULT_TEST_COMMAND`: `DEFAULT_TEST_TIMEOUT = 600`.
- Nová funkce vedle `resolve_test_command`:
  ```python
  def resolve_test_timeout(task: Task, settings: ProjectSettings) -> int:
      """Time limit (s) of every ``test`` step: task, nearest index.md, test_timeout in config.yaml, else 600."""
      value = effective_test_timeout(task)
      if value is not None:
          try:
              return check_timeout(value)
          except ValueError as exc:
              raise TaskRunError("invalid_test_timeout", f"task {task.id}: test_timeout {value!r} {exc}") from exc
      if settings.test_timeout is not None:
          return settings.test_timeout
      return DEFAULT_TEST_TIMEOUT
  ```
- V `run_task` hned za `test_argv = resolve_test_command(task, settings)` volat
  `test_timeout = resolve_test_timeout(task, settings)` (tj. před vytvořením worktree, větve
  a claimem → chyba „před startem“; platí i pro `resolve_onto`).
- `_Job`: nové pole `test_timeout: int = DEFAULT_TEST_TIMEOUT`; předat do `_Job(...)`.
- V `_execute` předat `run_workflow(..., test_timeout=job.test_timeout)`.

### 6. `src/aifactory/skill/codes.py`
- Přidat kód `("invalid_test_timeout", "2", "the task's test_timeout (own or inherited) is not a whole number of seconds greater than 0")` hned za `invalid_test`.

### 7. `src/aifactory/workflow/interpreter.py`
- `run_workflow(..., test_timeout: int | None = None)`; v docstringu doplnit
  „``test_timeout`` (time limit in seconds of every ``test`` step; default 600)“.
- `run.test_timeout = test_timeout` hned za `run.test_argv = ...`.
- Modulový docstring: doplnit větu, že `test` step má limit `run.test_timeout`, jinak 600 s.

### 8. `src/aifactory/engine/runner.py` (engine → značka `# aifactory`)
- V `Run.__init__` vedle `self.test_argv`:
  ```python
  # aifactory: time limit (s) of every `test` step (quality.test); a task run sets it
  # from the task's `test_timeout`, index.md or config.yaml. None means 600 s.
  self.test_timeout: int | None = None
  ```

### 9. `src/aifactory/engine/quality.py` (každá změna logiky se značkou `# aifactory`)
- Konstanta `DEFAULT_TEST_TIMEOUT = 600  # aifactory: default time limit of the test step`
  (z ní bude onboarding sssf číst; `run/task.py` může importovat odsud místo vlastní
  konstanty – doporučeno: `from aifactory.engine.quality import DEFAULT_TEST_TIMEOUT`
  a v `run/task.py` ji jen re-exportovat, ať je jediný zdroj pravdy).
- `test(run)`: `timeout_seconds=getattr(run, "test_timeout", None) or DEFAULT_TEST_TIMEOUT,  # aifactory`.
- `_run` – oprava `TimeoutExpired`:
  ```python
  except subprocess.TimeoutExpired as error:
      returncode = 124
      # aifactory: TimeoutExpired carries bytes even with text=True
      stdout = _text(error.stdout)
      stderr = _text(error.stderr) + (
          f"\nTimed out: exceeded the time limit of {spec.timeout_seconds}s."  # aifactory
      )
  ```
  s pomocnou funkcí
  ```python
  def _text(value: str | bytes | None) -> str:  # aifactory
      if value is None: return ""
      return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
  ```
- Payload eventu `quality:{name}`: přidat `"timeout_seconds": spec.timeout_seconds,  # aifactory`
  (pro všechny kontroly; nevadí). Event `quality:test` tak nese limit.
- `run_tests`: failures zprávu nech ve stávajícím tvaru — `output_tail` obsahuje hlášku
  „Timed out: exceeded the time limit of Ns.“; volitelně pro `returncode == 124` místo
  „exited 124“ napsat „exceeded the time limit of Ns“ (pak se značkou `# aifactory`).
  Krok musí skončit `passed=False`.
- `vendor/` a `prototype/` neměnit.

### 10. `src/aifactory/skill/skill.md`
- V sekci polí tasku (za odrážku `test`, ~ř. 121–124):
  „- `test_timeout` is the time limit of the workflow's `test` steps in whole seconds greater
  than 0 (own or inherited, like `test`); without it `test_timeout` from `.factory/config.yaml`,
  else 600. An invalid value is reported by `factory backlog check` and stops
  `factory task run` with `invalid_test_timeout`.“
- V sekci workflow (odrážka o `test` step, ~ř. 217–220): doplnit, že limit se řídí
  task `test_timeout` → `index.md` → `test_timeout` v `.factory/config.yaml` → 600 s,
  překročení krok shodí (exit 124, hláška o limitu), a že event `quality:test` nese i
  `timeout_seconds`.
- Pokud skill.md někde vyjmenovává klíče `.factory/config.yaml` (hledej `test_command`),
  přidej tam `test_timeout`.

### Dashboard (`web/settings.py`) — mimo rozsah, NEMĚNIT. Ověř jen, že stávající
web testy projdou (nové pole má default `None`; `SHARED_FIELDS` se nemění).

## Testy (žádné volání modelu; reálné podprocesy přes `sys.executable -c`)

### `tests/run/test_task_test_timeout.py` (nový; vzor `tests/run/test_task_test_command.py`)
Fixture `script`/`repo` a `setup(...)` zkopírovat, rozšířit o `task_timeout`,
`step_timeout`, `config_timeout` (zapisují `test_timeout: <json>` do tasku / step
`index.md` / `config.yaml`). Test příkaz nastav v tasku `test: py("print('ok')")`.
Helper `ran_timeouts(repo, run_id)` čte `payload_json["timeout_seconds"]` z eventů
`quality:test` v `.factory/trace.db`.
- `test_task_timeout_beats_index_and_config`: task 41, index 42, config 43 → `[41]`.
- `test_index_timeout_beats_config`: index 42, config 43 → `[42]`.
- `test_project_index_timeout_is_inherited` (index projektu `backlog/M01-core/index.md`) → jeho hodnota.
- `test_config_timeout_beats_default`: config 43 → `[43]`.
- `test_default_timeout_is_600`: nic → `[600]`.
- `test_retest_uses_the_same_timeout`: steps `[plan, test, {test: {id: retest}}]` → `[41, 41]`.
- `test_exceeded_timeout_fails_the_step`: `test: py("import time; time.sleep(30)")`,
  `test_timeout: 1` → run `failed`, `error == "accept not met"`,
  `wf.results["test"]["passed"] is False`, ve failures je „time limit of 1s“,
  žádný `TypeError`; běh trvá zjevně < 30 s.
  Variantu s výstupem: příkaz nejdřív vypíše text (`print('x', flush=True)`) a pak spí —
  pokrývá cestu, kde `TimeoutExpired.stdout` jsou `bytes`.
- `test_invalid_timeout_stops_before_start` parametrizovaný: task `0`, task `"600"`,
  task `true`, step `-5`, step `1.5` → `TaskRunError` s kódem `invalid_test_timeout`,
  žádný worktree, žádná větev `factory/`, `script.calls == []`.
- Neplatný `test_timeout` v `config.yaml` → `run_task` skončí chybou (`TaskRunError` z
  načtení configu, kód `invalid_config` nebo co dnes vrací – ověř) před startem.

### `tests/workflow/test_workflow_test_timeout.py` (nový; vzor `test_workflow_test_command.py`)
- `run_workflow(..., test_command=[py sleep 30], test_timeout=1)` → `results["test"]["passed"] is False`, failures zmiňují limit.
- `run_workflow(..., test_command=[py ok], test_timeout=5)` → passed.
- Default: přímé volání `engine_quality.test(run)` přes `session.ensure` (jako
  `test_default_test_command_is_just_test`) s `run.test_argv = [py ok]` → v trace / výsledku
  limit 600 (ověř přes `QualityCheckSpec` nebo event payload; nejjednodušší je
  monkeypatch `engine_quality._run` zachytit `spec.timeout_seconds` == 600, a s
  `run.test_timeout = 7` == 7).
- Regrese `TypeError`: přímo `engine_quality._run(QualityCheckSpec(name="x", area="backend", operation="build", argv=[py print+sleep], timeout_seconds=1), run)` → `returncode == 124`, `output_tail` obsahuje vypsaný text i hlášku o limitu.

### `tests/backlog/test_backlog_test_timeout_field.py` (nový; vzor `test_backlog_test_field.py`)
- platné hodnoty v tasku i `index.md` → `factory backlog check --json` vrátí 0 a žádné issues.
- neplatná v tasku (`0`, `-1`, `"600"`, `true`, `1.5`) → `invalid_field`, cesta tasku,
  `'test_timeout'` ve zprávě, hodnota zůstává v `task.own`.
- neplatná v `index.md` → `invalid_field` s cestou indexu, `effective_test_timeout` ji vrátí.
- `effective_test_timeout`: nejbližší vyhrává, `null` se přeskakuje, `None` když nikde.

### `tests/config/test_config_settings.py` (rozšířit)
- default `settings.test_timeout is None`; `test_timeout: 1800` se načte;
  `0`, `-1`, `"1800"`, `true`, `1.5` → `parse_project_settings`/`load_config` hlásí issue
  obsahující `test_timeout` (`ConfigError`). Podívej se, jak testy v souboru dnes testují
  neplatné hodnoty, a drž stejný styl.

## Ověření
Z kořene worktree:
- `just test`
- `just typecheck`
- `just lint`
Všechny musí skončit exit 0 (posuzuj podle exit kódu). Před tím rychle cíleně:
`cd aifactory && uv run pytest -q tests/run/test_task_test_timeout.py tests/workflow/test_workflow_test_timeout.py tests/backlog/test_backlog_test_timeout_field.py tests/config/test_config_settings.py tests/run/test_task_test_command.py tests/web`
(ověř v justfile, jak se testy aifactory spouštějí, a použij stejný runner).

## Dokumentace
`app_docs/HAIFA-S06-T01-casovy-limit-kroku-test-test-timeout.md`: krátce popsat klíč,
pořadí (task → index.md → config.yaml → 600), kód `invalid_test_timeout`, payload
`timeout_seconds` a opravu `TimeoutExpired` bytes.

## Omezení
- Měnit jen `aifactory/`, `justfile`, spec a doc soubor tohoto tasku.
- Změny logiky v `aifactory/src/aifactory/engine/` označit `# aifactory`.
- `vendor/`, `prototype/`, dashboard, limity lint/typecheck/build a `command` kroky neměnit.
- Testy nevolají model (fake harness `fake_env` jako v `test_task_test_command.py`).
