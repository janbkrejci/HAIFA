# Plán: interpret YAML workflow v `aifactory` + nová sémantika `until` (úkol 2.7)

## Cíl

Přenést interpret YAML workflow z prototypu (`prototype/src/haifa_proto/workflow.py`) do balíčku
`aifactory.workflow`, napojit ho na už přenesený registr rolí (`aifactory.engine.role_registry`,
čte `.factory/roles.yaml`) a na harness vrstvu z 2.3 (`aifactory.harness`, `aifactory.harness.override`),
přidat CLI `factory workflow check <soubor> [--json]` a změnit sémantiku `until` tak, aby po
posledním zamítnutí/neúspěchu v posledním kole už neběžel opravný krok.

## Kontext, který už existuje (neimplementovat znovu)

- `aifactory/src/aifactory/engine/role_registry.py` — hotový port `prototype/.../roles.py`:
  `RoleRegistry`, `RoleDef`, `CodeStepDef`, `Issue`, `RolesError`, `RAN_FIELD="ran"`,
  `CODE_ACTIONS` (vč. `command`), `VERIFY_ACTIONS`, `check_description`, `load_roles`, `parse_roles`,
  `RoleRegistry.result_fields(name)` (pro `command` vrací pole `VerifyOutput` = `passed`, `failures`, … + `ran`).
- `aifactory/src/aifactory/engine/defaults/roles.yaml` — balený registr, obsahuje i `command`.
- `aifactory/src/aifactory/config/loader.py` — `load_config` / `load_worktree_config(root)` vrací
  `FactoryConfig` s `.roles: RoleRegistry` (z `.factory/roles.yaml`, jinak balený default) a
  `.agents: SSSFConfig` (z `.factory/agents.yaml`, harness explicitní, `prompt_engineering` doplněný).
  `ConfigError.issues` jsou `ConfigIssue` s `to_dict()`.
- `aifactory/src/aifactory/harness/__init__.py` — `HARNESSES` (`claude`, `codex`, `pi`), `ALIASES`,
  `canonical(name)` (ValueError u neznámého), `install()` (idempotentní, `setdefault` — nepřepíše fake).
- `aifactory/src/aifactory/harness/override.py` — `StepOverride(harness, model, thinking)`,
  `THINKING_LEVELS`, `check_override(agent, override) -> list[str]` (nic nespouští),
  `step_override(cfg, agent_name, override)` context manager (dočasně nahradí agenta v `cfg.agents`,
  vždy vrátí původního; neplatný override → `HarnessConfigError`).
- Engine (`aifactory.engine.*`) je importovatelný přímo: `data_types` (`PhaseParams`, `AgentCall`,
  `QualityCheckSpec`, `QualityResult`, `VerifyOutput`, `ChangeCapture`, `ChangesOutput`),
  `quality` (`run_tests`, `run_quality`, `_run(spec, run)`, `as_envelope(result, what)`),
  `changes` (`capture`, `as_envelope`), `git_helper` (`commit_all`, `rev`, `is_repo`),
  `session.ensure(cfg, adw_id)`, `Run.phase(params)`, `Run.finish(accepted=, reason=)`, `run.cfg` je
  ten samý objekt, který dostal `session.ensure`.
- `cli.py` už má `("workflow", "validate and inspect workflows")` v `SUBCOMMANDS`, ale bez podpříkazů
  (`main` vrací „not implemented yet“).

Engine soubory vyjmenované v `pyproject.toml` (`extend-exclude` / mypy overrides) se **nemění**.
`vendor/` a `prototype/` se **nemění**.

## Rozhodnutí o sémantice `until` (jádro úkolu)

Prototyp vyhodnocoval `until` po každém provedeném kroku těla, ale v posledním kole doběhlo celé tělo,
takže po posledním zamítnutí review běžel navíc `revise_2` (známý rozdíl v `docs/prototype-report.md`, D7).
Nová pravidla pro `repeat`:

1. `until` se vyhodnocuje **po každém kroku těla, který proběhl** (`ran` = jeho `when` platil). Jakmile
   platí, celá smyčka okamžitě končí (zbytek těla ani další kola neběží).
2. **Poslední kolo končí u kontrolního kroku.** Při parsování se pro každý `repeat` s `until` spočítá
   `until_tail: int | None` = index posledního prvku těla (na úrovni těla), jehož podstrom (přes `walk`)
   obsahuje list, jehož `key` je odkazován v `until` (`refs(until.node)` → `ref.step`). V kole `i == max`
   smyčka po dokončení prvku s indexem `until_tail` skončí, i když `until` neplatí — kroky za ním by
   opravovaly práci, kterou už nic neověří.
3. Když `until` chybí nebo neodkazuje na žádný krok v těle (`until_tail is None`), poslední kolo proběhne celé.
4. Když `until` platí už před smyčkou (výsledek kroku mimo smyčku), první krok těla stejně proběhne —
   kontrola je až po kroku (stejně jako v prototypu).

Důsledky (musí sedět s testy):
- `repeat {max: 3, until: test.passed}` `[test, fix]`, testy F,T → `test_1, fix_1, test_2`.
- testy T → `test_1` (fix nikdy).
- testy F,F,F (max dojde) → `test_1, fix_1, test_2, fix_2, test_3` — **žádné `fix_3`**.
- `repeat {max: 2, until: review.approved}` `[review, revise]`, review rej,appr → `review_1, revise_1, review_2`.
- review rej,rej (max dojde) → `review_1, revise_1, review_2` — **žádné `revise_2`**.

Tohle je vědomá odchylka od Python `adw_simple_sdlc.py` u test/fix smyčky (ten po posledním neúspěšném
testu ještě spustí `fix_3`); zapsat do docstringu `loop` a modulu.

## Soubory

### Nové: `aifactory/src/aifactory/workflow/`

Port `prototype/src/haifa_proto/workflow.py` rozdělený do modulů. Kód přebírat co nejvěrněji, jen
změnit importy (`haifa_proto.*` → `aifactory.*`, `engine.load_engine_module("x")` → přímý import
`from aifactory.engine import x`) a úpravy popsané níže. Vše typované pro `mypy --strict`, ruff čisté
(řádek ≤ 100).

1. `__init__.py` — re-export veřejného API: `WorkflowError`, `ConditionError`, `Condition`,
   `parse_condition`, `evaluate`, `truthy`, `refs`, `Workflow`, `RoleStep`, `CodeStep`, `Repeat`,
   `Step`, `walk`, `parse_workflow`, `load_workflow`, `outline`, `CheckResult`, `check_workflow`,
   `check_agents`, `CodeRunner`, `EngineCodeRunner`, `WorkflowRun`, `StepRecord`, `preflight`,
   `run_workflow`. `__all__` explicitně.

2. `conditions.py` — řádky 88–313 prototypu beze změny logiky: `ConditionError`, uzly `Ref/Lit/Not/And/Or/Cmp`,
   tokenizer (regex), rekurzivní sestupný parser `_CondParser`, `Condition`, `parse_condition`, `refs`,
   `evaluate`, `truthy`. `RAN_FIELD` importovat z `aifactory.engine.role_registry`.
   **Žádné `eval`/`exec`/`compile`**; modulový docstring to říká.

3. `model.py` — `WorkflowError(issues)` (stejný tvar jako prototyp), `DEFAULT_COMMAND_TIMEOUT = 600`,
   dataclassy `RoleStep`, `CodeStep`, `Repeat`, `Workflow`, alias `Step`, `walk`.
   - `RoleStep`: jako prototyp (`name, role: RoleDef, phase_id, description, path, harness, model,
     thinking, when, inputs`, property `key`), navíc property `override -> StepOverride`.
   - `Repeat`: přidat pole `until_tail: int | None = None`.
   - Ostatní beze změny.

4. `parse.py` — `_Parser` z prototypu (řádky 384–732) + `outline` (735–774). Úpravy:
   - `HARNESS_NAMES` = `(*HARNESSES, *ALIASES)` z `aifactory.harness`; v `override("harness")` použít
     `canonical(value)` (chytit `ValueError` → issue `unknown_harness`) a uložit kanonické jméno.
   - `THINKING_LEVELS` importovat z `aifactory.harness.override`.
   - `repeat()`: po sestavení těla spočítat `until_tail` (helper `_until_tail(until, steps)`:
     `keys = {r.step for r in refs(until.node)}`; projít `enumerate(steps)`; pro `Repeat` prvek brát
     `{leaf.key for leaf in walk(prvek.steps)}`, jinak `{prvek.key}`; vrátit poslední index s průnikem, jinak None).
   - `load_workflow(path, roles: RoleRegistry | None = None)` — default `load_roles()` (balený).
   - `parse_workflow(data, roles, source=None)` beze změny.

5. `check.py` — statická validace pro CLI a preflight:
   - `check_agents(workflow, cfg: SSSFConfig) -> list[Issue]`: pro každý unikátní
     `(role.agent, harness, model, thinking)` z `walk(workflow.steps)` (jen `RoleStep`):
     agent chybí v `cfg.agents` → `Issue("unknown_agent", f"step {name!r} needs agent {agent!r}, which is not in the roster (agents: …)", step.path)`;
     jinak `check_override(agent, step.override)` → každý problém jako `Issue("invalid_agent", problem, step.path)`.
   - `CheckResult` dataclass: `ok, path, workflow, issues, outline, roles_source: str, agents_source: str | None, warnings: list[str]`,
     `to_json()` → `{"ok","path","workflow","errors":[i.to_dict()],"steps":outline,"roles":roles_source,"agents":agents_source,"warnings":[…]}`.
   - `check_workflow(path, roles, cfg=None, *, roles_source, agents_source) -> CheckResult`:
     neexistující soubor → `missing_file`; `load_workflow` → `WorkflowError.issues`; pokud parse prošel a
     `cfg` není None → přidat `check_agents`; když `cfg is None` → warning „agents not checked: no .factory/agents.yaml“.
     Nic se nespouští.

6. `interpreter.py` — řádky 815–1153 prototypu s úpravami:
   - `CodeRunner` Protocol a `EngineCodeRunner` beze změny chování (přímé importy enginu).
     `command`: `QualityCheckSpec(name=step.key, area="backend", operation="build", argv=list(step.argv), timeout_seconds=step.timeout)`,
     `quality._run(spec, run)`, `QualityResult(passed=check.passed, …)` — `passed` = exit kód 0
     (timeout → 124, chybějící binárka → 127, obojí `passed=False`).
   - **Odstranit** `apply_override`/`restore`/`ensure_harnesses` z prototypu. Místo nich:
     - `preflight(workflow, cfg)`: `aifactory.harness.install()`, pak `issues = check_agents(workflow, cfg)`;
       pro každou unikátní kombinaci navíc `agents.validate(probe, [agent])` na `cfg.model_copy(deep=True)`
       s nahrazeným agentem přes `effective_agent` (SystemExit → `invalid_agent`). Issues → `WorkflowError`.
     - `_Interpreter.role()`: `with step_override(self.run.cfg, role.agent, step.override) as agent:` a uvnitř
       `run.phase(...)`, `ph.log(harness=agent.coding_agent, model=agent.model, thinking=agent.thinking)`,
       `StepRecord`, `ph.call(AgentCall(...))`. Po bloku `store(step.key, envelope)`.
   - `loop()` s novou sémantikou (viz výše):
     ```python
     def loop(self, step: Repeat, suffix: tuple[int, ...]) -> None:
         for i in range(1, step.max + 1):
             last = i == step.max
             for index, inner in enumerate(step.steps):
                 ran = self.dispatch(inner, (*suffix, i))
                 if ran and step.until is not None and truthy(step.until, self.results):
                     return
                 if last and step.until_tail is not None and index == step.until_tail:
                     return
     ```
   - Zbytek (`phase_name`, `params`, `store`, `previous`, `commit_message`, `dispatch`, `code_step`,
     `run_workflow`, `WorkflowRun`, `StepRecord`, `REQUEST_DESCRIPTION`) beze změny.
     `commit_message` používá prefix `sssf({adw_id}):` jako prototyp — ponechat.

### Změny: `aifactory/src/aifactory/cli.py`

- V `build_parser` pro `name == "workflow"` volat `_add_workflow_commands(child)`:
  `check` s argumentem `file` (`Path`), `--json`, `--roles PATH` (registr rolí místo `.factory/roles.yaml`),
  `--agents PATH` (roster místo `.factory/agents.yaml`, načte se `aifactory.harness.config.load_config`).
- `_workflow(args)`: bez podpříkazu vytisknout help, exit 0. `check`:
  1. Zdroj registru a agentů (vždy **pracovní strom**, protože check slouží při editaci):
     - najít repo root z `Path.cwd()` (`aifactory.config.repo_root`; `ConfigError` = nejsme v repu → brát jako „bez .factory“).
     - Když existuje `<root>/.factory/config.yaml` a nejsou dané `--roles`/`--agents`: `load_worktree_config(root)`
       → `roles = cfg.roles`, `agents = cfg.agents`, zdroje `".factory/roles.yaml"` (nebo `"packaged defaults"`,
       když soubor neexistuje) a `".factory/agents.yaml"`.
     - Jinak: `--roles` → `load_roles(Path)`, jinak balený default; `--agents` → `harness.config.load_config`,
       jinak `None` (agenti se nekontrolují, warning).
     - `ConfigError` / `RolesError` / `HarnessConfigError` při načtení → exit **2**; JSON
       `{"ok": false, "error": str(exc), "issues": [...]}`, text na stderr `factory workflow check: …`.
  2. `check_workflow(...)`; JSON: `print(json.dumps(result.to_json(), indent=2))`. Text: při OK
     `OK: <name> (<n> steps)`; jinak řádek `"{file}:{issue.path}: {issue.code}: {issue.message}"` pro každou
     chybu a `"<n> error(s)"`; warnings na stderr s prefixem `warning:`.
  3. Exit 0 = ok, 1 = chyby workflow.
- V `main` přidat `if command == "workflow": return _workflow(args)`.

### Nové testy: `aifactory/tests/workflow/`

Testy nevolají model ani skutečný CLI harness. Jména souborů musí být v celém `tests/` unikátní
(pytest `prepend` import mode, testovací adresáře nejsou balíčky) — proto prefix `workflow`.

1. `workflow_fakes.py` — port `prototype/tests/workflow_fakes.py`:
   `Script`, `Call`, `FakeHarness(name, script)` (vrací `AgentResult(text=json.dumps(envelope))`,
   agent se pozná z `Path(request.session_dir).parent.name`), `FakeCodeRunner(test_results: list[bool])`
   (test výsledky ze skriptu, `commits`, `commands`), `ok(**fields)`, `make_engine_env(tmp_path, monkeypatch)`:
   git repo s jedním commitem (bez `repo_templates`), prompty s `{{prompt}}` a `PREV<<{{previous_envelope}}>>PREV`,
   roster `planner, builder, reviewer, documenter` s `harness: claude`, `model: sonnet`, `thinking: medium`,
   `data_dir`/`observability.db` do `tmp_path`; načíst přes `aifactory.harness.config.load_config`;
   `agents = aifactory.harness.install()`; nejdřív `monkeypatch.setattr(harness.load(name), "run", _no_real_harness(name))`
   pro claude/codex/pi, pak `monkeypatch.setitem(agents.INTERFACES, name, fake)` pro claude, codex, pi a `claude_code`.
   Uložit/obnovit SIGINT/SIGTERM handlery (jako `tests/engine/conftest.py`). `monkeypatch.chdir(repo)`,
   `monkeypatch.setenv("ENGINEER_NAME", "tester")`.
2. `conftest.py` — fixture `workflow_env` nad `make_engine_env`.
3. `test_workflow_conditions.py` — port `prototype/tests/test_conditions.py` (parser, priority, `not`,
   porovnání, `ran` u neproběhlého kroku = False, chyby syntaxe, že `__import__('os')` / `1+1` / `a.b.c` neprojdou).
4. `test_workflow_parse.py` — port `prototype/tests/test_workflow_load.py` + nové:
   - `until_tail`: `[test, fix]` s `until: test.passed` → 0; `[review, revise]` s `review.approved` → 0;
     `until` odkazující krok mimo tělo → `None`; vnořený repeat v těle obsahující odkazovaný krok → jeho index.
   - `command` bez `id`/`argv` → `missing_id`/`missing_argv`; `until: tests_cmd.passed` na command s `id: tests_cmd` projde.
   - harness alias `claude_code` se uloží jako `claude`; neznámý harness → `unknown_harness`.
   - registr z vlastního YAML (`parse_roles`) — neznámá role v workflow → `unknown_step`.
5. `test_workflow_loops.py` — běh přes `run_workflow(..., code=FakeCodeRunner(...))`, kontrola
   pořadí fází (`[p for p, _, _ in run.phases]` nebo `records`), `accepted`, `exit_code`, `script.calls`:
   - test smyčka: F,T → `test_1, fix_1, test_2`, accept ok.
   - test smyčka: T → `test_1`, `fix` se nevolá (builder dostal jen build).
   - test smyčka: F,F,F (max 3 dojde) → `test_1, fix_1, test_2, fix_2, test_3`, žádné `fix_3`, `accepted is False`, `exit_code != 0`.
   - review smyčka: rej, appr → `review_1, revise_1, review_2`; následný `test: {when: revise.ran}` proběhne.
   - review smyčka: rej, rej (max 2 dojde) → `review_1, revise_1, review_2`, žádné `revise_2`;
     `commit: {when: test.passed and review.approved}` neproběhne; `accepted is False`.
   - `when` na kroku: bez revize `test: {when: revise.ran}` neproběhne; `when` na celém `repeat`.
   - `until` bez odkazu na tělo (např. `until: plan.approved`… použít platné pole) → poslední kolo projde celé.
   - Obálky: `fix` dostane jako `previous` VerifyOutput testu (PREV marker), `revise` dostane ReviewOutput.
   Workflow psát jako YAML stringy → `parse_workflow(yaml.safe_load(...), load_roles())`.
   Zamítnuté review: `ok(approved=False, verdict=…)` — přesná pole zkontrolovat v `data_types.ReviewOutput`
   a gatu `verdict_consistent` (envelope musí gate projít, jinak retry sežere skript). Artefakty
   pro `artifacts_exist`: buď prázdný seznam, nebo soubor vytvořený přes `script.on(...)`.
6. `test_workflow_command.py`:
   - s `FakeCodeRunner`: `command` se zavolá s argv z YAML, výsledek čitelný přes `id`.
   - se skutečným `EngineCodeRunner().command(run, step)` a `run = session.ensure(cfg, id)` uvnitř `run.phase(...)`:
     argv `[sys.executable, "-c", "raise SystemExit(0)"]` → `passed True`; `SystemExit(3)` → `passed False`,
     `returncode == 3`; neexistující binárka → `passed False`, `returncode == 127`.
   - celý workflow `repeat {max: 2, until: suite.passed}` `[command{id: suite, argv: […]}, fix]` s reálným
     `EngineCodeRunner` jen pro command (subclass `FakeCodeRunner`, která deleguje `command` na `EngineCodeRunner`).
7. `test_workflow_harness_mix.py` — port `prototype/tests/test_workflow_harness_mix.py`: override harness/model/thinking
   na kroku dorazí do správného fake harnessu, agenti se po běhu vrátí do původního stavu (`cfg.agents` beze změny),
   preflight odmítne model (`fake.reject_models = True`) dřív, než cokoli běží, a neznámého agenta v rosteru.
8. `test_workflow_cli.py` — `cli.main([...])` + `capsys`:
   - v `tmp_path` repo z `tests/config/config_repo.make_repo` (import jako v `tests/config` — pokud není
     na `sys.path`, zkopírovat potřebné minimum do `workflow_fakes.py`; nepřidávat `__init__.py`):
     platný workflow s rolemi `plan`, `build` → exit 0, `OK: …`; `--json` má `ok`, `steps`, `roles`, `agents`.
   - workflow s `review` (agent `reviewer` v rosteru chybí) → exit 1, `unknown_agent`.
   - více chyb najednou (neznámý krok, `until: test.approved`, repeat bez `max`) → všechny v `errors`.
   - chybějící soubor → exit 1 `missing_file`; mimo repo bez `.factory` → balený registr + warning, exit 0;
     `--roles` s neplatným YAML → exit 2.
   - `factory workflow` bez podpříkazu → help, exit 0.

Harness `pi` v CLI testech nepoužívat (jeho `resolve_model` čte katalog); jen `claude`.

## Postup

1. Vytvořit `aifactory/src/aifactory/workflow/` (conditions → model → parse → check → interpreter → `__init__`).
2. CLI `workflow check`.
3. Testy (fakes, conftest, soubory výše).
4. Ověřit.

## Ověření

Z kořene repa:

```bash
just test          # celé aifactory testy, včetně tests/workflow
just typecheck     # mypy --strict nad src i tests
just lint          # ruff
cd aifactory && uv run factory workflow check ../prototype/src/haifa_proto/defaults/workflows/simple-sdlc.yaml --json
```

Poslední příkaz (mimo `.factory/` → balený registr, warning o agentech) musí skončit exit 0 a vypsat
kroky včetně repeat. Hodnotit podle exit statusu. `git diff --stat -- vendor prototype` musí být prázdný.

## Mimo rozsah

YAML verze stávajících ADW do `.factory/workflows` (2.8), `factory workflow run` / běh ve worktree (2.9),
krok `pr` (2.12), napojení `test` na `test_command` z `.factory/config.yaml` (2.9), validace
`FactoryConfig.workflows` při `config show`.
