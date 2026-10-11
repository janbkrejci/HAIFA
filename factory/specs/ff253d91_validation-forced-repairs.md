# Plán 2.17: validace v `aifactory` s vynucenými opravnými koly

## Cíl

Přenést `prototype/validation/` do `aifactory/validation/`, aby scénáře poháněly CLI `factory` místo `haifa-proto`. K tomu:

- vynutit opravné kolo test → fix skrytým testem,
- vynutit kolo review → revise pravidlem reviewera ve validačním rosteru,
- přidat scénáře **B1** (zápis do hlavního checkoutu) a **RESOLVE** (`task resolve`).

Recept je `just validate`. Prototyp (`prototype/`) a `vendor/` se **nemění**. Výchozí konfigurace produktu (`aifactory/src/aifactory/defaults/`, `engine/defaults/roles.yaml`) se také **nemění**: pravidla pro opravná kola žijí jen v `aifactory/validation/`.

## Co se liší proti prototypu (ověřeno v kódu)

| Téma | Prototyp | `aifactory` |
|---|---|---|
| CLI | `haifa_proto.cli.main` | `aifactory.cli.main` (`factory`). Každý `task`/`backlog` příkaz bere `--json --repo PATH`. |
| JSON | `{ok, run, pr, error}` na nejvyšší úrovni | Obálka `{"ok", "data", "error": {code,message,...}, "warnings": [...]}` (`skill/envelope.py`). Data `task run` jsou `{"run": TaskRunRow, "pr": TaskPrRow\|null, "pr_error", "chain"}`. `return` a `resolve` mají stejný tvar bez `chain`. `approve` vrací `{task_id, pr, merge_sha, strategy, reviewed, base_sha, removed_worktrees}`. Kód, který čte výstup, musí sahat do `data`. |
| Exit kódy | konflikt a `unmet_dependencies` dávaly 1 | `skill/codes.py`: `run_failed` a `pr_failed` dávají **1**. `conflict`, `unmet_dependencies`, `pr_not_open`, `merge_failed`, `unknown_task` a další dávají **2**. Kontroly R2, R3 a RESOLVE se musí přizpůsobit. |
| Roster | `.factory/sssf.config.yaml` s `coding_agent` a `prompt_engineering` | `.factory/agents.yaml` (`defaults:` a `agents: [{name, harness, model, thinking, writes}]`). **Bez** `prompt_engineering`. Prompty jsou povinně v `.factory/prompts/<agent>/{system,user}.md`. |
| Config projektu | `config.yaml` s `agents_config` a `require_review` | `ProjectSettings` (`config/settings.py`): `base`, `git_provider` (local\|github\|azure), `merge_strategy`, `remote`, `backlog_dir`, `specs_dir`, `docs_dir`, `levels`, `worktrees_dir`, `protected_files`. Jen tyto klíče. Zda nezná `require_review`, ověř v `settings.py`. |
| Odkud se config čte | pracovní strom | **Commit v `base`** (`config/run.py::load_run_config`). Necommitnutá změna dá jen `warnings`, proto se roster musí commitnout do base. |
| Trace DB | `.factory/data/sssf.db` | `.factory/trace.db` (`local.yaml`, výchozí). Sessions jsou v `.factory/data/sessions/<run_id>/`. Worktree je `.factory/worktrees/<run_id>`, větev `factory/<task>-<n>`. |
| Falešný harness | `HAIFA_VALIDATE_FAKE` + `validation.worker` | Neexistuje. Napiš vlastní `validation/fake.py` podle `tests/workflow/workflow_fakes.py::install_fake_harnesses`, ale bez `monkeypatch`: `aifactory.harness.install()`, pak pro `claude`, `codex` a `pi` `setattr(harness.load(n), "run", guard)` a `setattr(..., "resolve_model", fake.resolve_model)`. Nakonec `agents.INTERFACES[n] = fake` a `INTERFACES["claude_code"] = fakes["claude"]`. |
| Test fáze | `just test` | `engine/quality.py::run_tests` vždy spouští `just test` ve worktree s `operator_env()`, tedy s `os.environ` bez venv. Proměnné prostředí z validace se do `just test` dostanou. |
| Smyčky | YAML spustí `revise_2` i po posledním zamítnutí | `until` se kontroluje po každém kroku. Po posledním zamítnutí `revise_2` ani `fix_3` neběží (`workflow/interpreter.py`). |
| gh | `HAIFA_GH` | `AIFACTORY_GH` (`providers/github.py`). Validace ho používá i pro vlastní volání `gh`. |
| resolve | neexistuje | `factory task resolve ID` spustí `resolve.yaml`: `rebase` → `resolve` (role `resolve`, agent `builder`, `BuildOutput`, jen při `rebase.conflict`) → `test`. Pak commit a push s lease. |
| Guard | — | `run/guard.py::TaskWriteGuard`. Nová změna v hlavním checkoutu se vrátí (`roll_back`) a vyhodí se `PermissionBreach`. Do trace jde event `type='error', name='permission_breach'`, běh skončí `failed` a CLI vrátí `run_failed` (exit 1). **Gitignorované soubory guard nevidí.** |

## Struktura (nové soubory)

```
aifactory/validation/
  __init__.py  __main__.py  README.md (česky)
  runner.py  results.py  safety.py  sandbox.py  context.py  roster.py
  worker.py  fake.py  fake_scripts.py  scenarios.py  hidden.py
  template/        # sandbox pro aifactory (viz níže)
  rosters/pi-haiku/agents.yaml
  rosters/pi-haiku/workflows/simple-sdlc.yaml
  results/.gitkeep (nebo nic; výsledky se tvoří za běhu)
aifactory/tests/validation/
  test_validation_unit.py  test_validation_roster.py
  test_validation_template.py  test_validation_local.py
```

Soubory `results.py` a `safety.py` zkopíruj téměř beze změny. Do `RISKS` v `results.py` přidej:

- `"B1": "Agent zapíše mimo worktree do hlavního checkoutu"`
- `"RESOLVE": "Konflikt dvou PR nejde vyřešit bez ruční práce"`

Všude nahraď `haifa_proto` za `aifactory` a `proto-validate` za `validate`.

### Balení, lint a typy (`aifactory/pyproject.toml`)
- `[tool.pytest.ini_options] pythonpath = ["tests", "."]`, aby testy mohly `import validation`.
- `[tool.ruff] src = ["src", "tests", "validation"]`. Do `extend-exclude` dej `validation/template` (python sandboxu je cizí kód) a `validation/results`.
- `[tool.mypy] files = ["src", "tests", "validation"]` a `exclude = ["^validation/template/", "^validation/results/"]`. Kód validace musí projít `strict`.
- Validace se do wheelu nebalí. Spouští se z adresáře `aifactory` přes `python -m validation`.

### `justfile` (sekce aifactory)
```
# validation scenarios R1–R5, R10, RESOLVE, B1: just validate --remote local|github [--roster DIR]
validate *ARGS:
    cd aifactory && uv run python -m validation "$@"
```

### `.gitignore` (kořen)
Přidej `aifactory/validation/results/*/local-*/`. Výsledky z githubu se commitují.

## Šablona sandboxu `aifactory/validation/template/`

Zkopíruj `prototype/validation/template/` a uprav ji takto.

- **`.factory/config.yaml.tmpl`** (renderuje se `string.Template`): `base: $base`, `git_provider: $provider`, `merge_strategy: squash`, `remote: origin`, `backlog_dir: backlog`, `specs_dir: specs`, `docs_dir: app_docs`, `levels: [module, step, task]`. Žádné neznámé klíče. `require_review` a `agents_config` vyhoď, pokud je `settings.py` nezná. Musí projít `factory config show`.
- **`.factory/agents.yaml`** místo `sssf.config.yaml`:
  - `defaults: {thinking: low}`;
  - agenti `planner` (claude, sonnet, `writes: [specs/]`), `builder` (codex, gpt-5.5), `reviewer` (pi, stejný model jako prototyp, `writes: []`), `documenter` (claude, haiku, `writes: [app_docs/]`).
  - Klíč je `harness`, ne `coding_agent`. Formát ověř v `harness/config.py::load_config`.
- **`.factory/workflows/simple-sdlc.yaml`**: kopie `aifactory/src/aifactory/defaults/workflows/simple-sdlc.yaml`. Na krocích přidej `harness:` jako v prototypu: plan → claude, build/fix/revise → codex, review → pi. Komentář v hlavičce oprav (už žádný „revise_2 po posledním zamítnutí“).
- **`.factory/prompts/<agent>/{system,user}.md`** pro planner, builder, reviewer a documenter. Zdroj je `adws/adw_data/prompt_engineering/<agent>/` (stejné proměnné `{{prompt}}`, `{{previous_envelope}}`, `{{context_handoff_dir}}`). Kopíruje je `materialize()` jako v prototypu, včetně sentinel řádku v `user.md`.
- **`.gitignore`**: `.factory/data/`, `.factory/worktrees/`, `.factory/local.yaml`, `.factory/trace.db*`, `__pycache__/`, `*.pyc`.
- **`justfile`**: `test` spustí viditelné testy a potom skryté, pokud je nastavená proměnná (viz níže).
  ```
  test:
      python3 -m unittest discover -s tests -t . -q
      if [ -n "${HAIFA_VALIDATE_HIDDEN:-}" ]; then PYTHONPATH=src python3 -m unittest discover -s "$HAIFA_VALIDATE_HIDDEN" -t "$HAIFA_VALIDATE_HIDDEN" -q; fi
  ```
- **backlog**: stejné úkoly. Přidej úkol pro B1 `backlog/M01-core/S01-math/M01-S01-T03-sign.md` (`sign(x)` do `mathx.py`, `writes: [src/sandbox/mathx.py]`, `status: todo`). Frontmatter (`writes`, `depends_on`, `workflow` na modulu) musí projít `factory backlog check`. Pokud se formát liší, uprav ho podle `aifactory/src/aifactory/backlog/`.
- **`tests/test_cli.py`**: `GreetTest` porovnává s `f"Hello, {text.slugify('Jan Novák')}!"`, ne s literálem, aby nezávisel na skrytém požadavku. Zadání greet (`M02-S01-T01`) nech, jak je.

### Skrytý test (vynucené kolo test → fix)

Soubor `validation/hidden.py` obsahuje text skrytého testu a funkci `write_hidden(workdir) -> Path`. Ta zapíše `<workdir>/hidden/test_hidden_slugify.py`, tedy **mimo repo i worktree**, takže ho builder v prvním kole nemůže vidět ani odvodit.

Test:
```python
import unittest
from sandbox import text

@unittest.skipUnless(hasattr(text, "slugify"), "slugify is not there yet")
class HiddenSlugifyTest(unittest.TestCase):
    def test_empty_slug_gets_the_x_prefix(self) -> None:
        # hidden requirement, not derivable from the task: nothing sluggable -> "x-empty"
        self.assertEqual(text.slugify("!!!"), "x-empty")
        self.assertEqual(text.slugify(""), "x-empty")
```

Požadavek je zvolený tak, aby nerozbil `greet("Jan Novák")` ani viditelné testy (`hello-world` a diakritika). `Context` nastaví `HAIFA_VALIDATE_HIDDEN=<workdir>/hidden` do prostředí **každého** příkazu `factory` v obou režimech. Test fáze ho zdědí přes `operator_env()`. Běhy před slugify ho přeskočí. Hlavní checkout bez proměnné spouští jen viditelné testy.

### Validační reviewer (vynucené kolo review → revise)

V `template/.factory/prompts/reviewer/user.md` (a v `system.md`) je za převzatý text přidaná sekce:

```
## Validation rule (haifa-validate)

This repository is a validation sandbox. The first review round of every run
always rejects: you are in the first round exactly when none of the files in
`previous_envelope.changed_files` contains the line `# haifa-validate: revised`.
Then return `approved: false` with exactly one `blocking` item:
"Add the line `# haifa-validate: revised` at the end of <the first changed source file>."
and one unmet finding for it. When the line is present, review normally.
```

- Konstanta `REVIEW_RULE_MARKER = "# haifa-validate: revised"` je ve `fake_scripts.py` a čtou ji scénáře i testy.
- Pravidlo je jen v šabloně validace. Roster z `--roster DIR` mění `agents.yaml` a workflow, prompty s pravidlem zůstávají.
- Test hlídá, že řetězec `haifa-validate` není nikde v `aifactory/src/`.

## Falešný harness a skripty (`fake.py`, `fake_scripts.py`, `worker.py`)

- **`worker.py`**: `python -m validation.worker <factory argv>`. Když je nastavené `HAIFA_VALIDATE_FAKE=<script.json>`, nejdřív zavolá `fake.install(path)`, pak `aifactory.cli.main(argv)`.
- **`fake.py`** přenes z prototypu s těmito změnami:
  - `AgentResult` je z `aifactory.engine.data_types`.
  - Instalace podle `install_fake_harnesses`: guard na `run` a `resolve_model` přesměrovaný na fake.
  - `apply_edits` přijme i **absolutní** `path`. Ten se zapíše přesně tam (pro B1 do hlavního checkoutu). Relativní cesta je vůči `request.cwd`.
  - Agent se bere z `Path(request.session_dir).parent.name`. Ověř, že v aifactory platí (`workflow_fakes.py` to tak dělá).
  - Záznam volání jde do `<script>.calls.jsonl` a do `raw_output_path`.
- **`fake_scripts.py`**:
  - Každý skript má reviewera `[reject, approve]` a builderovi přidá položku **revise**. Ta připíše `REVIEW_RULE_MARKER + "\n"` na konec prvního souboru z `writes` úkolu (např. `src/sandbox/mathx.py`).
  - Zamítnutí vypadá takto: `{"status":"success","summary":"...","approved":false,"blocking":["Add the line `# haifa-validate: revised` at the end of <file>."],"findings":[{"requirement":"validation rule","met":false,"evidence":"marker missing"}]}`. Musí projít gatem `verdict_consistent`. Tvar `findings` ověř v `engine/data_types.py::ReviewOutput`.
  - Pořadí builderových položek: `build`, `[fix]`, `revise`.
  - **slugify (`slugify_with_repair`)**: `build` napíše verzi s diakritikou (`SLUGIFY_BODY_FIXED`), takže projdou viditelné testy a selže jen skrytý. `fix` nahradí `return "-".join(...)` za `slug = "-".join(...)` a `return slug or "x-empty"`.
  - **`truncate` / `return`**: skript běhu po `task return` má také reject/approve a revise.
  - **resolve** (`M01-S01-T02`, varianta `resolve`): jen `builder: [resolve]`. Ten zapíše celý `src/sandbox/mathx.py` s oběma funkcemi: text šablony `mathx.py`, `__all__ = ["clamp", "lerp"]`, `CLAMP`, `LERP` a oba markery revize, pokud je měly obě větve. Sestav ho z výsledku, ne ručně: přečti `TEMPLATE_DIR/src/sandbox/mathx.py` a aplikuj edity clamp, lerp a revise. Envelope `BuildOutput` s `changed_files: ["src/sandbox/mathx.py"]`. Soubor nesmí obsahovat konfliktní značky.
  - **B1 (`M01-S01-T03`, varianta `breach`)**:
    - planner je normální;
    - builder napíše legální změnu `mathx.py` a zároveň absolutní zápisy do hlavního checkoutu: nový soubor `<repo>/B1-breach.md` a `append` do sledovaného `<repo>/README.md`. Obojí je negitignorované.
    - `script_for(task, variant, repo=...)` dostane cestu hlavního checkoutu.
    - Reviewer a documenter se nezavolají; frontu jim nedávej, nebo ji nech prázdnou.

## `context.py`

Přenes a uprav:

- `TRACE_DB = ".factory/trace.db"`, `SESSIONS_DIR = ".factory/data/sessions"`.
- `Cmd`:
  - `ok = code == 0 and data.get("ok") is True`;
  - `error_code` z `data["error"]["code"]`;
  - `payload = data.get("data") or {}`;
  - `run` a `pr` čti z `payload`;
  - `warnings = data.get("warnings", [])`.
- `parse_stdout`: obálka se tiskne s `indent=2` na stdout, narrace jde na stderr. Stávající logika stačí.
- `_spawn`:
  - `PYTHONPATH` = adresář `aifactory` (`AIFACTORY_DIR`), `cwd = repo`, `argv + ["--repo", repo, "--json"]`;
  - vždy nastav `HAIFA_VALIDATE_HIDDEN`;
  - fake skript dostane každý příkaz v local režimu a navíc v githubu, když je `fake=True` (B1);
  - příkazy bez `--repo` (`harness check`) mají zvláštní cestu.
- `run_task(task_id, *extra, variant, fake=False)`.
- Trace dotazy (`phases`, `agent_starts`, `session_usage`, `phase_tokens`, `task_run`, `task_pr`) ověř proti schématu v `engine/tracer.py` a `run/store.py`. Názvy tabulek sedí: `sessions`, `phases`, `events`, `envelopes`, `task_runs`, `task_prs`.
- `test_passed(run_id, phase)`: zjisti, kam aifactory zapisuje výsledek test fáze (log event s `passed`, řádek v `envelopes`/`gate_results`, nebo `context_handoff/quality/NN_test/command.log`) a čti ho odtud. Přidej `test_output(run_id, phase) -> str` (výpis `command.log` té fáze) pro kontrolu skrytého testu.
- Přidej `envelope(run_id, phase) -> dict` (poslední obálka fáze z tabulky `envelopes`) pro `approved` u `review_1` a `review_2`.
- `catch_up_base`, `task_in_base` a `status_in_base` zůstávají.

## `sandbox.py` a `roster.py`

- Konstanty: `VALIDATION_DIR`, `AIFACTORY_DIR = VALIDATION_DIR.parent`, `HAIFA_ROOT = AIFACTORY_DIR.parent`.
- `gh_executable()` čte `AIFACTORY_GH`.
- `materialize` kopíruje prompty do `.factory/prompts/`.
- `setup_local` a `setup_github` zůstávají. Git config `commit.gpgsign false` v sandboxu.
- `ROSTER_FILES = (("agents.yaml", ".factory/agents.yaml"), ("workflows/simple-sdlc.yaml", ".factory/workflows/simple-sdlc.yaml"))`. `resolve_roster` hlásí chybějící soubory a navíc zkontroluje, že roster má agenty `planner`, `builder`, `reviewer` a `documenter`. Když nemají, je to `SetupError`.
- `step_harnesses(repo)`:
  - workflow načti přes `aifactory.workflow` (parse + role registry: `parse_workflow(yaml, load_roles())`);
  - `walk()` vrací `RoleStep` s `.harness` a `.role.agent`; ověř v `workflow/model.py`;
  - harness agenta vezmi z `harness.config.load_config(repo/.factory/agents.yaml)`;
  - aliasy normalizuj přes aifactory (hledej `ALIASES` v `aifactory/harness`).
  - Do `harnesses` dej i id kroků `resolve` z `resolve.yaml`, pokud je to jednoduché. Jinak stačí `simple-sdlc`.
- Nový roster `validation/rosters/pi-haiku/`: `agents.yaml` s `defaults: {harness: pi, model: nousresearch/stealth/space-bunny-alpha, thinking: low}`, planner a documenter na claude haiku. `workflows/simple-sdlc.yaml` je stejný jako v šabloně, ale bez `harness:` codex, nebo s `harness: pi`. Obsah přenes z prototypu.

## `runner.py`

Stejný jako v prototypu:

- přepínače `--remote`, `--results-dir` (výchozí `aifactory/validation/results`), `--workdir`, `--keep-workdir`, `--only`, `--roster`, `--r5-samples`;
- stejné exit kódy 0, 1 a 2;
- stejný `summary.json` se všemi klíči prototypu.

Změny:

- `prog="just validate"`.
- Preflight githubu: `factory harness check --json --config <roster nebo template>/agents.yaml` přes worker bez faku. Ověř v `cli.py`, že `--config` bere agents YAML. Obálka musí mít `ok` true.
- Před scénáři zavolej `hidden.write_hidden(workdir)` a cestu dej do `Context`.
- `copy_trace` kopíruje `.factory/trace.db` do `trace/sssf.db` (název výstupu zůstává kvůli shodě s prototypem), dál sessions a logy. Výstupní adresář `results/<datum>/<remote>-<HHMMSS>/` se nemění.
- `--only` zná `R1, R10, R2, RESOLVE, R3, R4, R5, B1` (velká písmena).

## Scénáře (`scenarios.py`)

Pořadí `ORDER`: **R1, R10, R2, RESOLVE, R3, R4, R5, B1**.

Očekávané fáze v local režimu (každý běh má vynucené kolo review):

```
FORCED_REVIEW_HAPPY = ("request"?, "plan", "commit_plan", "build", "test_1",
  "review_1", "revise_1", "review_2", "retest", "commit_build", "changes",
  "document", "commit_docs")
```

Přesný seznam (je tam engineer fáze `request`? jak se jmenuje retest?) ověř jedním lokálním během. Pomůže i `tests/workflow/test_default_workflows_run.py`. Seznam pak zapiš jako konstantu. `EXTRA_PHASE` pro github zůstává.

Společná funkce `_review_round_checks(ctx, res, run_id)` přidá tyto kontroly:

- `review_1_rejected`: obálka `review_1` má `approved` false;
- `revise_ran`: fáze `revise_1` existuje a je `success`;
- `review_2_approved`: obálka `review_2` má `approved` true;
- `review_rule_in_prompt`: vyrenderovaný `sessions/<run>/reviewer/prompts/user.md` obsahuje `REVIEW_RULE_MARKER`.

Na githubu, kde rozhoduje skutečný model: když `review_1` schválí, výsledek je `inconclusive` s vysvětlením, ne `failed`.

- **R1** (`M02-S01-T02`, `--version`):
  - kontroly jako v prototypu, s pořadím fází `FORCED_REVIEW_HAPPY`;
  - navíc `_review_round_checks`;
  - v měřeních `review_rounds`;
  - roster gap dává `inconclusive`;
  - observation o rozdílu YAML a Pythonu přepiš: aifactory `revise_2` po posledním zamítnutí nespustí.
- **R10** (`M01-S02-T01`, `slugify_with_repair`):
  - `test_failed_first` (`test_1` passed je False);
  - nová kontrola `hidden_test_failed_first`: výstup `test_1` obsahuje `HiddenSlugifyTest` nebo `x-empty`;
  - `fix_ran_on_codex` a `same_session` jen s codexem, jinak roster gap;
  - `test_passed_after_fix`;
  - `_review_round_checks`;
  - v githubu `thread_resumed` jako dřív.
  - Když na githubu `fix` neproběhl, je to `inconclusive` (se skrytým testem by nemělo nastat).
- **R2** (`clamp`, `lerp` paralelně): jako v prototypu. `second_reports_conflict` je `approve2.code == 2 and error_code in ("conflict",)`, na githubu i `merge_failed`, a base se nezmění. Do `ctx.state["R2"]` ulož druhý úkol a jeho PR pro RESOLVE. Observation o chybějícím resolve smaž.
- **RESOLVE** (nový; potřebuje `ctx.state["R2"]` s konfliktem, jinak `inconclusive`):
  1. `ctx.catch_up_base()`; `cmd = ctx.haifa("task", "resolve", second, task=second, variant="resolve")`. Kontrola `resolve_ok`: `cmd.ok` a `run.state == "succeeded"`.
  2. Kontrola `resolve_phase_ran`: fáze runu obsahují `rebase`, `resolve` (success) a `test` (passed). V local režimu musí `resolve` proběhnout. Na githubu, pokud rebase konflikt nehlásil, `resolve` chybí a to je jen observation.
  3. Kontrola `no_conflict_markers`: `git show <head_sha>:src/sandbox/mathx.py` neobsahuje `<<<<<<<`.
  4. `approve = ctx.haifa("task", "approve", second)`. Na githubu opakuj až 6× po 10 s, dokud je `error_code == "merge_failed"` (mergeability). Kontrola `second_merged`.
  5. Kontrola `both_prs_merged`: `task_pr(branch).state == "merged"` u obou větví z R2 a `status_in_base == "done"` u obou úkolů.
  6. Kontrola `base_has_both`: `mathx.py` v `origin/<base>` obsahuje `def clamp` i `def lerp`. V local režimu navíc `just test` v čistém checkoutu base (`git worktree add` do `workdir/resolve-check`, `check_inside`, a pak odstranit) projde.
  - Evidence: run id resolve, PR a `merge_sha`.
- **R3**: jako v prototypu. `dependency_blocks` očekává **exit 2** a `unmet_dependencies`. `approve_refused` očekává exit 2 a `pr_not_open`. Tvary dat `task show --json` (`prs`) a `backlog sync --json` (`updated`, `commit`) ověř v `cli.py` a čti z `payload`. Běh po `task return` má také reject/revise (skript `return`).
- **R4**: config se teď čte z base, proto se kontroly mění:
  - `tree_dirty` pro `.factory/prompts/planner/user.md` a `.factory/agents.yaml` (přidej `thinking: high` k planneru; kotvu uprav podle nového `agents.yaml`);
  - `prompt_change_invisible` jako dřív;
  - **nově** `config_change_invisible`: `agent_start` fáze `plan` nemá `thinking == "high"`;
  - `uncommitted_warning`: `cmd.warnings` není prázdné a zmiňuje necommitnutou konfiguraci.
  - Observation o „nekonzistenci pro 1.10“ nahraď: D4 je vyřešené.
  - Úklid ve `finally` zůstává.
- **R5**: beze změny. Worktree jsou v `.factory/worktrees`.
- **B1** (nový; běží s falešným harnessem **v obou režimech**, `fake=True`; na githubu to zapiš jako observation: guard je kód, model ho nepotřebuje):
  1. `ctx.catch_up_base()`; `before = git status --porcelain` hlavního checkoutu.
  2. `cmd = ctx.run_task("M01-S01-T03", variant="breach", fake=True)`. Kontrola `run_failed`: `cmd.code == 1`, `error_code == "run_failed"` a `run.state == "failed"`.
  3. Kontrola `breach_reported`: `run.error` (nebo `error.message`) zmiňuje `B1-breach.md`.
  4. Kontrola `write_reverted`: `<repo>/B1-breach.md` neexistuje, `README.md` má obsah jako v HEAD a `git status --porcelain` se rovná `before`.
  5. Kontrola `phase_failed`: fáze `build` není `success` a trace má event `type='error' AND name='permission_breach'` pro run.
  6. Kontrola `no_pr`: `cmd.pr` je prázdné a base se nezměnila (`base_commits` před a po).
  - Evidence: run id a `trace/sessions/<run>`.

## Testy (`aifactory/tests/validation/`)

Všechny bez sítě a bez modelu. Přenes testy prototypu a uprav je.

- **`test_validation_unit.py`** (port prototypu):
  - `safe_rmtree`, `normalize_repo`, github bez `HAIFA_SANDBOX_REPO` dává exit 2 před subprocesem, `--only` odmítne neznámé, pravidlo outcome, tvar result JSON, `output_dir`, `parse_stdout`;
  - `fake.install` hlídá skutečné adaptéry (obnov je ve fixture přes `monkeypatch`, aby testy neovlivnily další testy);
  - fake aplikuje edity **včetně absolutní cesty**;
  - `Cmd` čte `data`, `error.code` a `warnings`.
- **`test_validation_roster.py`**:
  - `step_harnesses` šablony (plan=claude, build/fix/revise=codex, review=pi);
  - `resolve_roster` vyžaduje oba soubory i všechny čtyři agenty a relativní cesta se bere od kořene HAIFA;
  - `apply_roster`;
  - pravidlo roster gap;
  - failed dává exit 1, inconclusive exit 0;
  - e2e `just validate --remote local --roster aifactory/validation/rosters/pi-haiku --only R1,R10`: R1 a R10 jsou `inconclusive` nebo `passed`, nikdy `failed`, a `summary.roster` je vyplněný.
- **`test_validation_template.py`**:
  - materializovaná šablona projde `factory backlog check --json`, `factory workflow check .factory/workflows/simple-sdlc.yaml` a `factory config show`;
  - tvar backlogu včetně `M01-S01-T03`;
  - workflow jmenuje tři harnessy;
  - `config.yaml` je vyrenderovaný;
  - suite base je zelená bez `HAIFA_VALIDATE_HIDDEN` i s ní (slugify ještě neexistuje, test se přeskočí);
  - prompty nesou sentinel a reviewer prompt `REVIEW_RULE_MARKER`;
  - **`haifa-validate` se nevyskytuje v žádném souboru pod `aifactory/src/`**.
  - Skrytý test proti naivnímu slugify selže a proti opravenému projde: přímo přes unittest v `tmp_path`.
- **`test_validation_local.py`** (port):
  - `just validate --remote local --results-dir ... --workdir ...` s tripwire na `CODEX_PATH`, `CLAUDE_CODE_PATH`, `PI_PATH` a `AIFACTORY_GH`, s `UV_NO_SYNC=1`, bez `HAIFA_SANDBOX_REPO` a `HAIFA_VALIDATE_FAKE`, timeout 600;
  - exit 0 a všech 8 scénářů `passed`;
  - `summary.results` obsahuje všechny;
  - R2 `overlap_s > 0`;
  - R10 má kontroly `hidden_test_failed_first` a `test_failed_first` ok a `repair_rounds >= 1`;
  - R1 má `revise_ran` a `review_2_approved` ok;
  - RESOLVE má `both_prs_merged`;
  - B1 má `write_reverted`;
  - tripwire marker neexistuje a workdir je smazaný.
  - Skip, když `just` není na PATH.

## Dokumentace

`aifactory/validation/README.md` (česky): přenes README prototypu a aktualizuj:

- recept `just validate`;
- `agents.yaml` a `--roster DIR` (co nahrazuje a jaké agenty vyžaduje);
- 8 scénářů v tabulce včetně B1 a RESOLVE;
- skrytý test (proměnná `HAIFA_VALIDATE_HIDDEN`, soubor mimo repo);
- pravidlo reviewera (marker; jen ve validační šabloně, ne v produktu);
- odhad nákladů na githubu: každý běh má navíc revise a druhé review, přibývá RESOLVE;
- úklid po githubu: zavřít zbylé PR a smazat větve `factory/*` a `haifa-validate/*`.

## Postup a ověření

1. Kostra: `pyproject.toml`, `justfile` a `.gitignore`; zkopírovat `results`, `safety`, `sandbox` a `roster`; šablona.
2. `fake.py`, `worker.py`, `context.py`, `fake_scripts.py` a `hidden.py`.
3. Scénáře postupně přes `just validate --remote local --only R1 --keep-workdir`. Z trace zjisti přesná jména fází a jak číst výsledek testu a obálky reviewera (`sqlite3 <workdir>/repo/.factory/trace.db`). Pak R10, R2 + RESOLVE, R3, R4, R5 a B1.
4. Testy.
5. Musí projít, posuzuj podle exit kódu:
   - `just validate --remote local` (exit 0, žádný `failed`);
   - `just test`;
   - `just typecheck`;
   - `just lint` (včetně `ruff format --check`).
6. `git status`: `prototype/`, `vendor/` ani `aifactory/src/aifactory/defaults/` nejsou změněné. Výsledky z local běhu git ignoruje.

## Rizika a poznámky

- Zkontroluj, jestli `task resolve` v local provideru pushne do bare remote a jestli `approve` potom projde. Očekávaný tok je v `tests/run/test_task_resolve.py`.
- Paralelní běhy R2 jsou dva procesy nad jednou trace DB. Aifactory to podporuje (2.15, WAL).
- Běhů je víc, každý má navíc revise a retest, takže e2e test běží déle. Timeout testu 600 s. Pokud je sada výrazně pomalejší, dá se roster e2e omezit na `--only R1,R10` (už je).
- Guard nevidí gitignorované soubory. Zápisy B1 proto jdou do negitignorovaných cest.
