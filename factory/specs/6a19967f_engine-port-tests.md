# Plán: přenos enginu sssf do `aifactory.engine` a testy chování (R6)

## Cíl

Engine sssf (`vendor/sssf/templates/adws/adw_modules/`) žije v balíčku jako `aifactory.engine`,
importuje se bez `sys.path` a bez `vendor/`. Rozšíření z prototypu (`engine.py` = načítání modulů,
`roles.py` = registr rolí z YAML) jsou přenesená vedle něj. Testy s falešným harnessem pokryjí
chování, na které spoléhá prototyp i sssf (riziko R6).

Mimo rozsah: harnessy claude/codex/pi (2.3), interpret workflow (2.7), jakákoli změna chování.
`vendor/` a `prototype/` se NEMĚNÍ. Testy nevolají model ani skutečné CLI.

## Klíčové rozhodnutí: moduly se kopírují bajt po bajtu

Všech 20 souborů v `vendor/sssf/templates/adws/adw_modules/` už používá **jen relativní importy**
(`from .data_types import …`, `from . import agents`). Po zkopírování do
`aifactory/src/aifactory/engine/` fungují jako `aifactory.engine.*` bez jediné úpravy.
Proto se **needituje ani import, ani formát** – soubory zůstanou identické s vendorem, a
`diff -r` je pak důkaz, že se logika nezměnila (R6).

Důsledek: vendorový kód neprojde `mypy --strict` (81 chyb) ani `ruff check`/`ruff format --check`
(51 chyb, 18 souborů k přeformátování). Neopravovat je v kódu (každá úprava = riziko změny chování,
např. pydantic anotace v `data_types.py`). Místo toho je vyjmout **v konfiguraci** – viz krok 2.
Ověřeno sondou: s níže uvedenou konfigurací mypy projde i na testu, který volá
`agents.load_config`, `runner.Run(...)` a `Run.finish`.

## Kroky

### 1. Zkopírovat engine

```bash
mkdir -p aifactory/src/aifactory/engine
cp vendor/sssf/templates/adws/adw_modules/*.py aifactory/src/aifactory/engine/
```

Nekopírovat `__pycache__`. Vzniknou (20 souborů, `__init__.py` je prázdný):
`__init__.py agent_cc.py agent_pi.py agents.py chain.py changes.py cli.py console.py data_types.py
gates.py git_helper.py models.py permissions.py prompts.py quality.py roles.py runner.py session.py
tracer.py utils.py`.

`__init__.py` zůstane prázdný (stejně jako ve vendoru). Nic do něj nepřidávat – import
`aifactory.engine` nesmí tahat harnessy ani `rich`.

### 2. `aifactory/pyproject.toml` – vyjmout vendorové moduly z lintu a typové kontroly

Přesně tyto změny (nic jiného v souboru neměnit):

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]
# Engine ported verbatim from sssf (vendor/sssf/templates/adws/adw_modules). Kept
# byte-identical so `diff -r` proves no logic changed (risk R6); not linted/formatted.
extend-exclude = [
    "src/aifactory/engine/__init__.py",
    "src/aifactory/engine/agent_cc.py",
    "src/aifactory/engine/agent_pi.py",
    "src/aifactory/engine/agents.py",
    "src/aifactory/engine/chain.py",
    "src/aifactory/engine/changes.py",
    "src/aifactory/engine/cli.py",
    "src/aifactory/engine/console.py",
    "src/aifactory/engine/data_types.py",
    "src/aifactory/engine/gates.py",
    "src/aifactory/engine/git_helper.py",
    "src/aifactory/engine/models.py",
    "src/aifactory/engine/permissions.py",
    "src/aifactory/engine/prompts.py",
    "src/aifactory/engine/quality.py",
    "src/aifactory/engine/roles.py",
    "src/aifactory/engine/runner.py",
    "src/aifactory/engine/session.py",
    "src/aifactory/engine/tracer.py",
    "src/aifactory/engine/utils.py",
]
```

```toml
[tool.mypy]
python_version = "3.11"
strict = true
files = ["src", "tests"]
# Calling the verbatim sssf engine (untyped) from typed code is allowed.
untyped_calls_exclude = ["aifactory.engine"]

# Engine ported verbatim from sssf; see [tool.ruff].extend-exclude.
[[tool.mypy.overrides]]
module = [
    "aifactory.engine.agent_cc",
    "aifactory.engine.agent_pi",
    "aifactory.engine.agents",
    "aifactory.engine.chain",
    "aifactory.engine.changes",
    "aifactory.engine.cli",
    "aifactory.engine.console",
    "aifactory.engine.data_types",
    "aifactory.engine.gates",
    "aifactory.engine.git_helper",
    "aifactory.engine.models",
    "aifactory.engine.permissions",
    "aifactory.engine.prompts",
    "aifactory.engine.quality",
    "aifactory.engine.roles",
    "aifactory.engine.runner",
    "aifactory.engine.session",
    "aifactory.engine.tracer",
    "aifactory.engine.utils",
]
ignore_errors = true
```

Seznamy jsou výslovné, ne `aifactory.engine.*`: nové moduly (`loader.py`, `role_registry.py`)
musí zůstat pod strict mypy a ruffem.

Závislosti: engine potřebuje `pydantic`, `pyyaml`, `python-dotenv`, `rich` – všechny už
v `dependencies` jsou. `uv.lock` se měnit nemusí.

### 3. Přenést rozšíření z prototypu

#### 3a. `aifactory/src/aifactory/engine/loader.py` (z `prototype/src/haifa_proto/engine.py`)

Prototyp řešil jen vložení vendoru do `sys.path` a `load_engine_module(name)`. V balíčku zbude
jen načítání – bez `sys.path`:

```python
"""Single entry point for loading engine modules by name.

The sssf engine lives in ``aifactory.engine`` as a regular package; nothing here
touches ``sys.path``. Kept so callers ported from the prototype can look modules
up by name (``load_engine_module("data_types")``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

ENGINE_PACKAGE = "aifactory.engine"
ENGINE_DIR = Path(__file__).resolve().parent


def load_engine_module(name: str) -> ModuleType:
    """Import ``aifactory.engine.<name>`` (or ``aifactory.engine`` for an empty name)."""
    full = ENGINE_PACKAGE if not name else f"{ENGINE_PACKAGE}.{name}"
    return importlib.import_module(full)
```

`ensure_engine_on_path` a `REPO_ROOT` se nepřenášejí (jediný jejich účel byl `sys.path` k vendoru).

#### 3b. `aifactory/src/aifactory/engine/role_registry.py` (z `prototype/src/haifa_proto/roles.py`)

Jméno `roles.py` je obsazené vendorovým modulem, proto `role_registry.py`.
Obsah zkopírovat z prototypu **beze změny logiky**, jen:

- `from haifa_proto import engine` → `from aifactory.engine import loader as engine`
  (volání `engine.load_engine_module("data_types")` / `("gates")` pak zůstanou doslova stejná).
- `DEFAULTS_DIR = Path(str(resources.files("haifa_proto") / "defaults"))` →
  `DEFAULTS_DIR = Path(str(resources.files("aifactory.engine") / "defaults"))`.
- Docstring modulu: zmínky `adw_modules/roles.py` → „vendorový `aifactory.engine.roles`“ apod.
  Texty chybových hlášek (`"no class … in adw_modules.data_types"` atd.) **neměnit** – jsou
  to výstupy a testy prototypu se na ně mohou odkazovat.

Musí projít strict mypy a ruffem jako v prototypu (prototyp má stejnou konfiguraci).

#### 3c. `aifactory/src/aifactory/engine/defaults/roles.yaml`

`cp prototype/src/haifa_proto/defaults/roles.yaml aifactory/src/aifactory/engine/defaults/roles.yaml`
(beze změny; komentář v hlavičce smí zůstat). Workflow YAML (`defaults/workflows/`) se
NEPŘENÁŠÍ – to je 2.8. Hatch zabalí YAML automaticky (je uvnitř `src/aifactory`).

### 4. Testy v `aifactory/tests/engine/`

Bez `__init__.py` (stejně jako `tests/`). Soubory:

| soubor | obsah |
|---|---|
| `conftest.py` | fixture `engine_env` |
| `engine_fakes.py` | `FakeHarness`, `Script`, `ok()`, `build_repo()` |
| `test_import.py` | import bez `sys.path`/`vendor` |
| `test_role_registry.py` | přenos `prototype/tests/test_roles.py` |
| `test_permissions.py` | rollback mimo `writes` a `protected_files` |
| `test_envelope_retry.py` | re-prompt téže session při nevalidním envelope |
| `test_gate_correction.py` | gate correction do téže session |
| `test_sigterm.py` | SIGTERM ukončí běh a uzavře procesy dětí agenta v trace |
| `test_trace.py` | fáze a události v trace DB, `run.finish(accepted=…)` |

Všechny testy plně typované (strict mypy běží i na `tests/`). Kde engine vrací `Any`, stačí
`assert`/`isinstance` nebo explicitní anotace; `cast` jen výjimečně.

#### 4a. `engine_fakes.py` – falešný harness (vzor `prototype/tests/workflow_fakes.py`)

- `Script`: `queue: dict[str, list[str]]` – **surové texty** odpovědí po agentech (ne jen
  dicty, protože testy potřebují poslat i nevalidní JSON), `effects: dict[str, list[Callable[[Path], None]]]`
  – co agent při daném volání udělá s repem (`cwd`), `calls: list[Call]`.
  Metody `add(agent, *texts)`, `add_ok(agent, **fields)` (= `json.dumps(ok(**fields))`),
  `on(agent, *effects)`.
- `Call`: `agent, session_id, prompt, cwd`.
- `FakeHarness` – drží rozhraní modulu harnessu, které volá `agents.py`:
  `ToolCallTracker` (třída s `observe(event) -> None`), `resolve_model(pattern) -> ("fake", pattern)`,
  `context_window(*a) -> 0`, `run(request, on_event=None, on_wait=None, on_spawn=None, on_exit=None)`.
  `run` zjistí agenta z `Path(request.session_dir).parent.name`, zapíše `Call`, provede další
  efekt (s `Path(request.cwd)`), zavolá `on_spawn(pid)` / `on_exit(pid)` kolem „běhu“ (pid
  nastavitelný atributem `pid`, default `os.getpid()` NE – použít např. 424242, aby
  řádky v `processes` byly odlišitelné), a vrátí
  `data_types.AgentResult(text=<text z fronty>, returncode=0, session_id=request.session_id)`.
  Volitelný hook `during: Callable[[], None] | None` volaný mezi `on_spawn` a `on_exit`
  (pro SIGTERM test). Prázdná fronta → `AssertionError`.
- `ok(**fields) -> dict` = `{"status": "success", "summary": "done", **fields}`.
- `build_repo(repo: Path)` = `git init -q`, `user.email/name`, `README.md` + `protected.md`,
  `git add -A`, `git commit -q -m init` (vzor `build_engine_repo`).

#### 4b. `conftest.py` – fixture `engine_env(tmp_path, monkeypatch)`

1. `repo = tmp_path/"repo"`, `build_repo(repo)`, `monkeypatch.chdir(repo)`
   (`git_helper.repo_root()` a `permissions` pracují s cwd).
2. `monkeypatch.setenv("ENGINEER_NAME", "tester")` (ať `engineer_name()` nevolá git config).
3. Prompty v `tmp_path/"prompts"`: `system.md` = `"system\n"`, `user.md` = `"{{prompt}}\n"`.
4. Config YAML v `tmp_path/"sssf.config.yaml"`: `defaults.data_dir = tmp_path/"data"` (MIMO repo),
   `defaults.protected_files: [protected.md]`, `defaults.coding_agent: claude_code`,
   `observability.db = tmp_path/"data"/"sssf.db"`, agenti:
   - `builder` (`writes: [allowed/**]`),
   - `free` (bez `writes` → `None` = neomezeno, ale `protected.md` chráněné),
   - `keyholder` (`writes: [protected.md]` – odemyká chráněný soubor),
   - `reader` (`writes: []`),
   všichni `model: sonnet`, `prompt_engineering` na soubory výše.
   `cfg = agents.load_config(str(config_path))`.
5. Pojistka: `monkeypatch.setattr(agent_cc, "run", <raise AssertionError>)` a totéž pro `agent_pi`,
   pak `monkeypatch.setitem(agents.INTERFACES, "claude_code", fake)` a `("pi", fake)`.
6. Uložit `signal.getsignal(SIGINT/SIGTERM)` a ve `finally` je obnovit (`session.ensure`
   instaluje handlery vázané na běh).
7. Vrátit dataclass `EngineEnv(cfg, script, fake, repo, db_path)`.

Pomocníci (v `engine_fakes.py` nebo conftest): `start(env, adw_id="t0000001") -> Run` =
`session.ensure(env.cfg, adw_id)`; `rows(db, sql, *args)` = nové `sqlite3.connect`, `fetchall`;
`agent_phase(run, owner, *, retries=0, gates=(), output_type=GenericOutput, prompt="do it")` –
otevře `run.phase(PhaseParams(name=owner, kind="agent", owner=owner, description="Run the
<owner> agent for the test", retries=retries))` a zavolá `ph.call(AgentCall(output_type=…,
prompt=…, gates=list(gates)))`. Pozor: `PhaseParams` validuje `description` (nesmí opakovat
jméno) – použít popis jako výše.

#### 4c. `test_import.py`

- V podprocesu `[sys.executable, "-c", code]` s `cwd=tmp_path` (ne v repu) importovat
  `aifactory.engine` a moduly `runner, agents, session, tracer, permissions, gates, data_types,
  chain, changes, quality, cli, models, console, prompts, utils, git_helper, roles, agent_cc,
  agent_pi, loader, role_registry`; ověřit, že žádná položka `sys.path` neobsahuje `vendor`
  ani `adw_modules`, `"adw_modules" not in sys.modules`, a `runner.__file__` leží v
  `Path(aifactory.__file__).parent / "engine"`. Exit 0.
- `loader.load_engine_module("runner") is aifactory.engine.runner`,
  `load_engine_module("")` je balíček `aifactory.engine`.

#### 4d. `test_role_registry.py`

Přenést `prototype/tests/test_roles.py`: `from haifa_proto import engine` →
`from aifactory.engine import loader as engine`; `from haifa_proto.roles import …` →
`from aifactory.engine.role_registry import …`. Testy porovnávající s vendorovým registrem
(`engine.load_engine_module("roles")`) teď porovnávají s `aifactory.engine.roles` – logika
testu stejná. Všechny testy musí projít.

#### 4e. `test_permissions.py` – rollback zápisů

Každý test: `run = start(env)`, efekt agenta přes `script.on(...)`, `script.add_ok(...)`,
fáze přes `agent_phase` v `pytest.raises(permissions.PermissionBreach)` (kde je breach).

1. **mimo `writes`**: `builder` vytvoří `allowed/a.txt` (povoleno), nový `stray.txt`
   (untracked) a upraví sledovaný `README.md`. Očekávání: `PermissionBreach`, zpráva
   obsahuje `stray.txt` i `README.md`; `stray.txt` neexistuje (smazán), `README.md` má původní
   obsah (git checkout), `allowed/a.txt` zůstal. V DB `events` je `type='error', name='permission_breach'`;
   fáze v `phases` má `status='fail'`; `sessions.status='fail'`.
2. **`protected_files`**: `free` (writes=None) upraví `protected.md` a vytvoří `ok.txt`.
   Breach, `protected.md` vrácen, `ok.txt` zůstal (neomezený agent smí mimo chráněné).
3. **pojmenování odemyká**: `keyholder` upraví `protected.md` → žádný breach, fáze success,
   `events` obsahuje `name='paths_touched'` s `protected.md` v payloadu.
4. **read-only**: `reader` vytvoří `x.txt` → breach, soubor smazán, zpráva obsahuje `read-only`.
5. **předem rozpracované se nevrací**: před během zapsat do `README.md` (necommitnuto),
   `builder` ho upraví znovu → breach, výsledek pro `README.md` je
   `left as-is (was already modified)` a soubor má obsah po úpravě agenta (nic se nezahodilo).
6. **session runtime vždy zapisovatelný**: stačí `permissions.permitted(<data_dir>/x, reader_cfg, cfg)`
   je `True` (jednotkový test `permitted`/`_matches`: `*` nepřekročí `/`, `**` ano, adresářový
   prefix s `/`).

#### 4f. `test_envelope_retry.py` – re-prompt téže session

1. `builder` odpoví `"not json at all"`, pak validním `ok()`. Fáze success.
   `len(script.calls) == 2`, oba `session_id` stejné, druhý prompt začíná
   `"Your response was not valid JSON for the required structure"` a obsahuje seznam polí
   (`status, summary, artifacts, notes_for_next_agent`).
   V `envelopes`: řádek `valid=0, attempt=1`, řádek `valid=1` (attempt 2).
2. JSON se špatným tvarem (`{"status": "maybe"}`) – totéž (validace pydanticem, ne jen parse).
3. JSON v code fence ```` ```json {...} ``` ```` projde napoprvé (1 volání).
4. Vyčerpání: `JSON_FIX_ATTEMPTS + 1` (= 3) nevalidních odpovědí → `RuntimeError` s
   `"never produced valid GenericOutput JSON"`, přesně 3 volání, fáze `fail`.
   Použít `agents.JSON_FIX_ATTEMPTS` místo čísla.

#### 4g. `test_gate_correction.py` – gate correction do téže session

Vlastní gate v testu (typovaná funkce `(envelope, run) -> GateReport`), např. `summary_fixed`:
`GateReport(checks=[GateCheck(item="summary", ok=envelope.summary == "fixed")])`.
Pozor: engine používá `gate.__name__` – musí to být pojmenovaná funkce.

1. `retries=1`, odpovědi `ok(summary="wrong")`, `ok(summary="fixed")`. Fáze success,
   2 volání, stejný `session_id`, druhý prompt začíná
   `"Your previous response failed validation:"` a končí
   `"re-emit ONLY your Report JSON."`. V `gate_results` dva řádky pro gate:
   `attempt=1, passed=0` a `attempt=2, passed=1`; v `events` `gate_fail` a `gate_pass`;
   `phases.attempt == 1`.
2. `retries=0`, odpověď `ok(summary="wrong")` → `agents.GateFailure`, jen 1 volání.
3. Legacy gate vracející `list[str]` (`["bad"]` pak `[]`) funguje stejně (`_as_report`).
4. Nevalidní JSON uvnitř opravného kola se opravuje taky do téže session
   (odpovědi: `ok(summary="wrong")`, `"garbage"`, `ok(summary="fixed")`) → success, 3 volání,
   jedna `session_id`.
5. `status: "fail"` v envelope po průchodu gates → `RuntimeError` s `reported status='fail'`.

#### 4h. `test_sigterm.py` – SIGTERM

Engine sám dětské procesy neposílá `kill` – jeho chování (`session._finalize_when_killed`) je:
handler na SIGTERM/SIGINT zapíše `session_finish(ok=False)`, ten uzavře **všechny** řádky
`processes` běhu (`processes_end_all`, tj. i dítě agenta `kind='agent'`), a vyhodí
`SystemExit(128 + signum)`, takže fáze se zapíše jako `fail`. Test ověřuje přesně toto a nic
nepřidává (jinak změna chování).

1. `run = start(env)`; `fake.during = lambda: os.kill(os.getpid(), signal.SIGTERM)`;
   `script.add_ok("builder")`. `with pytest.raises(SystemExit) as exc: agent_phase(run, "builder")`.
   Očekávání: `exc.value.code == 128 + signal.SIGTERM`;
   `processes`: řádek `kind='adw'` (pid = `os.getpid()`) a řádek `kind='agent', name='builder'`
   (pid falešného dítěte) – oba mají `ended_at IS NOT NULL`;
   `sessions.status == 'fail'`; fáze `status='fail'`, `error` neprázdný nebo `events` obsahuje
   `type='error'` pro fázi a `phase_end` s `{"status": "fail"}`.
   (Pozor: `on_exit` se kvůli výjimce nezavolá – řádek dítěte uzavírá právě handler. To je
   jádro testu.)
2. `session.ensure` nainstaluje handler: `signal.getsignal(SIGTERM)` po `start()` není
   původní handler; totéž pro SIGINT (fixture je pak obnoví).

Signál do vlastního procesu je v pytest bezpečný, protože handler je nainstalovaný a test běží
v hlavním vlákně; fixture handlery vždy obnoví.

#### 4i. `test_trace.py` – fáze, události, `run.finish`

1. **kódová fáze**: `with run.phase(PhaseParams(name="lint", kind="code", owner="git",
   description="Run a deterministic step for the test")) as ph: ph.log(note="x")`.
   `phases`: 1 řádek `status='success'`, `seq=1`, `phase_id == f"{adw_id}_01_lint"`, `ended_at`
   vyplněný. `events` pro fázi v pořadí: `phase_start`, `log`, `phase_end` (payload `status=success`).
   Soubor `data/sessions/<adw_id>/events.jsonl` existuje a má ≥ 3 řádky.
2. **agentní fáze**: `agent_start`, `handoff`, `agent_end`, `phase_end`; `envelopes` s
   `valid=1`; `agent_sessions` řádek pro `builder`;
   `data/sessions/<adw_id>/builder/envelope.json` a `prompts/user.md` existují;
   `agent_map.json` obsahuje `builder` se `session_id`.
3. **výjimka ve fázi**: `raise ValueError("boom")` uvnitř `run.phase` → výjimka propadne,
   fáze `fail`, `error` obsahuje `boom`, `events` `error` + `phase_end` fail, `sessions.status='fail'`.
4. **`finish(accepted=True)`** po úspěšné fázi → vrací `0`, `sessions.status='success'`,
   `ended_at` vyplněný.
5. **`finish(accepted=False, reason="suite red")`** po úspěšné fázi → vrací `1`,
   `sessions.status='fail'`, `events` má `type='error', name='not_accepted'` s payloadem
   `{"reason": "suite red"}`.
6. **`finish(accepted=False)` bez důvodu** → reason = výchozí text
   `"the run's acceptance criterion was not met"`.
7. **`finish()` bez fází** → `1`, `status='fail'` (bez `not_accepted` eventu).
8. **`finish(accepted=True)` s neúspěšnou fází** (fáze vyhodila, výjimku zachytit v testu) → `1`,
   bez `not_accepted` eventu.
9. **připojený běh pokračuje v sekvenci**: dvakrát `session.ensure(cfg, "same-id")`, v každém
   jedna fáze → druhá má `seq=2` a jiné `phase_id` (`max_phase_seq`).
10. `add_usage` – falešný harness vrátí `AgentResult(tokens=…, cost=…)`? Jen pokud jde snadno
    (volitelné pole ve `Script`); jinak vynechat.

Konzole `rich` píše na stdout – v testech nevadí (pytest zachytává).

### 5. Neměnit

- `vendor/`, `prototype/`, `adws/`, `justfile`, kořenový `CLAUDE.md`.
- `aifactory/src/aifactory/cli.py` – engine se do CLI nenapojuje (to jsou další úkoly).

## Ověření

```bash
# 1) logika beze změny: přenesené moduly jsou identické s vendorem (musí vypsat nic, exit 0)
diff -r -x __pycache__ -x loader.py -x role_registry.py -x defaults \
  vendor/sssf/templates/adws/adw_modules aifactory/src/aifactory/engine
diff prototype/src/haifa_proto/defaults/roles.yaml aifactory/src/aifactory/engine/defaults/roles.yaml

# 2) žádná závislost na vendoru / sys.path v balíčku (očekávej exit 1 = nic nenalezeno)
grep -rn "sys.path\|vendor\|haifa_proto" aifactory/src/aifactory/engine/loader.py aifactory/src/aifactory/engine/role_registry.py

# 3) brány
just test
just typecheck
just lint

# 4) vendor a prototyp nedotčené
git status --porcelain vendor prototype   # prázdné
```

Rozhoduje exit status příkazů, ne slova ve výstupu (engine obsahuje texty jako „error“).

## Rizika a poznámky

- Pokud by mypy i přes `untyped_calls_exclude` hlásil v testech `no-any-return`/`misc` kvůli
  `Any` z enginu, řešit v testech (anotace, `assert isinstance`), NE úpravou enginu a NE
  plošným vypnutím strict pro `tests`.
- `utils.py` při importu volá `load_dotenv()` – převzaté chování, nechat.
- Testy s gitem: temp repo s `user.email/name` nastaveným lokálně; `data_dir` mimo repo, aby
  runtime nebyl ve snapshotu.
- `tests/engine/conftest.py` je zatím jediný `conftest.py`; pokud by mypy hlásil duplicitní
  jména modulů (`engine_fakes`, `conftest`), přidat do `[tool.mypy]` `explicit_package_bases`
  nebo přejmenovat helper – ne měnit engine.
