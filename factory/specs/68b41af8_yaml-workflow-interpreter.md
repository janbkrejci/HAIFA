# Plán: interpret YAML workflow nad enginem sssf (volba harnessu, modelu a thinking u kroku)

## Cíl

Workflow podle sekce „Workflow jako data“ v `docs/product-brief.md` bude YAML soubor. Interpret v `prototype/` ho načte, celý zvaliduje hned při načtení a spustí přes engine z `vendor/sssf/templates/adws/adw_modules/`. Použije `run.phase`, `agents.execute`, `quality`, `git_helper` a `changes`. Dodávka:

- `prototype/src/haifa_proto/roles.py`: registr rolí načítaný z YAML,
- `prototype/src/haifa_proto/defaults/roles.yaml`: obsahová kopie `adw_modules/roles.py` a navíc role `revise`,
- `prototype/src/haifa_proto/workflow.py`: model workflow, načtení a validace, podmínky, interpret,
- `prototype/src/haifa_proto/defaults/workflows/*.yaml`: `simple-sdlc`, `plan`, `plan-build`, `plan-build-test`, `document`, `scout`,
- CLI `haifa-proto workflow check <soubor> [--roles PATH] [--json]`,
- testy v `prototype/tests/`.

Mimo rozsah: worktree, PR, backlog, web, grafický editor. Příkaz `workflow run` se nepřidává, stačí knihovní funkce `run_workflow`.

## Pevná omezení

- `vendor/` se **neupravuje**. Engine se importuje jen přes `haifa_proto.engine.load_engine_module(...)` (jediné místo, které sahá na `sys.path`). Harnessy se registrují přes `haifa_proto.harness.install()`.
- Každá fáze má popis, který neopakuje jen její jméno (pravidlo 7 ve `vendor/sssf/SKILL.md`). Kontroluje se **při načtení**: popis se prožene validátorem `data_types.PhaseParams` (viz níže).
- Testy nevolají model ani skutečné `claude`/`codex`/`pi`. Harnessy v `agents.INTERFACES` se v testu nahrazují falešnými objekty přes `monkeypatch.setitem`. Kódové kroky (`test`, `commit`, `changes`, `command`) jdou přes falešný `CodeRunner`.
- Žádný `eval`/`exec`/`compile`. Podmínky parsuje vlastní rekurzivní sestup.
- Kód musí projít `just test`, `just typecheck` (mypy strict nad `src` i `tests`) a `just lint` (ruff check a `ruff format --check`, délka řádku 100).

## Zjištěný stav enginu (recon)

- `adw_modules/roles.py` obsahuje:
  - `RoleSpec(agent, output_type, description, gates, retries=1)` a `CodeSpec(action, description)`.
  - Role `ROLES`: `plan`, `build`, `scout`, `review`, `document`, `ask` a `fix`.
  - Aliasy `planner`, `builder`, `reviewer`, `documenter`, které sdílejí **tentýž** objekt spec.
  - Kódové kroky `CODE_STEPS`: `test`, `quality`, `commit`, `changes`.
  - Role `revise` **neexistuje**. `adw_simple_sdlc.py` ji zapisuje inline: agent `builder`, typ `BuildOutput`, gate `diff_matches_claims`, popis „Close the reviewer's blocking findings“, `retries=1`.
- `agents.execute(run, phase, call)` najde agenta jako `resolve(run.cfg, phase.params.owner)` a z `AgentConfig` čte `coding_agent`, `model` a `thinking`. `harness = INTERFACES[agent.coding_agent]`, volá se `harness.run(request, on_event=, on_wait=, on_spawn=, on_exit=)` a `harness.ToolCallTracker().observe(event)`. Předchozí envelope se do promptu vkládá jako `call.previous.model_dump_json(indent=2)` na místo `{{previous_envelope}}` v `user.md`. Session se znovu použije jen při stejném `agent.model` (`_agent_session_id`). Když je `envelope.status != "success"`, vyhodí se `RuntimeError`.
- **Přepis harnessu, modelu a thinking u kroku** se proto dělá stejně jako `chain.apply_step`: před fází se dočasně změní `AgentConfig` v `run.cfg` a po fázi se v `finally` obnoví. Když se harness mění na jiný než `pi`, vyprázdní se i `harness_engineering`, protože `agents.validate` ho jinde odmítne.
- `haifa_proto.harness.install()` registruje `claude`, `codex`, `pi` (a alias `claude_code`) do `agents.INTERFACES` a rozšiřuje `coding_agent` na `Literal["claude","codex","pi","claude_code"]`. `harness.HARNESSES` má kanonické klíče `claude`, `codex`, `pi`.
- Validátor `PhaseParams.description` odmítne prázdný popis i popis, pro který platí `text.rstrip(".").casefold() == name.replace("_"," ").casefold()`. Chyba je pydantic `ValidationError`.
- `quality.run_tests(run) -> QualityResult`, `quality.run_quality(run)`, `quality.as_envelope(result, what) -> VerifyOutput`. Funkce `quality._run(QualityCheckSpec(name, area, operation, argv, timeout_seconds), run) -> QualityCheckResult` vyžaduje otevřenou fázi (`run.phases[-1]`). Hodnoty `area` a `operation` ověř v `QualityArea`/`QualityOperation` v `data_types.py`. `quality.test` používá `area="backend", operation="build"`.
- `git_helper.commit_all(message) -> str` vrací sha, nebo `""`, když není co commitovat. `git_helper.rev("HEAD")`, `git_helper.is_repo()`. `changes.capture(run, ChangeCapture(base=sha)) -> ChangeSet` (`.empty`) a `changes.as_envelope(changeset, notes="") -> ChangesOutput`.
- `session.ensure(cfg, adw_id)` vytvoří `Run`. Tracer používá sqlite `cfg.observability.db` a `events.jsonl` v `cfg.defaults.data_dir`. `Run.__init__` volá `git_helper.repo_root()` z cwd. `session.ensure` nastaví handlery SIGTERM/SIGINT. `permissions.snapshot` vyžaduje git repo s alespoň jedním commitem.
- `run.finish(accepted=, reason=) -> int` (0 nebo 1) se volá právě jednou.
- Pole envelopes (`model_fields`):
  - `EnvelopeBase`: `status, summary, artifacts, notes_for_next_agent`,
  - `PlanOutput`: navíc `commit_message`,
  - `BuildOutput`: `changed_files, commit_message`,
  - `ReviewOutput`: `approved, findings, blocking`,
  - `DocumentOutput`: `document_path, documented_files, commit_message`,
  - `VerifyOutput`: `passed, failures`,
  - `ChangesOutput`: `base, changed_files, insertions, deletions, stat, diff_path`.
- Fáze `adw_simple_sdlc.py` (jména a vlastníci):
  - `request`(engineer), `plan`(planner), `commit_plan`(git), `build`(builder),
  - smyčka `test_i`(quality) a `fix_i`(builder), max 3,
  - smyčka `review_i`(reviewer) a `revise_i`(builder), max 2,
  - `retest`(quality), jen když revize proběhla a review schválilo,
  - pak při `verified`: `commit_build`(git), `changes`(git), `document`(documenter), `commit_docs`(git).

  Review dostává `previous=build` (poslední výstup builderu), ne envelope testu. Commit bere `commit_message` posledního envelope, který to pole má (plan → build/fix/revise → document).
- `tests/test_cli.py::test_subcommands_are_noops` parametrizuje `backlog, harness, task, serve`. Přidej do seznamu `workflow`: bez podpříkazu vypíše nápovědu a vrátí 0.
- `pyproject.toml`: hatch balí `src/haifa_proto` celé, takže YAML v `defaults/` se dostane do wheelu. Soubory hledej přes `importlib.resources.files("haifa_proto") / "defaults"` (v testech jde o běžnou cestu, stačí `Path(str(...))`).

## Návrh

### 1. `defaults/roles.yaml`

```yaml
# Step name -> role. Content mirrors vendor adw_modules/roles.py; output types
# and gates are names looked up in adw_modules.data_types / adw_modules.gates.
roles:
  plan:
    agent: planner
    output_type: PlanOutput
    gates: [artifacts_exist, files_non_empty]
    description: Turn the request into an implementable plan
    aliases: [planner]
  build:
    agent: builder
    output_type: BuildOutput
    gates: [diff_matches_claims]
    description: Implement what the previous step asked for
    aliases: [builder]
  scout:    {agent: scout, output_type: ScoutOutput, gates: [artifacts_exist],
             description: "Find and report where things live; change nothing"}
  review:   {agent: reviewer, output_type: ReviewOutput, gates: [artifacts_exist, verdict_consistent],
             description: Confirm the work matches what was asked for, aliases: [reviewer]}
  document: {agent: documenter, output_type: DocumentOutput, gates: [artifacts_exist, files_non_empty],
             description: Write up the completed change from the diff, aliases: [documenter]}
  ask:      {agent: builder, output_type: GenericOutput, gates: [],
             description: "Answer the request directly, with no fixed output shape"}
  fix:      {agent: builder, output_type: BuildOutput, gates: [diff_matches_claims],
             description: "Repair what the previous step reported, from its verbatim output"}
  revise:   {agent: builder, output_type: BuildOutput, gates: [diff_matches_claims],
             description: "Close the reviewer's blocking findings"}   # from adw_simple_sdlc.py
code_steps:
  test:    {owner: quality, description: "Run the suite — a known command, so code runs it and no agent has to rediscover it"}
  quality: {owner: quality, description: "Run lint, typecheck and build — known commands, all of them"}
  commit:  {owner: git, description: "Commit what the previous step produced, in its own words"}
  changes: {owner: git, description: "Diff the run against its pinned baseline, for the documenter"}
  command: {owner: quality, description: "Run the command the workflow names, as code rather than as an agent"}
```

Popisy zkopíruj **přesně** z `vendor/.../roles.py`, včetně pomlčky „—“. `retries` je volitelné, výchozí hodnota 1, stejně jako v `RoleSpec`. Kódové kroky jsou pevně dané akce, `code_steps` dodávají jen `owner` a `description`. Neznámý klíč v `code_steps` je chyba.

### 2. `roles.py`

```python
class RolesError(Exception): issues: list[Issue]      # Issue sdílí workflow.py, viz níže

@dataclass(frozen=True)
class RoleDef:
    name: str; agent: str; output_type: type[Any]; output_type_name: str
    gates: tuple[Callable[..., Any], ...]; gate_names: tuple[str, ...]
    description: str; retries: int = 1

@dataclass(frozen=True)
class CodeStepDef:
    name: str; owner: str; description: str          # name is also the action

CODE_ACTIONS = ("test", "quality", "commit", "changes", "command")

@dataclass(frozen=True)
class RoleRegistry:
    roles: dict[str, RoleDef]          # aliases map to the SAME RoleDef object
    code_steps: dict[str, CodeStepDef]
    def is_role(name) -> bool; def is_code(name) -> bool; def known_steps() -> list[str]
    def result_fields(name) -> frozenset[str]   # see section 4

DEFAULT_ROLES_PATH = Path(str(resources.files("haifa_proto") / "defaults" / "roles.yaml"))
def load_roles(path: Path | None = None) -> RoleRegistry
```

`load_roles` sbírá **všechny** problémy a nakonec vyhodí `RolesError`. Kontroluje:

- Soubor je platný YAML s mapou na nejvyšší úrovni a obsahuje `roles` a `code_steps`.
- `output_type` je jméno atributu v `load_engine_module("data_types")`. Atribut musí být třída a podtřída `data_types.EnvelopeBase`.
- Každý gate je jméno atributu v `load_engine_module("gates")` a musí být callable.
- `agent` je neprázdný řetězec a `retries` je int ≥ 0.
- Alias nesmí kolidovat s jinou rolí ani s kódovým krokem.
- Jméno kódového kroku leží v `CODE_ACTIONS` a všechny akce z `CODE_ACTIONS` jsou pokryté.
- Popis se kontroluje podle pravidla 7 funkcí `check_description(name, text) -> str | None`. Ta zkusí `data_types.PhaseParams(name=name, kind="code", owner="x", description=text)` a vrátí text chyby z `ValidationError`, jinak None. Stejnou funkci používá `workflow.py`.

### 3. Formát workflow (YAML)

```yaml
name: simple-sdlc                     # povinné, neprázdné
description: ...                       # povinné, pravidlo 7 vůči name
steps: [ ... ]                         # povinné, neprázdný seznam
accept: test.passed and review.approved  # volitelné, výchozí True
```

Položka `steps` má jeden z těchto tvarů:

| Tvar | Význam |
| --- | --- |
| `plan` (řetězec) | role nebo kódový krok bez voleb |
| `plan: {harness: claude, model: opus, thinking: high, when: ..., id: ..., description: ..., input: [...]}` | role s volbami, hodnota smí být i `null` |
| `test: {when: ..., id: ..., description: ...}` | kódový krok `test`, `quality`, `commit` nebo `changes` |
| `command: {id: dotnet_test, argv: [dotnet, test], timeout: 600, when: ..., description: ...}` | kódový krok s argv; `id` i neprázdný `argv` (seznam řetězců) jsou povinné |
| `repeat: {max: 3, until: test.passed, when: ...}` + sourozenecký klíč `steps: [...]` | smyčka; `max` je povinné (int ≥ 1), `until` volitelné, `steps` povinné a neprázdné |

Pravidla:

- Jednoprvková mapa je krok. Mapa s klíčem `repeat` smí mít navíc jen `steps`. Jiné klíče jsou chyba (`unknown_key`).
- `harness` smí být jen `claude`, `codex` nebo `pi` (kanonické klíče `harness.HARNESSES`, bez aliasu `claude_code`). `thinking` smí být `off, minimal, low, medium, high, xhigh, max`. `model` je neprázdný řetězec. U kódového kroku jsou tyto tři klíče chyba (`override_on_code_step`).
- `id` pojmenovává fázi v trace (výchozí je jméno kroku) a musí odpovídat `^[a-z][a-z0-9_]*$`. U `command` je `id` zároveň jméno výsledku v podmínkách a nesmí kolidovat se jménem role ani kódového kroku.
- `description` přepíše popis z registru. Kontroluje se pravidlem 7 vůči `id`, případně vůči jménu kroku.
- `input` (jen u rolí) je seznam jmen kroků. Jako `previous` se předá nejnovější envelope, který vyrobil některý z nich. Výchozí `previous` je poslední envelope vůbec, což odpovídá chování `adw_compose`. Jména musí ve workflow existovat.

Datový model (frozen dataclasses v `workflow.py`):

```python
@dataclass(frozen=True)
class Issue: code: str; message: str; path: str      # path e.g. "steps[3].repeat.until"
                                                     # (Issue lives in workflow.py or a tiny
                                                     #  shared module, importable by roles.py)
class WorkflowError(Exception): issues: list[Issue]

@dataclass(frozen=True)
class Condition: source: str; node: Node             # Node = parsed AST (section 4)

@dataclass(frozen=True)
class RoleStep:  name: str; role: RoleDef; phase_id: str; description: str; path: str
                 harness: str | None; model: str | None; thinking: str | None
                 when: Condition | None; inputs: tuple[str, ...]
@dataclass(frozen=True)
class CodeStep:  name: str; action: str; key: str     # key = condition namespace name
                 phase_id: str; owner: str; description: str; path: str
                 argv: tuple[str, ...]; timeout: int; when: Condition | None
@dataclass(frozen=True)
class Repeat:    max: int; until: Condition | None; when: Condition | None
                 steps: tuple[Step, ...]; path: str
Step = RoleStep | CodeStep | Repeat

@dataclass(frozen=True)
class Workflow:  name: str; description: str; steps: tuple[Step, ...]
                 accept: Condition | None; source: Path | None

def load_workflow(path: Path, roles: RoleRegistry | None = None) -> Workflow
def parse_workflow(data: object, roles: RoleRegistry, source: Path | None = None) -> Workflow
def check_workflow_file(path: Path, roles_path: Path | None = None) -> CheckResult
```

`load_workflow` a `parse_workflow` sesbírají **všechny** problémy a vyhodí jediný `WorkflowError`. Kódy chyb:

| Kód | Kdy |
| --- | --- |
| `invalid_yaml`, `not_a_mapping` | soubor nejde přečíst jako YAML, nebo nejvyšší úroveň není mapa |
| `missing_name`, `missing_steps`, `unknown_key` | chybí povinné pole, nebo je tam neznámý klíč |
| `unknown_step` | neznámá role nebo kódový krok; hláška obsahuje `known_steps()` |
| `unknown_harness`, `invalid_thinking`, `invalid_model`, `override_on_code_step` | neplatný přepis harnessu, thinking nebo modelu, nebo přepis u kódového kroku |
| `missing_max`, `invalid_max`, `empty_repeat` | chyba u `repeat` |
| `missing_argv`, `missing_id`, `invalid_id`, `duplicate_id` | chyba u `command` a `id`; duplicitní `id` jen u `command` |
| `bad_description` | popis porušuje pravidlo 7 |
| `bad_condition` | syntaktická chyba podmínky |
| `unknown_ref` | krok v podmínce nebo v `input` není ve workflow |
| `unknown_field` | pole neexistuje na výstupu kroku |

Chyba registru rolí se v `check` hlásí jako `invalid_roles`.

### 4. Podmínky (`when`, `until`, `accept`)

Gramatika bez `eval`, nad vlastním tokenizérem (regex tokenů a rekurzivní sestup):

```
expr    := or
or      := and ("or" and)*
and     := not ("and" not)*
not     := "not" not | cmp
cmp     := atom (("=="|"!="|"<"|"<="|">"|">=") atom)?
atom    := REF | NUMBER | STRING | "true" | "false" | "null" | "(" expr ")"
REF     := IDENT "." IDENT        # exactly two parts: <step>.<field>
IDENT   := [a-z_][a-z0-9_]*
STRING  := '...' | "..."          # no escapes needed; unterminated -> bad_condition
```

- Klíčová slova `and/or/not/true/false/null` nesmí být jménem kroku ani pole.
- Cokoli jiného je `bad_condition` s pozicí. Patří sem `__import__('os')`, volání funkce, holý identifikátor bez tečky, `a.b.c` i prázdný řetězec.
- AST jsou dataclasses `Ref(step, field)`, `Lit(value)`, `Not(x)`, `And(l, r)`, `Or(l, r)`, `Cmp(op, l, r)`.
- Funkce `refs(node)` vrátí všechny `Ref`. Používá je validace i našeptávač v UI.

**Pole kroků** (`RoleRegistry.result_fields(name)`):

- role: `set(output_type.model_fields)`,
- `test`, `quality`, `command`: `set(data_types.VerifyOutput.model_fields)`, tedy i `passed` a `failures`,
- `changes`: `set(data_types.ChangesOutput.model_fields)`,
- `commit`: `{"sha", "committed", "message"}`,
- u každého kroku navíc `ran`.

**Validace při načtení:**

- Pro každý `Ref` musí `step` být klíčem jmenného prostoru nějakého kroku ve workflow. U role je to jméno kroku, jak je napsané (`review`, `reviewer`), u kódového kroku jeho jméno, u `command` jeho `id`. Jinak `unknown_ref`.
- `field` musí ležet v `result_fields`, jinak `unknown_field`. Hláška vypíše dostupná pole.
- Příklad: `until: test.approved` skončí `unknown_field`.

**Vyhodnocení** (`evaluate(node, ns: Mapping[str, Mapping[str, Any]]) -> Any`, `truthy(...) -> bool`):

- `Ref` vrací `ns[step][field]`. Krok, který ještě neběžel, dává `None`, a `ran` je v tom případě `False`.
- `and`, `or` a `not` pracují s Python pravdivostí a vyhodnocují zkráceně.
- `Cmp` porovnává. Když porovnání vyhodí `TypeError` (například `None < 3`), výsledek je `False`.
- Jmenný prostor se po každém provedeném kroku přepíše jeho posledním výsledkem: `envelope.model_dump()` nebo pole kódového kroku, plus `ran=True`.

### 5. Interpret (`run_workflow`)

```python
class CodeRunner(Protocol):                           # seam for tests
    def test(self, run: Any) -> Any: ...              # -> QualityResult
    def quality(self, run: Any) -> Any: ...           # -> QualityResult
    def commit(self, run: Any, message: str) -> str: ...
    def changes(self, run: Any, base: str) -> Any: ...   # -> ChangeSet
    def command(self, run: Any, step: CodeStep) -> Any: ...  # -> QualityResult
    def baseline(self) -> str: ...

class EngineCodeRunner:     # default: quality.run_tests / run_quality, git_helper.commit_all,
                            # changes.capture(run, ChangeCapture(base=base)),
                            # quality._run(QualityCheckSpec(name=step.key, area="backend",
                            #   operation="build", argv=list(step.argv),
                            #   timeout_seconds=step.timeout), run) wrapped into QualityResult
                            #   exactly like quality.run_tests does;
                            # baseline = git_helper.rev("HEAD") if git_helper.is_repo() else ""

@dataclass
class StepRecord: phase: str; step: str; kind: str; owner: str
                  harness: str | None; model: str | None; thinking: str | None

@dataclass
class WorkflowRun:
    exit_code: int; accepted: bool; adw_id: str
    records: list[StepRecord]                 # executed steps in order
    envelopes: dict[str, Any]                 # step namespace key -> last envelope
    results: dict[str, dict[str, Any]]        # the condition namespace

def preflight(workflow: Workflow, cfg: Any) -> None
def run_workflow(workflow: Workflow, prompt: str, cfg: Any, *,
                 code: CodeRunner | None = None, adw_id: str | None = None) -> WorkflowRun
```

`preflight` se volá na začátku `run_workflow` před `session.ensure`, takže se nic nespustí proti napůl platné konfiguraci:

1. Zavolá `harness.install()`.
2. Pro každou roli ve workflow (i vnořenou) vezme `probe = cfg.model_copy(deep=True)`, aplikuje na ni přepis kroku (stejná funkce jako za běhu) a zavolá `agents.validate(probe, [role.agent])`. Dvojice `(agent, harness, model, thinking)` se kontrolují jen jednou.
3. Když `agents.validate` vyhodí `SystemExit`, převede ji na `WorkflowError([Issue("invalid_agent", str(e), step.path)])`.

`apply_override(cfg, step) -> tuple[AgentConfig, dict[str, Any]]` najde agenta, uloží původní hodnoty `coding_agent`, `model`, `thinking` a `harness_engineering` a nastaví nové:

- Harness se přepíše na `step.harness`. Když je nový harness jiný než `pi`, `harness_engineering` se nastaví na `[]`.
- Model se přepíše na `step.model` a thinking na `step.thinking`.
- Hodnota, kterou krok nepřepisuje, zůstane podle agenta.

`restore(agent, saved)` vrátí původní hodnoty. Obě funkce se volají v `try/finally` kolem agentní fáze.

Průběh `run_workflow`:

1. Zavolá `preflight`. Pak `run = session.ensure(cfg, adw_id)`, `baseline = code.baseline()` (připnuté před prvním commitem) a `run.console.note(f"workflow: {workflow.name}")`.
2. Otevře fázi `request` (`kind="engineer"`, `owner=run.engineer`, popis „Capture the incoming ask and the workflow chosen to answer it“) a zaloguje `ph.log(input=prompt, workflow=workflow.name, baseline=baseline[:7])`.
3. `_exec(steps, suffix=())` prochází kroky:
   - Když má krok `when` a podmínka nevyjde, krok se přeskočí: nic se nezapíše, `ran` se nemění.
   - **Repeat:** `for i in 1..max:` projde tělo s `suffix + (i,)`. Po **každém** provedeném kroku těla vyhodnotí `until` a když platí, ukončí celou smyčku. Tahle sémantika dává přesně pořadí `test_1, fix_1, test_2` z Python verze.
   - **Jméno fáze:** `phase_id` doplněný o `_` a indexy iterací (`test_1`, `review_2`). Když už jméno v běhu je, přidá se `_2`, `_3` atd., protože fáze musí být v trace unikátní.
   - **Role:** `apply_override`, pak `run.phase(PhaseParams(name=..., kind="agent", owner=role.agent, retries=role.retries, description=step.description))`. Do fáze `ph.log(harness=agent.coding_agent, model=agent.model, thinking=agent.thinking)`, potom `env = ph.call(AgentCall(output_type=role.output_type, prompt=prompt, previous=<previous>, gates=list(role.gates)))`. Nakonec se obnoví hodnoty agenta. `<previous>` je nejnovější envelope z kroků v `input`, pokud je `input` zadané, jinak poslední envelope vůbec. Uloží se `StepRecord`, `envelopes[name] = env` a `results[name] = {**env.model_dump(), "ran": True}`.
   - **test / quality:** fáze `kind="code"`, owner podle registru (`quality`). Výsledek se zaloguje stejně jako `record()` v `adw_simple_sdlc` (`passed`, `checks`, `artifacts`). Do `previous` přijde `quality.as_envelope(result, action)`. `results[name]` jsou pole `VerifyOutput` a `ran`.
   - **command:** totéž jako test, jen přes `code.command(run, step)`. Klíč výsledku je `step.key` (id) a `as_envelope(result, step.key)`.
   - **commit:** zpráva se vezme z nejnovějšího envelope, který má neprázdné `commit_message`, jinak `f"sssf({run.adw_id}): {previous.summary}"` (vzor `adw_simple_sdlc.commit`). Provede se `sha = code.commit(run, message)`, zaloguje se `ph.log(sha=, message=, committed=bool(sha))` a `results["commit"] = {"sha","committed","message","ran"}`. `previous` se nemění.
   - **changes:** `cs = code.changes(run, baseline or "HEAD")` a log jako v `adw_compose`. Když je `cs.empty`, vyhodí se `RuntimeError("nothing changed since ... — there is nothing to document.")`. `previous = changes.as_envelope(cs)` a `results["changes"]` jsou pole `ChangesOutput` a `ran`.
4. `accepted = truthy(workflow.accept)`, a když `accept` chybí, pak `True`. Vrátí se `run.finish(accepted=accepted, reason=f"accept `{workflow.accept.source}` was not met")`.
5. Výjimka z fáze se nechytá, propadne ven stejně jako v Python ADW. Fáze i session už jsou v té chvíli zapsané jako `fail`.

### 6. Výchozí workflow (`defaults/workflows/`)

`simple-sdlc.yaml` popisy kopíruje z `adw_simple_sdlc.py`:

```yaml
name: simple-sdlc
description: Plan, build, test with repairs, review with revision, then document — committing each work product separately
steps:
  - plan
  - commit: {id: commit_plan, description: Put the spec on record before any code exists to blur it}
  - build: {description: Implement the plan exactly}
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix: {description: "Repair what the suite reported, from its verbatim output"}
  - repeat: {max: 2, until: review.approved}
    steps:
      - review: {input: [build, fix, revise], description: Confirm the build matches the plan}
      - revise
  - test: {id: retest, when: revise.ran and review.approved,
           description: "Re-run the suite — the revision changed code after the last green result"}
  - commit: {id: commit_build, when: test.passed and review.approved,
             description: "Land the code only now: green suite, approved review"}
  - changes: {when: test.passed and review.approved,
              description: "Diff the whole run against its pinned baseline, for the documenter"}
  - document: {when: test.passed and review.approved, description: Write up the completed change}
  - commit: {id: commit_docs, when: test.passed and review.approved,
             description: "Ship the write-up in its own commit, beside the code it describes"}
accept: test.passed and review.approved
```

Známá odchylka od Python verze, kterou do YAML napiš jako komentář: když review zamítne i v poslední iteraci, YAML smyčka pustí ještě `revise_2`, kdežto Python ne. Na výsledku to nic nemění, protože `retest` i commity hlídá `review.approved`. Tři testované scénáře se tím nemění.

Další workflow podle docstringů `Phases:`:

- `plan.yaml`: `[plan]`.
- `scout.yaml`: `[scout]`.
- `plan-build.yaml`: `[plan, build, commit]` s popisem commitu „Land the builder's changes, using the message it wrote“.
- `plan-build-test.yaml`: `[plan, build, repeat{max 3, until test.passed}[test, fix], commit{when test.passed}]` a `accept: test.passed`.
- `document.yaml`: `[changes, document]`.

Všechny mají `description` platné podle pravidla 7.

### 7. CLI `workflow check`

V `cli.py`:

- přibude podpříkaz `workflow`; bez podpříkazu vypíše nápovědu a vrátí 0 (vzor `harness`),
- `workflow check <file> [--roles PATH] [--json]` volá `check_workflow_file`.

```python
@dataclass
class CheckResult:
    ok: bool; path: str; workflow: str | None; issues: list[Issue]; outline: list[dict[str, Any]]
    def to_json(self) -> dict[str, Any]
```

- `outline` je plochý seznam kroků ve tvaru `{"path","step","kind","phase","agent","owner","harness","model","thinking","when","until","max"}` (klíče `None` vynech). Workflow se nespouští a konfigurace agentů se nečte. Kontroluje se jen syntaxe, registr, harness, thinking, podmínky a popisy.
- Na neexistující soubor vrací `ok: false` s kódem `missing_file`.
- JSON výstup: `{"ok": bool, "path": str, "workflow": name|null, "errors": [{"code","message","path"}], "steps": outline}`. Exit 0, když je `ok`, jinak 1.
- Textový výstup: `OK: <name> (<n> steps)`, při chybě řádky `<file>:<path>: <code>: <message>` a nakonec `<n> error(s)`.

## Testy (`prototype/tests/`)

Sdílené pomůcky patří do `tests/workflow_fakes.py`. Vše musí projít mypy strict (anotace, `Any` u engine typů).

- **`FakeHarness(name, script)`**: objekt s atributy `run`, `resolve_model` (vrací `("fake", pattern)`), `context_window` (vrací 0) a `ToolCallTracker` (třída, jejíž `observe` vrací None).
  - `run(request, on_event=None, on_wait=None, on_spawn=None, on_exit=None)` zjistí agenta z `Path(request.session_dir).parent.name`.
  - Zapíše `Call(harness=name, agent, model=request.model, thinking=request.thinking, prompt=request.prompt)` do sdíleného `script.calls`.
  - Vezme další envelope z `script.queue[agent]` a vrátí `data_types.AgentResult(text=json.dumps(env), returncode=0, session_id=request.session_id)`. Prázdná fronta je `AssertionError`.
- **`FakeCodeRunner(test_results: list[bool])`**:
  - `test()` vrací `QualityResult(passed=b, checks=[], failures=[] if b else ["test: failed"], artifacts=[])`. Ověř, že `QualityResult` jde postavit bez `checks`. Jinak postav `QualityCheckResult` s vyplněnými poli.
  - `commit()` si zapíše zprávu a vrátí `"abc1234"`.
  - `changes()` vrací `ChangeSet(base=BaseRef(label=..., ref=..., commit="0"*40, reason=""), files=["x.py"], insertions=1)`. Ověř povinná pole `BaseRef` v `data_types.py` ř. 185 a `ChangeSet.empty`.
  - `baseline()` vrací `"0"*40`.
- **Fixture `engine_env(tmp_path, monkeypatch)`**:
  1. `git init` v `tmp_path/"repo"`, první commit (nastav `user.email`/`user.name` lokálně v repu) a `monkeypatch.chdir(repo)`.
  2. Prompty `tmp_path/"prompts"/{system,user}.md`. `user.md` obsahuje `PREV<<{{previous_envelope}}>>PREV`.
  3. `sssf.config.yaml` v `tmp_path` s `defaults.data_dir` a `observability.db` pod `tmp_path/"data"`, mimo repo. Agenti `planner`, `builder`, `reviewer` a `documenter` mají `coding_agent: claude`, `model: sonnet`, `thinking: medium` a `prompt_engineering` na soubory výše.
  4. `harness.install()`, pak `cfg = agents.load_config(path)`.
  5. Falešné harnessy přes `monkeypatch.setitem(agents.INTERFACES, n, FakeHarness(n, script))` pro `claude`, `codex`, `pi`.
  6. Uloží `signal.getsignal(SIGINT/SIGTERM)` a na konci je vrátí zpět.

Soubory testů:

1. **`test_roles.py`**
   - `load_roles()` odpovídá vendoru: pro každý klíč `vendor_roles.ROLES` má registr stejné `agent`, **stejný objekt** `output_type`, stejné gate funkce ve stejném pořadí (`is`), stejné `description` a `retries`. Aliasy sdílejí tentýž `RoleDef`.
   - Kódové kroky z `CODE_STEPS` mají stejné popisy.
   - Navíc oproti vendoru jsou jen `revise` (a `command` mezi kódovými kroky).
   - Chyby v YAML v `tmp_path`: neznámý `output_type`, neznámý gate, `output_type`, který není podtřídou `EnvelopeBase` (třeba `PhaseParams`), popis rovný jménu (`plan: {description: Plan}`) a kolize aliasu. Každá dá `RolesError` se správným kódem.
2. **`test_conditions.py`**
   - Parsování a vyhodnocení `and`, `or` a `not` s prioritou: `not a.x or b.y and c.z`.
   - Závorky, všechna porovnání, řetězcový, číselný i bool literál.
   - Chybějící krok dává `None`, `x.ran` bez běhu je `False` a `None < 1` je `False`.
   - `bad_condition` pro `__import__('os').system('x')`, `a`, `a.b.c`, `a.b ==`, `"unterminated`, `a.b and`.
   - Kontrola, že `workflow.py` neobsahuje `eval(` ani `exec(`: grep ve zdrojáku přes `Path(workflow.__file__).read_text()`.
3. **`test_workflow_load.py`**
   - Parametrizace přes všechny `defaults/workflows/*.yaml`: načtou se bez chyby.
   - `simple-sdlc` má očekávanou strukturu: 2× `Repeat` s `max` 3 a 2.
   - Chybné případy (každý z inline YAML v `tmp_path`) končí `WorkflowError` s daným kódem **při `load_workflow`**. U případů, kdy se chyba za běhu ukázat nemůže, se `run_workflow` nevolá:
     - neznámá role (`unknown_step`),
     - neznámý harness `harness: gemini` (`unknown_harness`),
     - `until: test.approved` (`unknown_field`),
     - `until: nothing.passed` (`unknown_ref`),
     - `repeat: {until: test.passed}` bez `max` (`missing_max`),
     - `max: 0` (`invalid_max`),
     - `test: {model: opus}` (`override_on_code_step`),
     - `thinking: extreme` (`invalid_thinking`),
     - `command` bez `argv` (`missing_argv`),
     - popis rovný `id` (`bad_description`),
     - neznámý klíč u kroku (`unknown_key`).
   - Jeden soubor s několika chybami vrátí všechny najednou.
4. **`test_workflow_simple_sdlc.py`**: tři scénáře nad `defaults/workflows/simple-sdlc.yaml` s `FakeCodeRunner` a falešnými harnessy.
   - Assert `[(p.params.name, p.params.kind, p.params.owner) for p in run.phases]` není k dispozici zvenku. Použij `WorkflowRun.records` a k tomu fázi `request` z traceru, nebo lépe přidej do `WorkflowRun` `phases: list[tuple[str, str, str]]` naplněné z `run.phases` po `finish`. Vyber jednu variantu a drž ji.
   - Očekávané posloupnosti (jméno, kind, owner) přepsané z docstringu `Phases:`:
     - **vše napoprvé** (testy `[True]`, review `approved`): `request/engineer`, `plan/agent/planner`, `commit_plan/code/git`, `build/agent/builder`, `test_1/code/quality`, `review_1/agent/reviewer`, `commit_build/code/git`, `changes/code/git`, `document/agent/documenter`, `commit_docs/code/git`.
     - **testy jednou selžou** (`[False, True]`): po `build` následuje `test_1`, `fix_1/agent/builder`, `test_2`, `review_1` a dál jako výše.
     - **review jednou zamítne** (reviewer: `approved=False, blocking=["missing X"]`, pak `approved=True`; testy `[True, True]`): po `test_1` následuje `review_1`, `revise_1/agent/builder`, `review_2`, `retest/code/quality`, `commit_build` a dál jako výše.
   - Ve všech scénářích: `exit_code == 0`, `accepted is True` a všechny volání harnessu mají `harness == "claude"`, `model == "sonnet"`, `thinking == "medium"` (výchozí hodnoty agenta, workflow nic nepřepisuje).
   - Ve scénáři 3 prompt `review_2` obsahuje envelope z `revise_1` (`input`), prompt `revise_1` obsahuje zamítavý review a `FakeCodeRunner.commits` mají 3 zprávy v pořadí plan → revise → document.
   - Doplňkový test: testy `[False, False, False]` → `accepted is False`, `exit_code == 1`, poslední fáze je `fix_3` a nic se necommituje po `commit_plan`.
5. **`test_workflow_harness_mix.py`**: fixture `tests/fixtures/workflows/mixed-harness.yaml`:
   ```yaml
   name: mixed-harness
   description: One run spread over three harnesses to prove each step picks its own
   steps:
     - plan: {harness: claude, model: opus, thinking: high}
     - build: {harness: codex, model: gpt-5.5}
     - review: {harness: pi, model: google/gemini-3.6-flash, thinking: low}
   accept: review.approved
   ```
   - `script.calls` odpovídá `[("claude","planner","opus","high"), ("codex","builder","gpt-5.5","medium"), ("pi","reviewer","google/gemini-3.6-flash","low")]`. `medium` je výchozí thinking agenta, protože ho krok nepřepisuje.
   - Envelope beze změny: z promptu codex volání vyřízni text mezi `PREV<<` a `>>PREV` a porovnej ho s `run.envelopes["plan"].model_dump_json(indent=2)`. Totéž udělej pro pi volání a `envelopes["build"]`. Navíc `PlanOutput.model_validate_json(vyříznuto) == PlanOutput.model_validate(to, co vrátil claude fake)`.
   - Po běhu mají agenti v `cfg` zase `claude/sonnet/medium` (restore).
   - Varianta, kdy `preflight` odmítne model: `FakeHarness.resolve_model` pro `codex` vyhodí `ValueError`. Výsledkem je `WorkflowError` s kódem `invalid_agent` a žádné volání harnessu.
6. **`test_cli_workflow.py`**
   - `main(["workflow","check", <simple-sdlc>])` vrátí 0 a stdout začíná `OK: simple-sdlc`.
   - S `--json` je `ok: true` a `steps` obsahuje harness a model z mixed fixture.
   - Chybný soubor vrátí 1 a JSON s `errors[*].code`.
   - Pro neexistující soubor je kód `missing_file`.
   - Do `test_cli.py` parametrizace přidej `"workflow"`.

## Pořadí prací

1. `defaults/roles.yaml`, `roles.py` (`Issue`, `check_description`) a `test_roles.py`.
2. Parser a vyhodnocovač podmínek ve `workflow.py` a `test_conditions.py`.
3. Model workflow, `load_workflow`/`parse_workflow`, výchozí YAML a `test_workflow_load.py`.
4. `preflight`, `apply_override`/`restore`, `CodeRunner`/`EngineCodeRunner`, `run_workflow`, `workflow_fakes.py` a oba běhové testy.
5. CLI a `test_cli_workflow.py`.
6. `just test`, `just typecheck`, `just lint`. Posuzuj podle exit statusu, ne podle textu výstupu.

## Ověření

- `just test` projde, včetně nových testů. Žádný test nespouští `claude`, `codex`, `pi` ani síť.
- `just typecheck` a `just lint` projdou.
- `just proto workflow check prototype/src/haifa_proto/defaults/workflows/simple-sdlc.yaml --json` vrátí exit 0 a `"ok": true`.
- `git status vendor/` je čistý.
