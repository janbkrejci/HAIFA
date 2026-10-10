# HAIFA-S05-T02 — Krok `agent:` ve workflow a překryv `roles.yaml`

## Cíl

1. Krok role ve workflow přijme `agent: JMÉNO` (vedle `harness`, `model`, `thinking`). Krok dostane
   kopii `RoleDef` s tímto agentem; `output_type`, `gates`, `retries`, `description` zůstanou.
2. `.factory/roles.yaml` (i soubor předaný `--roles` / `load_roles(path)`) **bez klíče `code_steps`**
   je překryv nad balíčkovým registrem `engine/defaults/roles.yaml`. Soubor s `code_steps` nahradí
   registr jako dnes (beze změny chování).

Mimo rozsah: role jako položky knihovny, editor rolí, nové output typy / gates. `vendor/` a
`prototype/` se nemění. Testy nevolají model ani síť. Každá změna logiky v
`aifactory/src/aifactory/engine/` nese komentář `# aifactory` (konvence viz `engine/runner.py`,
např. `# aifactory: …`).

## Zjištění z průzkumu (kontext pro buildera)

- Interpreter (`workflow/interpreter.py`) i `preflight` a `check.check_agents` čtou agenta výhradně
  z `step.role.agent` (`step_override(cfg, role.agent, …)`, `params(..., role.agent, ...)`,
  `agents.validate(probe, [step.role.agent])`). Stačí tedy, aby parser vložil do `RoleStep.role`
  kopii role s jiným agentem — běh, preflight (roster + `check_override`) i `outline`
  (`"agent": step.role.agent`) pak fungují automaticky.
- `config/loader.py::_load_roles` volá `parse_roles(data)`; CLI `factory workflow check --roles P`
  volá `load_roles(P)`, který také končí v `parse_roles`. Překryv proto implementuj v
  `parse_roles` (v `engine/role_registry.py`), aby platil všude stejně.
- Kódy chyb jsou vyjmenované v `src/aifactory/skill/codes.py::ISSUE_CODES` a test
  `tests/test_skill.py::test_issue_codes_complete` staticky hledá každý literál kódu v
  `workflow/*.py` a `engine/role_registry.py` — **každý nový kód musí přibýt do `ISSUE_CODES`**
  (sekce `"roles"` resp. `"workflow"`).
- Existující test `tests/config/test_config_loader.py::test_invalid_roles_names_the_file` zapisuje
  `roles.yaml` bez `code_steps` (jen `plan` s `NoSuchOutput`). Po změně to bude překryv nad
  existujícím `plan`; chyba `unknown_output_type` na `roles.plan.output_type` zůstane → test dál
  projde. Ověř.
- Fixture rosteru: `workflow_fakes.AGENTS = ("planner","builder","reviewer","documenter","scout")`
  (pro `workflow_env`); `make_factory_repo` má v `.factory/agents.yaml` jen `planner` a `builder`.

## Změny

### 1. `aifactory/src/aifactory/engine/role_registry.py` (značky `# aifactory`)

Přidej překryv. Návrh:

```python
OVERLAY_REQUIRED: tuple[str, ...] = ("agent", "output_type", "gates", "description")  # aifactory

def _default_data() -> dict[str, Any]:  # aifactory: raw packaged registry, base of an overlay
    return yaml.safe_load(DEFAULT_ROLES_PATH.read_text(encoding="utf-8"))

def is_overlay(data: object) -> bool:  # aifactory
    """A roles mapping without `code_steps` overlays the packaged registry."""
    return isinstance(data, Mapping) and "code_steps" not in data

def merge_overlay(data: Mapping[Any, Any], base: Mapping[Any, Any]) -> dict[str, Any]:
    """Raw merge of an overlay onto ``base``; raise ``RolesError`` on structural problems."""
```

Pravidla `merge_overlay` (všechny problémy sbírej a vyhoď najednou `RolesError(issues)`):

- `raw = data.get("roles")`; chybí → bere se jako `{}` (prázdný překryv = balíčkový registr).
  Není-li mapping → `Issue("missing_roles", "`roles` must be a mapping", "roles")`.
- Index aliasů základu: pro každou base roli `alias -> canonical` (z `aliases`).
- Pro každé `name, spec` v překryvu, `path = f"roles.{name}"`:
  - `spec` není mapping → `invalid_role` („a role must be a mapping“), přeskoč.
  - `name` je alias base role → `alias_conflict`: `f"{name!r} is an alias of {canonical!r} — override {canonical!r}"`, přeskoč.
  - `name` je base role → `merged[name] = {**deepcopy(base_roles[name]), **spec}` (uvedená pole
    přepíší, ostatní zůstanou; `aliases` uvedené v překryvu nahradí seznam).
  - jinak nová role → pro každé pole z `OVERLAY_REQUIRED`, které ve `spec` chybí:
    `Issue("missing_key", f"a new role needs {key!r} (this file overlays the packaged registry; "
    "add `code_steps` to replace it)", f"{path}.{key}")`; jinak `merged[name] = dict(spec)`
    (přidej na konec, pořadí base rolí zachovej).
- Výsledek: `{**data, "roles": merged, "code_steps": deepcopy(base["code_steps"])}` — ostatní
  top-level klíče překryvu zůstanou, takže překlep (např. `role:`) nahlásí `parse_roles` jako
  `unknown_key` s cestou jako dnes.

Uprav `parse_roles`:

```python
def parse_roles(data: object, base: Mapping[Any, Any] | None = None) -> RoleRegistry:
    # aifactory: a file without `code_steps` overlays the packaged registry (D24)
    if is_overlay(data):
        data = merge_overlay(data, base if base is not None else _default_data())
    loader = _Loader()
    ...beze změny
```

Validace sloučeného výsledku jde přes stávající `_Loader` → `unknown_key`, `unknown_output_type`,
`unknown_gate`, `bad_description`, `alias_conflict` (nový alias = kód kroku nebo duplicita) atd. mají
stejné cesty (`roles.<name>.<key>`) i kódy jako dnes. Neplatný YAML / `None` (prázdný soubor) není
mapping → `is_overlay` vrátí False → stávající `not_a_mapping`.

Aktualizuj docstring modulu (jedna věta o překryvu). `load_roles` beze změny (volá `parse_roles`).

### 2. `aifactory/src/aifactory/engine/defaults/roles.yaml`

Jen hlavičkový komentář (`# aifactory: …`): `.factory/roles.yaml` bez `code_steps` je překryv
tohoto souboru — existující krok přepíše uvedená pole, nový krok potřebuje `agent`, `output_type`,
`gates`, `description`; soubor s `code_steps` registr nahradí. Data neměň.

### 3. `aifactory/src/aifactory/config/loader.py::_load_roles`

Logika se nemění (`parse_roles` řeší překryv sám). Doplň docstring/komentář: soubor bez
`code_steps` je překryv balíčkového registru. Chyby se dál hlásí jako
`ConfigIssue(label, f"{i.path}: {i.code}: {i.message}")`.

### 4. `aifactory/src/aifactory/workflow/model.py`

`RoleStep` dostane pole `agent: str | None = None` (explicitní `agent:` z workflow; `role.agent` už
je přepsaný). Umísti za `thinking`, s defaultem, ať se nerozbijí jiné konstrukce.

### 5. `aifactory/src/aifactory/workflow/parse.py`

- `_ROLE_OPTS` += `"agent"`.
- Nová metoda `_Parser.agent(value, path) -> str | None`: `None` → `None`; není neprázdný string →
  `self.add("invalid_agent", f"agent must be a non-empty roster name, got {value!r}", path)`, vrať
  `None`; jinak `value.strip()`. (`invalid_agent` už v `ISSUE_CODES["workflow"]` je.)
- V `role_step`: `agent = self.agent(opts.get("agent"), f"{path}.agent")`; pokud je, `role =
  dataclasses.replace(role, agent=agent)`; do `RoleStep(..., role=role, agent=agent)`.
- `code_step`: `agent` na kódovém kroku hlásí `override_on_code_step` stejně jako
  `harness/model/thinking` (tj. kontrola `if key in _OVERRIDES or key == "agent"`; zprávu nech
  „has no agent to set“).
- `outline`: řádek role už má `"agent": step.role.agent` (ukáže zvoleného agenta). Nic dalšího
  nutné; volitelně nech beze změny.
- Docstring modulu: zmínka, že krok může zvolit agenta.

### 6. `aifactory/src/aifactory/workflow/check.py`

`check_agents`: když agent není v rosteru a `step.agent is not None`, dej issue na cestu
`f"{step.path}.agent"` se zprávou `f"step {step.name!r} sets agent {name!r}, which is not in the
roster (agents: {known})"`; jinak zachovej dnešní zprávu a cestu `step.path` (stávající test
`("unknown_agent", "steps[2].review")` musí projít). `check_override` se aplikuje na zvoleného
agenta automaticky (přes `step.role.agent`). Docstring: zmínit `agent` kroku.
`preflight` v `interpreter.py` netřeba měnit (skip pro chybějícího agenta už dělá `not in roster`);
ověř testem.

### 7. `aifactory/src/aifactory/skill/codes.py`

Do `ISSUE_CODES["roles"]` přidej `"missing_key"`. (Ostatní použité kódy už existují.)

### 8. `aifactory/src/aifactory/skill/skill.md` (sekce „Workflow format“)

- Volby kroku role: `agent` (jméno z `.factory/agents.yaml`; krok běží na něm, typ výstupu a gates
  role zůstanou), `harness`, `model`, `thinking`, `when`, `id`, `description`, `input`. Kódové kroky
  odmítnou `agent`, `harness`, `model`, `thinking`.
- Nahraď větu „a workflow names roles, never agents“: workflow jmenuje role; `agent:` u kroku
  přepíše agenta jen pro ten krok; `factory workflow check` a preflight ověří, že je v rosteru a
  přijme `harness/model/thinking` kroku; `data.steps[].agent` ukazuje agenta kroku.
- Odstavec o překryvu: `.factory/roles.yaml` bez `code_steps` je překryv balíčkového registru —
  existující role přepíše uvedená pole (např. `review: {agent: critic}`), nová role potřebuje
  `agent`, `output_type`, `gates`, `description`; alias nelze přepsat (přepiš kanonické jméno);
  soubor s `code_steps` registr nahradí celý. Chyby: `data.issues[]` / config issues s `path` a
  `code` (`unknown_key`, `alias_conflict`, `missing_key`, …). Krátký YAML příklad.
- Po úpravě spusť `uv run pytest tests/test_skill.py` (sekce, kódy).

## Testy (pytest, bez modelu a sítě)

### `aifactory/tests/engine/test_role_registry.py`
- `test_overlay_changes_one_role_and_adds_one`: `parse_roles({"roles": {"review": {"agent":
  "critic"}, "audit": {"agent": "auditor", "output_type": "ReviewOutput", "gates":
  ["artifacts_exist"], "description": "Audit the change against the security checklist"}}})` →
  `roles["review"].agent == "critic"`, `output_type_name == "ReviewOutput"`, `gate_names`
  shodné s balíčkem; alias `reviewer` → `critic`; `audit` existuje; `plan` beze změny;
  `set(code_steps) == set(CODE_ACTIONS)`.
- `test_overlay_file_loads` přes `load_roles(path)` se souborem bez `code_steps`.
- `test_full_file_replaces_as_before`: `parse_roles(yaml.safe_load(DEFAULT_ROLES_PATH...))` dává
  stejné `(name, agent, output_type_name, gate_names, description, retries)` jako `load_roles()`;
  a plný soubor bez `scout` → `scout` neexistuje (náhrada, ne překryv).
- `test_invalid_overlay` (parametrize, assert `(code, path)` v issues):
  - nová role bez `gates` → `("missing_key", "roles.audit.gates")`
  - `review: {colour: red}` → `("unknown_key", "roles.review.colour")`
  - `planner: {agent: x}` → `("alias_conflict", "roles.planner")`
  - `plan: {aliases: [test]}` → `("alias_conflict", "roles.plan.aliases")`
  - `review: {output_type: Nope}` → `("unknown_output_type", "roles.review.output_type")`
  - `roles: []` → `("missing_roles", "roles")`
  - `review: 3` → `("invalid_role", "roles.review")`
  - top-level `role: {}` → `("unknown_key", "role")`

### `aifactory/tests/config/test_config_loader.py`
- `test_overlay_roles_merge_with_packaged`: `.factory/roles.yaml` = `roles: {build: {agent:
  planner}}` → `config.roles.roles["build"].agent == "planner"`, `config.roles.is_role("scout")`,
  `config.roles.is_code("test")`. Stávající testy musí projít beze změny.

### `aifactory/tests/workflow/test_workflow_parse.py`
- `- review: {agent: critic}` → `step.role.agent == "critic"`, `step.agent == "critic"`,
  `role.output_type_name == "ReviewOutput"`, gates shodné; `outline(...)` řádek `agent == "critic"`.
- `- build: {agent: ""}` → `("invalid_agent", "steps[0].build.agent")`.
- `- commit: {agent: builder}` → `override_on_code_step` na `....commit.agent`.

### Nový `aifactory/tests/workflow/test_workflow_step_agent.py` (fixture `workflow_env`)
- `test_step_runs_on_its_agent`: workflow `steps: [plan, {build: {agent: scout}}]`;
  `env.script.add("planner", PLAN)`, `env.script.add("scout", BUILD)` (BuildOutput envelope) →
  `exit_code == 0`; `[c.agent for c in env.script.calls] == ["planner", "scout"]`; záznam fáze
  `build` má ownera `scout` (`result.phases` / `records`), envelope `build` je `BuildOutput`.
- `test_step_agent_with_override`: `build: {agent: scout, harness: codex, model: gpt-5.5}` → volání
  `("codex", "scout", "gpt-5.5", ...)`.
- `test_unknown_step_agent_fails_preflight`: `build: {agent: ghost}` → `WorkflowError` s
  `[("unknown_agent", "steps[1].build.agent")]`, `env.script.calls == []`.
- Vzor: `tests/workflow/test_workflow_harness_mix.py` (importy `workflow_fakes`, `ok`, `workflow`,
  `FakeCodeRunner`, `workflow_env_fixture`).

### `aifactory/tests/workflow/test_workflow_cli.py`
- `factory workflow check` s `- build: {agent: ghost}` v `make_factory_repo` → exit 1, issue
  `("unknown_agent", "steps[1].build.agent")`.
- `.factory/roles.yaml` překryv s novou rolí `audit` (agent `planner`, `GenericOutput`, `gates: []`,
  popis) a workflow `steps: [plan, audit, {build: {agent: planner}}]` → exit 0; `data.steps`
  obsahuje řádek `audit` s `agent == "planner"` a `build` s `agent == "planner"`;
  `data.roles == ".factory/roles.yaml"`.

## Ověření

Z kořene worktree:

```
just test          # cd aifactory && uv run pytest (vč. web-test závislosti)
just typecheck     # mypy
just lint          # ruff check + ruff format --check
```

Rychlá smyčka: `cd aifactory && uv run pytest tests/engine/test_role_registry.py tests/workflow
tests/config/test_config_loader.py tests/test_skill.py -q`. Před `just lint` spusť
`uv run ruff format .` v `aifactory/`.

## Dokumentace

`app_docs/HAIFA-S05-T02-krok-agent-ve-workflow-a-prekryv-roles-y.md` patří fázi dokumentace;
builder ji nepíše, pokud o to není výslovně požádán.
