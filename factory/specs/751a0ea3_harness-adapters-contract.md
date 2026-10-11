# Plán: úkol 2.3 — harnessy claude/codex/pi, registr a kontraktové testy v `aifactory`

## Cíl

Přenést registr harnessů a adaptér Codexu z prototypu do `aifactory/src/aifactory/harness/`. Adaptéry claude a pi už v balíčku jsou jako `aifactory.engine.agent_cc` a `aifactory.engine.agent_pi` (úkol 2.2 je přenesl doslova). Doplnit:

- výslovný harness u agenta (`harness: claude|codex|pi`) a přepis harness/model/thinking u kroku (D13), bez odvozování ze jména modelu,
- `factory harness check [--json] [--config PATH]`,
- společné kontraktové testy pro všechny tři adaptéry s falešnými procesy.

## Pevná omezení (nepřekročit)

- `vendor/` a `prototype/` se nemění. Fixtures z prototypu se **kopírují** (`cp`), ne přesouvají.
- **Soubory v `aifactory/src/aifactory/engine/` se nemění.** Jsou doslovnou kopií sssf (riziko R6, vyloučené z ruff/mypy v `pyproject.toml`). Rozšíření dělej jen v `aifactory.harness`. Nepřepisuj ani globální jména v modulech enginu (prototyp to dělal v `config_types.install()`, tady to není potřeba, viz bod 3).
- Testy nevolají model ani skutečné CLI. Každé spuštění `claude`/`codex`/`pi` jde přes falešný `Popen`, katalog modelů pi (`agent_pi._pi_catalog`) je vždy nahrazený.
- Nic z `aifactory.harness` nesmí importovat `aifactory.engine.models`, `aifactory.engine.chain` ani `aifactory.engine.cli`. Tyhle moduly odvozují harness ze jména modelu (sssf compose), a to D13 zakazuje.
- Mimo rozsah: worktree (2.9), `.factory/` (2.4), interpret workflow (2.7). Úkol 2.3 dodá API pro přepis u kroku a testuje ho přímo. Napojení na YAML workflow udělá úkol 2.7.

## Soubory

### Nové: `aifactory/src/aifactory/harness/`

#### 1. `__init__.py`: registr

Port `prototype/src/haifa_proto/harness/__init__.py` s těmito změnami:

```python
HARNESSES: dict[str, str] = {
    "claude": "aifactory.engine.agent_cc",
    "codex": "aifactory.harness.codex",
    "pi": "aifactory.engine.agent_pi",
}
ALIASES: dict[str, str] = {"claude_code": "claude"}
CLI_BINARIES: dict[str, tuple[str, str]] = {
    "claude": ("CLAUDE_CODE_PATH", "claude"),
    "codex": ("CODEX_PATH", "codex"),
    "pi": ("PI_PATH", "pi"),
}
REQUIRED_API = ("run", "resolve_model", "context_window", "ToolCallTracker")
HarnessName = Literal["claude", "codex", "pi"]
```

- `canonical(name) -> str`: alias převede na kanonické jméno. Na neznámé jméno vyhodí `ValueError("unknown harness 'x', available: [...]")`.
- `load(name) -> ModuleType`: `importlib.import_module(HARNESSES[canonical(name)])`. Žádné `sys.path` ani `engine.ensure_engine_on_path`.
- `check_interface(module) -> list[str]`
- `install() -> ModuleType`: vrátí `aifactory.engine.agents`. Zaregistruje `claude`, `codex`, `pi` i `claude_code` do `agents.INTERFACES`, ale **jen chybějící klíče** (`setdefault`). Test nebo jiný volající, který na klíč dosadil fake, tak o něj nepřijde (poučení z `prototype/.../workflow.py:ensure_harnesses`). Kontrola `check_interface` se provede při každé registraci a při chybě vyhodí `RuntimeError`. Funkce je idempotentní.

#### 2. `codex.py`: adaptér Codexu

Port `prototype/src/haifa_proto/harness/codex.py` 1:1, jen importy vedou přímo na balíček:

```python
from aifactory.engine.data_types import AgentRequest, AgentResult
from aifactory.engine.utils import now_iso, operator_env
```

Zruš proxy `_dt`/`_utils`/`engine.load_engine_module`. Chování zůstává stejné:
- první kolo je `codex exec ... -C <cwd> -- <prompt>`, opravné kolo `codex exec resume ... -- <thread_id> <prompt>`,
- stavový soubor `<session_dir>/<session_id>.codex.json`,
- delta usage, `Popen(cwd=request.cwd, stdin=DEVNULL, env=operator_env())`,
- `CODEX_PATH`, `CODEX_SANDBOX` a `CODEX_SAFE_MODE` z env.

Anotace musí projít `mypy --strict`. Kde je to nutné, použij `Any` jako v prototypu. `untyped_calls_exclude = ["aifactory.engine"]` volání do enginu povoluje.

#### 3. `config.py`: výslovný harness v konfiguraci

Engine (`data_types.AgentConfig`/`ConfigDefaults`) typuje `coding_agent: Literal["pi","claude_code"]` a má výchozí `"pi"`. Proto:

- Rozšířené podtřídy `AgentConfig`, `ConfigDefaults` a `SSSFConfig` (dědí z `aifactory.engine.data_types`, takže `isinstance` s originály platí). Pole `coding_agent: HarnessName` bez výchozí hodnoty u `AgentConfig`, u `ConfigDefaults` jako `HarnessName | None = None`. `SSSFConfig` přepíše `defaults` a `agents` na rozšířené typy. Přepis typu pole spolu s mypy strict: buď třídní syntaxe s `# type: ignore[assignment]` u přepsaných polí, nebo `pydantic.create_model` jako v `prototype/.../config_types.py`. Obojí je v pořádku, podmínkou je zelený `just typecheck`.
- Každá rozšířená třída má vlastnost `harness` (vrací `coding_agent`), aby kód HAIFA mluvil jazykem D13.
- `normalize_raw(raw: dict) -> dict`, čistá funkce nad YAML slovníkem. Pro `defaults` i pro každého agenta:
  - klíč `harness` je primární, `coding_agent` se přijímá kvůli kompatibilitě se sssf,
  - pokud jsou uvedené oba s různou kanonickou hodnotou, je to chyba,
  - hodnota se převede přes `canonical()` (`claude_code` → `claude`) a uloží do `coding_agent`, klíč `harness` se odstraní,
  - poté se provede stejné dědění z `defaults` jako `agents.load_config` (klíče `coding_agent, model, thinking, color, tools, writes` a `harness_engineering`),
  - agent, který po dědění nemá `coding_agent`, je chyba. **Harness se nikdy nedoplní ze jména modelu ani z výchozího `"pi"` enginu.**
  - Všechny problémy se sesbírají a vyhodí se jedna výjimka `HarnessConfigError(ValueError)` se seznamem, např. `agent 'builder': harness is not set (claude|codex|pi)`, `agent 'x': unknown harness 'gpt'...`, `agent 'x': harness 'codex' conflicts with coding_agent 'pi'`.
- `load_config(path: str | Path) -> SSSFConfig` načte YAML, zavolá `normalize_raw` a vrátí `SSSFConfig.model_validate(raw)` (rozšířenou třídu). Úkol 2.4 si později napojí `normalize_raw` na `.factory/`.
- `validate(cfg, required: list[str]) -> None` zavolá `install()` a pak `aifactory.engine.agents.validate(cfg, required)`. Engine tak ověří `resolve_model` proti **zvolenému** harnessu a zamítne `harness_engineering` mimo pi.

#### 4. `override.py`: přepis u kroku workflow (D13)

```python
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")

@dataclass(frozen=True)
class StepOverride:
    harness: str | None = None
    model: str | None = None
    thinking: str | None = None
```

- `effective_agent(agent, override) -> AgentConfig` vrátí `agent.model_copy(update=...)` jen s vyplněnými poli. Harness se převede přes `canonical()`. Když výsledný harness není `pi`, nastaví se `harness_engineering=[]`, protože rozšíření pi patří jen pi (stejně jako v `prototype/.../workflow.py:_apply_step`). **Přepis samotného modelu nikdy nemění harness.**
- `check_override(agent, override) -> list[str]` vrátí problémy a nic nespouští: neznámý harness, thinking mimo `THINKING_LEVELS`, a `load(harness).resolve_model(model)` pro výslednou dvojici (harness, model), kde `ValueError` se stane problémem.
- `@contextmanager step_override(cfg, agent_name, override) -> Iterator[AgentConfig]`:
  - zavolá `check_override`; když najde problémy, vyhodí `HarnessConfigError` ještě před jakoukoli změnou,
  - v `cfg.agents` vymění záznam agenta za `effective_agent(...)` a na konci ho vždy vrátí zpět (i po výjimce).
  - Engine (`agents.execute`) hledá agenta v `run.cfg.agents` podle jména, takže přepis platí právě pro jedno volání fáze uvnitř bloku `with`.

#### 5. `check.py`: `factory harness check`

Port `prototype/src/haifa_proto/harness/check.py`:
- `HarnessStatus` (`name, binary, path, version, error`, plus nové `agents: list[str]` = agenti v konfiguraci, kteří harness používají). Dále `ok` a `to_json()`.
- `check_harness(name, agents=())`: binárka z env proměnné (`CLI_BINARIES`) nebo výchozí, `shutil.which`, spuštění `[path, "--version"]` s `timeout=15` a `env=aifactory.engine.utils.operator_env()`. Verze je první neprázdný řádek stdout, jinak stderr. Nenulový exit znamená chybu.
- `harnesses_in_config(cfg) -> dict[str, list[str]]`: kanonický harness → jména agentů, v pořadí `HARNESSES`.
- `check_all(cfg: SSSFConfig | None = None) -> list[HarnessStatus]`: s konfigurací ověří jen harnessy, které se v ní používají. Bez konfigurace ověří všechny tři (výchozí konfiguraci `.factory/` doplní úkol 2.4).

### Úpravy

#### `aifactory/src/aifactory/cli.py`

- Z placeholderu `harness` udělej skutečný subparser se subpříkazem `check` (`--json`, `--config PATH`). Ostatní subpříkazy zůstanou placeholdery (`SUBCOMMANDS` ponech, jen harness dostane vlastní parser; texty nápovědy zůstanou).
- `factory harness` bez subpříkazu vypíše nápovědu harness parseru a vrátí 0.
- `factory harness check` vypíše pro každý harness řádek: jméno, cestu nebo `not on PATH`, verzi nebo chybu, a agenty z konfigurace, pokud je zadaná. Vrátí 0, když jsou všechny kontrolované `ok`, jinak 1.
- S `--json` vypíše `{"ok": bool, "harnesses": [status.to_json(), ...]}`.
- Chyba konfigurace (`HarnessConfigError`, chybějící soubor) → hláška na stderr a návratový kód 2.

#### `aifactory/tests/test_smoke.py`

`test_subcommands_not_implemented` předpokládá, že všechny subpříkazy vrací 2. Vynech z něj `harness` a přidej `assert main(["harness"]) == 0`.

#### `aifactory/pyproject.toml`

Jen pokud je to nutné, např. kvůli ruff/mypy pro nové soubory. Nové moduly `aifactory.harness.*` **nepřidávej** do vyloučení z ruff/mypy, musí být čisté.

### Nové testy: `aifactory/tests/harness/`

**Pozor na strukturu:** `tests/` nemá `__init__.py` a mypy kontroluje `files = ["src", "tests"]`. Druhý `conftest.py` by způsobil `Duplicate module named 'conftest'`. Proto:
- **v `tests/harness/` nevytvářej `conftest.py`**,
- helpery jsou obyčejné funkce v `tests/harness/harness_fakes.py`, importované `from harness_fakes import ...` (stejný mechanismus jako `engine_fakes`),
- jména testovacích souborů musí být v celém `tests/` unikátní (prefix `test_harness_*`).

Fixtures: `cp prototype/tests/fixtures/harness/*.jsonl aifactory/tests/harness/fixtures/`

#### `harness_fakes.py`

- `FakePopen`, `FakeSpawner` a `normalize` z `prototype/tests/harness_fakes.py`. Rozšíření:
  - `FakeSpawner` přijímá frontu **textů** (JSONL řetězců), nejen jmen fixtures,
  - **předává skutečnému `Popen` každý příkaz, jehož `cmd[0]` není binárka harnessu** (`agent_cc.CLAUDE_PATH`, `codex.CODEX_PATH`, `agent_pi.PI_PATH`). Důvod: `monkeypatch.setattr(module.subprocess, "Popen", ...)` patchuje globální modul `subprocess` a `subprocess.run` (git v `permissions`) volá `Popen` interně. Referenci na skutečný `Popen` si ulož před patchem.
  - Nadbytečné spuštění harnessu vyhodí `AssertionError`.
- Generátory proudů podle fixtures:
  - `claude_stream(text, *, tool=True) -> str`: `system/init`, `assistant tool_use Bash ls`, `user tool_result`, `assistant text`, `result` s `modelUsage`,
  - `pi_stream(text, *, tool=True) -> str`: `message_end toolCall`, `tool_execution_start/end`, `message_end text`,
  - `codex_stream(text, *, thread_id, usage, tool=True) -> str`: `thread.started`, `command_execution` started/completed, `agent_message`, `turn.completed`.
- `fake_pi_catalog(monkeypatch, tmp_path)`: `agent_pi._pi_catalog` vrací `[("openai","gpt-5.5",272000)]`, `agent_pi.MODELS_JSON` míří do tmp (jako fixture `agents` v prototypu).
- `MODELS = {"claude": "sonnet", "codex": "gpt-5.5", "pi": "openai/gpt-5.5"}`. Codex i pi dostávají model `openai/...`/`gpt-5.5`, takže testy zároveň dokazují, že se harness neodvozuje z modelu.
- `build_repo(path)` a `rows(db, sql, *args)`: malé kopie z `tests/engine/engine_fakes.py` (git init, `README.md`, `protected.md`, commit).
- `make_env(tmp_path, monkeypatch, harness, *, agent="builder") -> HarnessEnv`:
  - postaví repo `tmp_path/"repo"`, udělá `chdir` a nastaví `ENGINEER_NAME`,
  - vytvoří prompty a YAML konfiguraci **s `harness: <name>` u agenta** (bez `coding_agent`) s `data_dir` a `observability.db` v tmp, načtenou přes `aifactory.harness.config.load_config`,
  - zavolá `fake_pi_catalog`, zaregistruje skutečný modul přes `monkeypatch.setitem(agents.INTERFACES, name, harness.load(name))`,
  - nahradí `Popen` spawnerem a pro jistotu obnoví obsluhu `SIGINT/SIGTERM` (viz `tests/engine/conftest.py`).
  - Vrátí dataclass `(cfg, repo, db_path, data_dir, spawner, module)`.
- `start_run(env)` a `agent_phase(run, owner, *, retries, gates)`: jako v `engine_fakes`, přes `session.ensure` a `run.phase(...).call(AgentCall(...))`.

#### `test_harness_registry.py`

- `install()` zaregistruje `claude, codex, pi, claude_code`, je idempotentní, `INTERFACES["claude_code"] is INTERFACES["claude"]` a `INTERFACES["codex"] is aifactory.harness.codex`.
- `install()` nepřepíše klíč, na který test dosadil fake (`monkeypatch.setitem`).
- `canonical` převádí alias a na `"gpt"` vyhodí `ValueError`.
- claude a pi se načítají z `aifactory.engine` (`Path(module.__file__).parent == aifactory.engine` dir), ne z `vendor/`.
- `check_interface` vrací `[]` pro všechny tři. `run` má parametry `request, on_event, on_spawn, on_exit, on_wait`.
- Statická kontrola: zdrojové soubory `aifactory/harness/*.py` neobsahují `engine.models`, `engine.chain` ani `from aifactory.engine import models`. Jednoduchý grep přes `Path.read_text`.

#### `test_harness_config.py`

- Agent s `harness: codex` a `model: gpt-5.5` → `coding_agent == "codex"`, `agent.harness == "codex"`, `agents.interface(agent) is codex` a `validate(cfg, ["a"])` projde.
- `defaults: {harness: claude}` se zdědí. `harness: claude_code` i `coding_agent: claude_code` se převedou na `claude`.
- Agent bez harnessu (ani v defaults) → `HarnessConfigError` s „harness is not set“, **i když model vypadá jako claude** (`model: opus`). Důkaz, že se harness neodvozuje.
- Konflikt `harness: codex` + `coding_agent: pi` → chyba. Neznámý harness → chyba se seznamem dostupných.
- `harness: pi` + `model: openai/gpt-5.5` → pi (s falešným katalogem). `harness: codex` + týž model → codex. Stejný model, jiný harness, podle zápisu.
- `harness: claude` + `model: openai/gpt-5.5` → `validate` skončí `SystemExit`, nepřepne se na jiný harness.
- `harness: codex` + `harness_engineering: [x]` → `validate` odmítne.
- `isinstance(cfg, aifactory.engine.data_types.SSSFConfig)`.

#### `test_harness_override.py`

- `effective_agent` s `StepOverride(harness="codex", model="gpt-5.5", thinking="high")` přepíše všechna tři pole. Pole, která nejsou uvedená, zůstanou z agenta.
- `StepOverride(model="gpt-5.5")` u agenta s `harness: claude` → harness zůstane `claude` a `check_override` hlásí problém s modelem (nepřepne na codex).
- Neplatný thinking a neznámý harness → problém. Přepnutí z pi na claude vyprázdní `harness_engineering`.
- `step_override` v bloku vymění agenta v `cfg.agents` a po bloku (i po výjimce uvnitř) vrátí původní objekt. Při neplatném přepisu vyhodí chybu dřív, než cokoli změní.
- End-to-end přes engine: `make_env(..., "claude")` s agentem na `claude`, dále zaregistrovaný codex a pi se spawnery. Tři fáze v jednom běhu, každá v `step_override` s jiným harnessem (claude, `codex`+`gpt-5.5`+`high`, `pi`+`openai/gpt-5.5`+`low`). Spawner zaznamená `cmd[0]` claude, codex, pi v tomto pořadí, codex má `model_reasoning_effort="high"` a pi `--thinking low`. Událost `agent_start` v trace má `coding_agent` postupně `claude`, `codex` a `pi`.
  - Pozor na `_agent_session_id`: agent se stejným jménem a jiným modelem dostane novou session, to je v pořádku. Pro jednoduchost mohou kroky používat tři různé agenty (`planner`, `builder`, `reviewer`) s přepisem na každém.

#### `test_harness_contract.py`: kontraktové testy (jádro úkolu)

Parametrizace `@pytest.mark.parametrize("name", ["claude", "codex", "pi"])` tam, kde to jde.

1. **Adaptér přímo** (port `prototype/tests/test_harness_contract.py`): nahraný tah → očekávané `text/tokens/cost/usage`, tool-call záznamy s klíči ⊆ `RECORD_KEYS` a `ended_at`, `on_spawn/on_exit == [PID]`, raw výstup zapsaný beze změny, `Popen` kwargs `cwd == request.cwd` a `stdin is DEVNULL`. Přenes i testy specifické pro codex: první příkaz, `resume` se stejným thread_id, reset čítače, `turn.failed` → `RuntimeError`, `resolve_model` přijímá a odmítá, sandbox. Očekávané hodnoty `EXPECTED` převezmi z prototypu.
2. **Přes engine, stejný tvar envelope:** jeden test projde smyčkou všechny tři harnessy, každý ve vlastním podadresáři `tmp_path`. `agent_phase(run, "builder")` se skriptovanou odpovědí `{"status":"success","summary":"done","artifacts":["specs/x.md"]}`. Soubor `session_dir/builder/envelope.json` je pro všechny tři **identický slovník**. Řádky tabulky `envelopes` (`output_type`, `valid`, `attempt`, JSON payload) jsou shodné.
3. **Obnovení téže session v opravném kole** (parametrizovaně): gate, který projde až při `summary == "fixed"`, `retries=1`. Spawner dostane dva proudy (`summary: wrong`, pak `summary: fixed`). Ověř:
   - claude: 1. volání obsahuje `--session-id U`, 2. volání `--resume U`, kde `U == agent_cc.session_uuid(<session_id>)`, a nemá `--session-id`,
   - pi: obě volání mají stejné `--session-id` a `--session-dir`,
   - codex: 1. volání `[CODEX_PATH, "exec", ...]` s `-C`, 2. volání `[CODEX_PATH, "exec", "resume", ...]` bez `-C`, `cmd[-2:] == [THREAD_ID, <korekční prompt>]`,
   - u všech: druhý prompt začíná `"Your previous response failed validation:"`, výsledné `envelope.summary == "fixed"` a `gate_results` je `[(1,0),(2,1)]`.
4. **Zápis událostí do trace** (parametrizovaně):
   - tabulka `events` fáze obsahuje `agent_start` s `payload.coding_agent == name` a `payload.model == MODELS[name]`,
   - alespoň jeden `tool_call` s názvem `Bash: ls` (claude) nebo `bash: ls` (codex, pi) a payloadem s klíči `{tool, tool_call_id, args, ok, agent}` ⊆ payload, `payload.agent == "builder"`,
   - dále `handoff` a `agent_end`,
   - tabulka `processes` má řádek s PID falešného procesu a vyplněným `ended_at`,
   - `agent_sessions` má `coding_agent == name`.
   - Názvy sloupců ověř v `aifactory/src/aifactory/engine/tracer.py`.
5. **cwd agenta je adresář od volajícího** (parametrizovaně): vytvoř druhé git repo `tmp_path/"caller_dir"` přes `build_repo` (permissions potřebuje git s commitem) a po `session.ensure` nastav `run.repo_root = caller_dir`. Proces zůstává v `tmp_path/"repo"`. Ověř, že každé spuštění harnessu má `kwargs["cwd"] == str(caller_dir)`, u codexu navíc `cmd[cmd.index("-C")+1] == str(caller_dir)` a `caller_dir != Path.cwd()`.

#### `test_harness_check_cli.py`

Port `prototype/tests/test_cli_harness.py` (fake `shutil.which` a `subprocess.run`, smazané `*_PATH` env proměnné) s `aifactory.cli.main` a těmito případy:
- bez `--config`: kontrolují se všechny tři, chybějící codex → výstup `not on PATH` a exit 1. Pořadí volání `--version` jen pro nalezené.
- `--json`, všechny přítomné → `ok: true`, pořadí `claude, codex, pi` a přesný slovník pro codex (včetně `agents: []`).
- `--config <yaml>` s agenty jen na `claude` a `pi` → kontrolují se jen `claude` a `pi` (codex se vůbec nezmíní ani nespustí), `agents` obsahuje jména.
- `CODEX_PATH=/opt/x/codex` → hledá se tato binárka.
- nenulový `--version` → `error` obsahuje `exited 2`.
- `factory harness` → 0. Konfigurace bez harnessu u agenta → exit 2 a hláška na stderr.

## Postup

1. `mkdir -p aifactory/src/aifactory/harness aifactory/tests/harness/fixtures && cp prototype/tests/fixtures/harness/*.jsonl aifactory/tests/harness/fixtures/`
2. `harness/__init__.py`, pak `codex.py`, `config.py`, `override.py`, `check.py`.
3. `cli.py` a úprava `tests/test_smoke.py`.
4. Testy v `tests/harness/`.
5. Ověření:
   ```bash
   just test
   just typecheck
   just lint          # při chybě formátu: cd aifactory && uv run ruff format .
   git status --porcelain vendor prototype aifactory/src/aifactory/engine   # musí být prázdné
   ```
   Výsledek posuzuj podle návratového kódu příkazu, ne podle slov ve výstupu.

## Hotovo, když

- `harness: claude|codex|pi` se u agenta vyžaduje výslovně (vlastní klíč nebo `defaults`). Chybějící harness je chyba, nikdy se neodvodí z modelu. `step_override` přepíše harness, model a thinking pro jeden krok.
- `factory harness check [--json] [--config PATH]` funguje podle testů.
- Kontraktové testy pokrývají pro claude, codex i pi: tvar envelope, obnovení téže session (codex přes `exec resume`), události v trace a cwd od volajícího.
- `just test`, `just typecheck` a `just lint` projdou. `vendor/`, `prototype/` a `aifactory/src/aifactory/engine/` jsou beze změny.
