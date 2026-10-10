# HAIFA-S06-T01: Časový limit kroku test (`test_timeout`)

## Co se změnilo a proč

Krok `test` měl pevný limit 600 s (`engine/quality.py`), což nestačí třeba testům Omnibusu
(1800 s). Nově jde limit nastavit klíčem `test_timeout` (celé sekundy větší než 0).
Pořadí, ve kterém se hledá hodnota:

1. task (front matter),
2. nejbližší `index.md` nad taskem (dědí se jako `test`, protože je v `INHERITED_KEYS`;
   úroveň s `null` se přeskakuje),
3. `.factory/config.yaml` (`test_timeout: 1800`),
4. výchozích 600 s (`aifactory.engine.quality.DEFAULT_TEST_TIMEOUT`).

Limit se použije v každém kroku s akcí `test` v běhu tasku, tedy i v `retest` a v testu
ve workflow `resolve`: `run_task` ho spočítá jednou přes `resolve_test_timeout` a předá
ho přes `_Job` do `run_workflow(test_timeout=...)` → `Run.test_timeout` → `quality.test`.
Událost `quality:*` v trace nově nese `timeout_seconds`, takže `quality:test` obsahuje
použitý limit.

## Validace

- `check_timeout` (`config/settings.py`) přijme jen `int` > 0. `bool` neprojde.
- `factory backlog check` hlásí neplatnou hodnotu v tasku nebo v `index.md` jako
  `invalid_field`. Hodnota v backlogu zůstane, aby běh tasku selhal a tiše
  nespadl zpět na 600 s.
- `load_config` hlásí neplatný `test_timeout` v `config.yaml` jako `ConfigError`
  (`ProjectSettings.test_timeout` je `Field(gt=0, strict=True)`).
- `factory task run` při neplatné hodnotě v tasku nebo v `index.md` skončí chybou
  `invalid_test_timeout` (nový kód v `skill/codes.py`). Stane se to ještě před vytvořením
  větve a worktree a před voláním modelu.
- Za neplatné se považuje `0`, záporné číslo, řetězec (`"1800"`), `true`/`false` a desetinné číslo.

## Překročený limit

Příkaz se ukončí a krok skončí s `passed: false`, exit 124 a hláškou
„Timed out: exceeded the time limit of Ns.“ Opravený je i pád
`TypeError: can't concat str to bytes`: `TimeoutExpired.stdout/stderr` jsou `bytes`
i při `text=True`, takže je nová funkce `_text` v `engine/quality.py` dekóduje.
Částečný výstup se tak zachová.

## Soubory

- `aifactory/src/aifactory/config/settings.py`: `check_timeout`, `ProjectSettings.test_timeout`.
  Export je v `config/__init__.py`.
- `aifactory/src/aifactory/backlog/model.py` (`INHERITED_KEYS`), `derived.py`
  (`effective_test_timeout`, společný helper `_nearest`), `loader.py` (`_timeout_issue`),
  `__init__.py` (export).
- `aifactory/src/aifactory/run/task.py`: `resolve_test_timeout`, pole `_Job.test_timeout`.
- `aifactory/src/aifactory/workflow/interpreter.py`: parametr `run_workflow(test_timeout=...)`.
- `aifactory/src/aifactory/engine/runner.py` (`Run.test_timeout`) a `engine/quality.py`
  (`DEFAULT_TEST_TIMEOUT`, `_text`, `timeout_seconds` v trace). Změny jsou označené `# aifactory`.
- `aifactory/src/aifactory/skill/skill.md`: popis klíče a limitu kroku `test` pro `factory --skill`.
  `skill/codes.py` přidává kód `invalid_test_timeout`.

## Ověření

```sh
just test        # nebo jen nové testy:
uv run pytest aifactory/tests/run/test_task_test_timeout.py \
  aifactory/tests/workflow/test_workflow_test_timeout.py \
  aifactory/tests/backlog/test_backlog_test_timeout_field.py \
  aifactory/tests/config/test_config_settings.py
just typecheck && just lint
```

- `tests/run/test_task_test_timeout.py` spouští opravdový podproces. Ověřuje pořadí
  task > `index.md` > `config.yaml` > 600, stejný limit pro `retest`, shození kroku při
  překročení limitu (i s částečným výstupem a bez `TypeError`) a zastavení před startem
  při neplatné hodnotě.
- `tests/workflow/test_workflow_test_timeout.py` ověřuje limit přímo přes `run_workflow`
  včetně dekódování částečného výstupu.
- `tests/backlog/test_backlog_test_timeout_field.py` pokrývá `check_timeout`, hlášení
  v `backlog check` a dědění přes `effective_test_timeout`.
- `tests/config/test_config_settings.py` pokrývá načtení a odmítnutí hodnoty v `config.yaml`.
