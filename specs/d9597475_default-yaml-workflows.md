# Plán: výchozí YAML workflow balíčku `aifactory` (plan, plan-build, plan-build-test, simple-sdlc, document, scout)

## Cíl

Přenést šest YAML workflow z `prototype/src/haifa_proto/defaults/workflows/` do
`aifactory/src/aifactory/defaults/workflows/`, zpřístupnit adresář jako konstantu
`DEFAULT_WORKFLOWS_DIR` v `aifactory.workflow` a otestovat je: `factory workflow check`
projde pro všech šest workflow a běh s falešným harnessem dá stejné pořadí fází jako Python ADW
stejného jména (`adws/adw_<name>.py`). Smyčky se chovají podle 2.7: v posledním kole smyčka
skončí u kontrolního kroku, takže po posledním zamítnutí review se `revise_2` nespustí a po
posledním neúspěšném testu se nespustí `fix_3`.

Mimo rozsah: workflow `resolve`, typ workflow `script`. `vendor/` a `prototype/` se **nemění**.
Soubory enginu vyjmenované v `pyproject.toml` se nemění. Interpret (`aifactory/workflow/*`)
až na jednu konstantu neměnit — sémantika `until`/`until_tail` je už hotová z 2.7.

## Co už existuje (neimplementovat znovu)

- `aifactory.workflow`: `load_workflow(path, roles=None)` (výchozí je balený registr rolí), `check_workflow`,
  `run_workflow(workflow, prompt, cfg, *, code=None)` → `WorkflowRun` s `.phases` =
  `[(name, kind, owner), …]` včetně úvodní fáze `("request", "engineer", <engineer>)`, `.exit_code`, `.accepted`.
- `Repeat.until_tail` + `_Interpreter.loop` (2.7): v posledním kole skončí po kroku, který čte `until`.
- CLI `factory workflow check FILE [--json] [--roles PATH] [--agents PATH]` (`aifactory/cli.py`):
  exit 0 = OK, 1 = problémy ve workflow, 2 = nejde načíst registr/roster. Bez `.factory/` a bez
  `--agents` se agenti nekontrolují (jen warning).
- `aifactory/tests/workflow/workflow_fakes.py`: `make_engine_env` / fixture `workflow_env`
  (import `workflow_env_fixture` do testového modulu, `# noqa: F401`), `Script`, `FakeHarness`,
  `FakeCodeRunner(test_results)` (`.commits` = zprávy commitů), `ok(**fields)`. Roster zapisuje do
  `tmp_path / "agents.yaml"` (tj. `env.repo.parent / "agents.yaml"`) pro agenty v `AGENTS`.
- Balený registr `aifactory/src/aifactory/engine/defaults/roles.yaml` je shodný s prototypovým;
  role `scout` má `agent: scout`.

## Změny

### 1. Nové soubory `aifactory/src/aifactory/defaults/workflows/*.yaml`

Adresář `aifactory/src/aifactory/defaults/` je čistě datový (bez `__init__.py`; hatchling
zabalí i ne-Python soubory uvnitř `src/aifactory`). Zkopírovat šest souborů z prototypu
(`cp prototype/src/haifa_proto/defaults/workflows/*.yaml aifactory/src/aifactory/defaults/workflows/`)
a upravit jen komentáře:

- `plan.yaml`, `plan-build.yaml`, `document.yaml`, `scout.yaml` — beze změny obsahu.
- `plan-build-test.yaml` — obsah beze změny; do hlavičkového komentáře doplnit řádek:
  `# Loop (2.7): the last round ends at the test step, so a last red suite is not followed by fix_3.`
  (vědomá odchylka od `adw_plan_build_test.py`, který `fix_3` ještě spustí; výsledek je stejný — bez commitu, exit 1).
- `simple-sdlc.yaml` — obsah (kroky, `when`, `accept`, `input`, popisy) beze změny. Odstavec
  „Known difference: … still runs revise_2 …“ nahradit:
  ```yaml
  # Loops (2.7): `until` is checked after every body step, and the last round ends
  # at the step `until` reads. A last rejection is therefore not followed by
  # revise_2 (as in the Python version), and a last red suite not by fix_3
  # (the Python version still runs fix_3; the outcome is the same: nothing committed).
  ```
- V komentářích prototypu je cesta `vendor/sssf/templates/adws/adw_simple_sdlc.py` — ponechat.

### 2. `aifactory/src/aifactory/workflow/parse.py` (a re-export)

- Přidat `from importlib import resources` a konstantu vedle importů:
  ```python
  DEFAULT_WORKFLOWS_DIR = Path(str(resources.files("aifactory") / "defaults" / "workflows"))
  """The packaged workflows (one per ported Python ADW)."""
  ```
  (stejný vzor jako `DEFAULTS_DIR` v `aifactory/engine/role_registry.py`).
- `aifactory/src/aifactory/workflow/__init__.py`: importovat a přidat `"DEFAULT_WORKFLOWS_DIR"`
  do `__all__` (seřazeno — velká písmena před `CheckResult`, ruff `RUF022` není zapnutý, ale držet abecedu).

### 3. `aifactory/tests/workflow/workflow_fakes.py`

- `AGENTS = ("planner", "builder", "reviewer", "documenter", "scout")` — workflow `scout` potřebuje
  agenta `scout` v rosteru (jinak `preflight` → `unknown_agent`). Ověřit, že žádný stávající test
  nepočítá s přesným rozsahem rosteru (grep `AGENTS`/`len(` v `tests/workflow`); stávající testy mají projít beze změny.

### 4. Nový test `aifactory/tests/workflow/test_default_workflows.py` — načtení a `check`

```python
DEFAULTS = sorted(DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))
NAMES = {"plan", "plan-build", "plan-build-test", "simple-sdlc", "document", "scout"}
```
Testy:
1. `test_every_ported_adw_has_a_workflow`: `{p.stem for p in DEFAULTS} == NAMES`.
2. `test_default_workflows_load` (parametrizovat přes `DEFAULTS`, `ids=stem`): `load_workflow(path)`,
   `workflow.name == path.stem`, `workflow.steps` neprázdné.
3. `test_default_workflow_passes_check` (parametrizovaný, fixture `workflow_env` kvůli rosteru s
   promptovými soubory): `monkeypatch.chdir(tmp_path)` do adresáře, který **není** git repo s
   `.factory/config.yaml` (např. nový `tmp_path / "elsewhere"`), aby CLI bralo `--agents`;
   `main(["workflow", "check", str(path), "--json", "--agents", str(workflow_env.repo.parent / "agents.yaml")]) == 0`,
   JSON `ok is True`, `errors == []`, `agents` = cesta k rosteru, `warnings == []`.
   (Pozn.: `_workflow_sources` s `--agents` nečte pracovní strom, takže chdir je jen pojistka.)
4. `test_simple_sdlc_structure`: port z `prototype/tests/test_workflow_load.py::test_simple_sdlc_structure`
   (dvě smyčky `max` [3, 2], `until` zdroje, `review.inputs == ("build","fix","revise")`,
   `steps[5]` je `CodeStep` s `(key, phase_id) == ("test", "retest")`, `accept` není None) a navíc
   `[loop.until_tail for loop in loops] == [0, 0]`.
5. `test_plan_build_test_structure`: smyčka `max == 3`, `until_tail == 0`, `accept.source == "test.passed"`.

### 5. Nový test `aifactory/tests/workflow/test_default_workflows_run.py` — pořadí fází

Společné pomocníky:
```python
def _run(env, name, tests, prompt="add a /health endpoint") -> tuple[WorkflowRun, FakeCodeRunner]:
    code = FakeCodeRunner(tests)
    result = run_workflow(load_workflow(DEFAULT_WORKFLOWS_DIR / f"{name}.yaml"), prompt, env.cfg, code=code)
    return result, code

def _phases(result) -> list[tuple[str, ...]]:
    """(name, kind, owner), except the engineer's name, which depends on the machine."""
    return [p[:2] if p[1] == "engineer" else p for p in result.phases]
```
Konstanty: `REQUEST = ("request", "engineer")`, `PLAN_PHASE = ("plan","agent","planner")`,
`BUILD_PHASE = ("build","agent","builder")`, `test_(i) = (f"test_{i}","code","quality")`,
`fix_(i) = (f"fix_{i}","agent","builder")`, `review_(i)`, `revise_(i)`,
`COMMIT = ("commit","code","git")`, … Envelopy jako v prototypovém testu:
`PLAN = ok(summary="planned", commit_message="Add the plan")`, `BUILD`, `FIX`, `REVISE`,
`APPROVE = ok(summary="looks right", approved=True)`,
`REJECT = ok(summary="missing X", approved=False, blocking=["missing X"])`,
`DOCUMENT = ok(summary="documented", commit_message="Document the feature")`,
`SCOUT = ok(summary="found it")`. Pořadí fází odvozeno z `Phases:` docstringů a smyček v `adws/adw_*.py`.

Scénáře (každý ověřuje `_phases`, `(exit_code, accepted)` a kde to dává smysl `code.commits`,
`code.test_results == []` a že skript nemá nevyčerpané envelopy):

- **plan**: `[REQUEST, PLAN_PHASE]`, exit 0, `code.commits == []`.
- **scout**: `[REQUEST, ("scout","agent","scout")]`, exit 0, žádné commity.
- **plan-build**: `[REQUEST, PLAN_PHASE, BUILD_PHASE, COMMIT]`, `commits == ["Build the feature"]`.
- **document**: `[REQUEST, ("changes","code","git"), ("document","agent","documenter")]`, exit 0.
- **plan-build-test**:
  - testy `[True]` → `[REQUEST, PLAN, BUILD, test_1, COMMIT]`, `commits == ["Build the feature"]`, accepted.
  - `[False, True]` → `[…, test_1, fix_1, test_2, COMMIT]`, `commits == ["Fix the failing test"]`
    (commit bere zprávu posledního builderu; ověřit v interpretu `commit_message`/`previous` — pokud
    bere jinou, test přizpůsobit skutečnému chování 1:1 s Python ADW, který používá `previous.commit_message` posledního build/fix).
  - `[False, False, False]` → `[…, test_1, fix_1, test_2, fix_2, test_3]` — **bez `fix_3` a bez commitu**,
    `(1, False)`, `commits == []`; builder má naskriptováno jen `BUILD, FIX, FIX`.
- **simple-sdlc** (port `prototype/tests/test_workflow_simple_sdlc.py`, fixture přejmenovat na `workflow_env`):
  `HEAD = [REQUEST, PLAN, ("commit_plan","code","git"), BUILD]`,
  `TAIL = [("commit_build","code","git"), ("changes","code","git"), ("document","agent","documenter"), ("commit_docs","code","git")]`.
  - vše projde: `[*HEAD, test_1, review_1, *TAIL]`, commity `["Add the plan","Build the feature","Document the feature"]`,
    všechna volání mají `(harness, model, thinking) == ("claude","sonnet","medium")`.
  - test F,T: `[*HEAD, test_1, fix_1, test_2, review_1, *TAIL]`; `'"passed": false' in calls[2].previous()`;
    `"fixed" in calls[3].previous()` (reviewer čte poslední kód); `commits[1] == "Fix the failing test"`.
  - review rej, appr: `[*HEAD, test_1, review_1, revise_1, review_2, ("retest","code","quality"), *TAIL]`,
    `"missing X"` v previous revize, `"revised"` v previous `review_2`,
    commity `["Add the plan","Close review findings","Document the feature"]`.
  - **review rej, rej (nový, jádro úkolu)**: reviewer `REJECT, REJECT`, builder `BUILD, REVISE`,
    testy `[True]` → `[*HEAD, test_1, review_1, revise_1, review_2]` — **žádné `revise_2`, žádný `retest`**,
    `(1, False)`, `commits == ["Add the plan"]`, builder volán přesně 2× (`[c.agent for c in calls].count("builder") == 2`).
    Shoduje se s `adw_simple_sdlc.py` (`if review.approved or i == MAX_REVISION_LOOPS: break`).
  - testy nikdy neprojdou `[False]*3`: builder `BUILD, FIX, FIX`, reviewer `APPROVE` →
    `[*HEAD, test_1, fix_1, test_2, fix_2, test_3, review_1]` — **bez `fix_3`**, review stále běží
    (jako Python ADW), `(1, False)`, `commits == ["Add the plan"]`. Komentář v testu: vědomá odchylka
    od Python ADW (ten spustí `fix_3`), sémantika 2.7.

Všechny testy typované (`-> None`, parametry `EngineEnv`), ruff čisté, řádky ≤ 100.

## Ověření

Z kořene repa:
1. `for f in aifactory/src/aifactory/defaults/workflows/*.yaml; do (cd aifactory && uv run factory workflow check "../$f") || echo "FAIL $f"; done`
   — každý musí skončit exit 0 (bez rosteru jen warning „agents not checked“; posuzovat podle exit kódu).
2. `just test` (celá sada, včetně nových `tests/workflow/test_default_workflows*.py`).
3. `just typecheck`
4. `just lint` (`ruff check` i `ruff format --check`; nové soubory předem `uv run ruff format`).
5. `git status` — žádná změna v `vendor/` ani `prototype/`.
