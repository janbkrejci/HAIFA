# HAIFA-S01-T10: `factory check` — kontrola factory v repu a na stroji

## Cíl

Nový čtecí příkaz `factory check [--repo CESTA] [--offline] [--json]`. Zjistí stav instalace
factory v repu a vrátí seznam nálezů, rozdělený na **repo** (opravit a commitnout) a **stroj**
(opravit lokálně). Pravidla jsou registrovaná v seznamu skupin (`RULE_GROUPS`), takže O1
(onboarding) a P2 (přihlášení harnessů, knihovna) přidají skupinu bez změny CLI.

Kontrola **nic nezapisuje** do repa, do trace DB ani do domovského adresáře. Dočasné soubory
(prompty pro `preflight`, rozbalený backlog z base) patří jen do `tempfile.TemporaryDirectory()`
mimo repo. Neotevírá `TaskRunStore`. Nevolá `git fetch`.

## Kontext v kódu (co už existuje a co použít)

- `config/source.py`: `git()`, `repo_root()`, `resolve_commit()`, `WorktreeSource`, `CommitSource`.
- `config/status.py`: `config_changes(root, sha)` (D4), `change_warnings`.
- `config/run.py`: `worktree_base(root)`, `DEFAULT_BASE`.
- `config/loader.py`: `load_config(source)` → `FactoryConfig` nebo `ConfigError(issues)`;
  `write_prompts(config, dest)` → `SSSFConfig` s prompty na disku.
- `config/settings.py`: `CONFIG_FILE`, `parse_project_settings(text, label, issues)`,
  `load_local(root)`, `ProjectSettings` (`base`, `remote`, `git_provider`, `test_command`,
  `backlog_dir`, `worktrees_dir`).
- `harness/check.py`: `check_harness(name, agents) -> HarnessStatus`, `harnesses_in_config(cfg)`.
- `run/task.py`: `named_workflow(name, config, task_id)` (vyhazuje `TaskRunError` s kódem
  `unknown_workflow` / `invalid_workflow`), `DEFAULT_TEST_COMMAND = ("just", "test")`,
  `FACTORY_DATA_DIR = ".factory/data"`.
- `run/gitops.py`: `extract_backlog(root, sha, backlog_dir, dest)` (git archive do tmp).
- `backlog`: `load_backlog(root, settings)`, `check_backlog(backlog)`, `effective_workflow(task)`,
  `iter_nodes`, `Task` (`status` ∈ `todo|done|cancelled`).
- `workflow`: `preflight(workflow, cfg)` → `WorkflowError(issues)`.
- `providers/azure.py`: `PAT_ENV` (`AZURE_DEVOPS_EXT_PAT`) — při PAT se `az account show` nevolá.
- `cli.py`: `SUBCOMMANDS`, `_emit_ok`, `_emit_fail`, `_dispatch`; `skill/codes.py`: `_CODES`,
  `ISSUE_CODES`; `skill/skill.md` šablona; `tests/test_skill.py` skenuje `_emit_fail` v `cli.py`
  a vyžaduje, aby každý kód byl v `ERROR_CODES`.

## 1. `GIT_OPTIONAL_LOCKS=0` pro čtecí git volání konfigurace

`aifactory/src/aifactory/config/source.py`, funkce `git()`: předávej `subprocess.run(...,
env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})`. Tím `git diff <sha> -- .factory` v
`config_changes` (D4, používá i dashboard a `config status`) ani nová kontrola neobnovují index
a neberou `index.lock`, když v repu běží tasky. Přidej konstantu `READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}`
a krátký komentář v docstringu modulu. Všechna git volání nového modulu kontroly jdou přes tento
`git()` (nebo přes jeho variantu, která nevyhazuje — viz níže `git_try`).

Přidej do `source.py` pomocníka, který nevyhazuje:

```python
def git_try(root: Path, *args: str) -> str | None:
    """stdout of a read-only git call, or None when it fails."""
```
(implementuj přes `git()` a `except GitError: return None`).

## 2. Nový balíček `aifactory/src/aifactory/check/`

### `check/model.py`

```python
Scope = Literal["repo", "machine"]
Severity = Literal["error", "warning", "info"]
Action = Literal["init", "update", "config_commit", "config_pull"]
Install = Literal["none", "working_tree", "base"]

@dataclass(frozen=True)
class Finding:
    code: str
    scope: Scope
    severity: Severity
    message: str
    fix: str | None = None        # lidsky čitelný návod, co udělat
    action: Action | None = None  # opravný příkaz dashboardu/CLI, jinak None
    def to_dict(self) -> dict[str, Any]:  # přesně klíče code, scope, severity, message, fix, action

@dataclass(frozen=True)
class Rule:
    name: str
    run: Callable[[CheckContext], Iterable[Finding]]
    needs_install: bool = True    # False = běží i při install == "none"

@dataclass(frozen=True)
class RuleGroup:
    name: str                     # "repo", "machine"; O1/P2 přidají vlastní
    rules: tuple[Rule, ...]

@dataclass(frozen=True)
class CheckReport:
    repo: str; install: Install; base: str; commit: str | None
    remote: str | None; ahead: int | None; behind: int | None
    offline: bool; groups: tuple[str, ...]; findings: tuple[Finding, ...]
    backlog: dict[str, int]       # souhrn backlog issues po kódech (prázdný, když nebyl načten)
    @property ok -> bool          # žádný finding se severity "error"
    def counts(self) -> dict[str, int]  # {"error": n, "warning": n, "info": n} (vždy všechny 3 klíče)
    def to_json(self) -> dict[str, Any]:
        # {"repo","install","base","commit","remote","ahead","behind","offline","ok",
        #  "counts","groups","backlog","findings":[...]}
```

### `check/machine.py` — sonda stroje (injektovatelná kvůli testům)

```python
@dataclass(frozen=True)
class Probe:  # výsledek spuštění
    returncode: int; stdout: str; stderr: str

class Machine(Protocol):
    def which(self, program: str) -> str | None: ...
    def run(self, argv: Sequence[str], timeout: float = 15) -> Probe | None: ...  # None = OSError/timeout
    def env(self, name: str) -> str | None: ...
    def harness(self, name: str, agents: list[str]) -> HarnessStatus: ...

class SystemMachine:  # shutil.which, subprocess.run(env=operator_env(), capture_output, text,
                      # check=False, stdin=DEVNULL), os.environ.get, harness.check.check_harness
```

`run` nikdy nepoužívej pro git. Testy podstrčí `FakeMachine`; žádný test nespustí `gh`, `az`
ani harness.

### `check/context.py` — líně počítaný kontext

```python
class CheckContext:
    def __init__(self, main: Path, *, offline: bool, machine: Machine) -> None
    main: Path            # hlavní checkout (viz níže)
    offline: bool
    machine: Machine
    # functools.cached_property:
    base: str             # worktree_base(main)
    commit: str | None    # git_try rev-parse --verify --quiet f"{base}^{{commit}}"
    install: Install      # "base" když CONFIG_FILE je v ls-tree commitu;
                          # jinak "working_tree" když (main/CONFIG_FILE).is_file(); jinak "none"
    base_config: FactoryConfig | None ; base_issues: tuple[ConfigIssue, ...]
                          # load_config(CommitSource(main, base, commit)) při install == "base"
    worktree_config: FactoryConfig | None ; worktree_issues: tuple[ConfigIssue, ...]
                          # load_config(WorktreeSource(main)) když CONFIG_FILE existuje na disku
    settings: ProjectSettings
                          # parse_project_settings z textu config.yaml v base, jinak z pracovního
                          # stromu, jinak ProjectSettings(); chyby parsování se tu ignorují
    roster: SSSFConfig | None   # base_config.agents, jinak worktree_config.agents, jinak None
    test_argv: tuple[str, ...]  # settings.test_command or DEFAULT_TEST_COMMAND
    base_backlog: Backlog | None  # extrahováno z commitu do tmp, load_backlog(tmp, settings);
                          # tmp adresář drží kontext a uklidí ho `close()` (kontext je context manager)
    def base_file(self, rel: str) -> str | None  # git_try cat-file blob f"{commit}:{rel}"
    def base_has(self, rel: str) -> bool         # git_try cat-file -e
```

Hlavní checkout: `repo_root(start)`, pak `git worktree list --porcelain` a první řádek
`worktree <cesta>` (to je hlavní checkout i když `--repo` míří do linked worktree). Když to
selže, použij `repo_root`. `ConfigError` z `repo_root` = složka není git repo → `NotARepository`
(vlastní výjimka v `check/__init__.py`), CLI vrátí 2.

Pozor: nepoužívej `load_run_config` (vyhazuje na první chybě); skládej z dílů výše.

### `check/repo_rules.py` — skupina `repo`

Každé pravidlo je funkce `(ctx) -> Iterable[Finding]`, všechny se `scope="repo"`.
Kódy (musí být přesně tyto a v `ISSUE_CODES["check"]`):

| pravidlo | kód | severity | action | kdy |
|---|---|---|---|---|
| install (`needs_install=False`) | `factory_missing` | error | `init` | `install == "none"` |
| | `config_not_committed` | error | `config_commit` | `install == "working_tree"` a base existuje |
| base | `base_missing` | error | None | `commit is None` (base neodkazuje na commit; i prázdné repo). Fix: vytvořit větev / nastavit `base` |
| checkout | `checkout_not_on_base` | warning | None | `git symbolic-ref -q HEAD` v hlavním checkoutu ≠ `refs/heads/<base>` (nebo detached). Zpráva uvede aktuální větev |
| remote | `remote_missing` | warning | None | `git_provider != "local"` a `settings.remote` není v `git remote` |
| | `remote_base_missing` | info | None | remote je, ale `refs/remotes/<remote>/<base>` neexistuje (asi nebyl fetch) |
| | `base_behind_remote` | warning | `config_pull` | `git rev-list --left-right --count <commit>...refs/remotes/<remote>/<base>` → behind > 0 |
| | `base_ahead_of_remote` | warning | None | ahead > 0; fix: `git push <remote> <base>` |
| config | `base_config_invalid` | error | `config_commit` když `worktree_config` je platná a `config_changes` není prázdné, jinak None | jeden finding na každou `ConfigIssue` z base (`f"{issue.path}: {issue.message}"`) — tím je pokrytý i chybějící prompt |
| | `worktree_config_invalid` | warning | None | jeden na každou issue z pracovního stromu (běhy ji nevidí, ale po commitu by rozbila base) |
| | `config_uncommitted` | warning | `config_commit` | jeden na `ConfigChange` z `config_changes(main, commit)`; text z `change_warnings` |
| | `base_setting_mismatch` | warning | None | `base_config.settings.base != ctx.base` |
| backlog | `backlog_missing` | warning | None | backlog v base nemá `backlog_dir` (issue `missing_backlog_dir`) |
| | `backlog_invalid` | error | None | jeden finding na každý **kód** z `check_backlog(base_backlog)` (kromě `missing_backlog_dir`): `"{n}× {code} in {base}, e.g. {path}: {message}"`; fix: `factory backlog check`, opravit, `factory backlog commit` |
| workflows | `workflow_unset` | warning | None | tasky se `status == "todo"` bez workflow (vypiš max 5 id + počet) |
| | `workflow_unknown` | error | None | `named_workflow` → `TaskRunError("unknown_workflow")`; zpráva uvede workflow a tasky |
| | `workflow_invalid` | error | None | `TaskRunError("invalid_workflow")` nebo `preflight` → `WorkflowError`; zpráva s issues |
| test | `justfile_missing` | error | None | `test_argv[0] == "just"` a v base není `justfile`, `Justfile` ani `.justfile` (v kořeni) |
| | `test_recipe_missing` | error (warning, když justfile obsahuje `import`/`mod`) | None | recept `test_argv[1]` (první argument nezačínající `-`; když chybí, první recept — tj. jen ověř, že nějaký recept existuje) není v justfile z base |
| | `test_script_missing` | error | None | `test_argv[0]` obsahuje `/`, není absolutní a v base neexistuje |
| gitignore | `gitignore_missing` | warning | `update` | jeden na každý chybějící runtime záznam v `.gitignore` z base |

Workflow pravidlo: jen když `base_config` a `base_backlog` jsou načtené. Názvy workflow = distinct
`effective_workflow(task)` pro `Task` se `status == "todo"` (řetězec, neprázdný). Pro každý jednou:
`named_workflow(name, base_config, first_task_id)`, pak v jednom `TemporaryDirectory()`
`cfg = write_prompts(base_config, Path(tmp))` a `preflight(workflow, cfg)`. (Nepoužívej
`prepare_cfg` — potřebuje `RunConfig` a `local.yaml`; pro preflight stačí roster s prompty.)

Recepty justfile: parsuj text z base. Recept = řádek bez úvodní mezery, ne `#`, ne `[attr]`,
regex `^@?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\b[^:=]*:(?!=)`; plus `alias NAME := ...`
(`^alias\s+(?P<name>[A-Za-z_][\w-]*)\s*:=`). Řádky `set ...:=` a `x := ...` (proměnné) nejsou
recepty (regex `:(?!=)` je vyřadí). Funkci dej jméno `justfile_recipes(text) -> set[str]` a
otestuj ji přímo (vč. `test *ARGS: web-test`, `@demo:`, `alias t := test`, `config := ...`).

`.gitignore` záznamy (vzorky cest): `.factory/local.yaml`, `.factory/trace.db` a
`.factory/trace.db-wal` (jen když `trace_db` z `load_local` je relativní a uvnitř repa; při chybě
`load_local` použij výchozí `.factory/trace.db`), `<worktrees_dir>/x`, `.factory/data/x`.
Řádek `.gitignore` (bez komentářů a `!`, oříznutý, bez úvodního `/`) pokrývá vzorek, když
`line.endswith("/") and sample.startswith(line)` nebo `fnmatch.fnmatchcase(sample, line)` nebo
`sample.startswith(line.rstrip("/") + "/")`. Hlásí se záznam (např. `.factory/trace.db*`), ne
vzorek. Bez `.gitignore` v base chybí všechny.

### `check/machine_rules.py` — skupina `machine`

Všechny se `scope="machine"`.

| pravidlo | kód | severity | action | kdy |
|---|---|---|---|---|
| harnesses | `harness_missing` | error | None | pro `harnesses_in_config(ctx.roster)`: `machine.harness(name, agents)` není `ok`; zpráva: harness, binárka, chyba, agenti; fix: nainstalovat nebo nastavit `CLAUDE_CODE_PATH`/`CODEX_PATH`/`PI_PATH` |
| just (`needs_install=False`) | `just_missing` | error, když `test_argv[0] == "just"`, jinak warning | None | `machine.which("just") is None` |
| test program | `test_program_missing` | error | None | `test_argv[0]` bez `/` a ≠ `just` a `machine.which` ho nenajde; absolutní cesta: `machine.which(path)` |
| local | `local_config_invalid` | warning | None | `load_local(main)` vyhodí `ConfigError` (jeden finding na issue) |
| hosting (`git_provider == "github"`) | `gh_missing` | error | None | `which("gh") is None` |
| | `gh_not_logged_in` | error | None | ne offline a `run(["gh","auth","status","--hostname","github.com"])` vrátí ≠ 0 nebo None; fix `gh auth login` |
| hosting (`azure`) | `az_missing` | error | None | `which("az") is None` |
| | `az_devops_missing` | error | None | `run(["az","extension","show","--name","azure-devops","--output","json"])` ≠ 0 |
| | `az_not_logged_in` | error | None | ne offline, `env(PAT_ENV)` prázdné a `run(["az","account","show","--output","json"])` ≠ 0 |
| | `hosting_skipped` | info | None | `--offline` a provider ≠ `local`: přihlášení se neověřovalo |

`--offline` vynechá jen volání hostingu (`gh auth status`, `az account show`); `which` a
`az extension show` (lokální) běží dál. Pravidla hostingu a harnessů běží jen při `install != "none"`
(bez konfigurace není provider ani roster).

### `check/__init__.py` — registr a spuštění

```python
RULE_GROUPS: list[RuleGroup] = [REPO_GROUP, MACHINE_GROUP]   # O1/P2: RULE_GROUPS.append(...)

class NotARepository(Exception): ...

def default_machine() -> Machine: return SystemMachine()

def run_check(repo: Path, *, offline: bool = False, machine: Machine | None = None,
              groups: Sequence[RuleGroup] | None = None) -> CheckReport:
```

`run_check` čte `RULE_GROUPS` při volání (ne při importu), aby se přidaná skupina projevila.
Pořadí nálezů = pořadí skupin a pravidel. Při `install == "none"` běží jen pravidla s
`needs_install=False`. Každé pravidlo je obalené: `ConfigError`, `GitError`, `OSError`,
`RuntimeError` → finding `check_failed` (severity warning, scope podle skupiny: `repo` →
`repo`, jinak `machine`; zpráva `f"{rule.name}: {exc}"`). Ostatní výjimky propadnou (CLI je s
`--json` zabalí do `internal_error`).

Do `CheckReport` doplň `remote`, `ahead`, `behind` (z pravidla remote — spočítej je v kontextu
jako cached property `ahead_behind: tuple[int, int] | None`) a `backlog` (počty kódů).

## 3. CLI (`aifactory/src/aifactory/cli.py`)

- `SUBCOMMANDS`: přidej `("check", "check that factory will run in this repo and on this machine")`
  (hned za `task`, `backlog`… pořadí libovolné, dej ho na začátek). V `build_parser`
  `elif name == "check": _add_check_command(child)`; `_dispatch`: `if command == "check": return _check(args)`.
- `_add_check_command`: `description` popíše: jen čte; nálezy `{code, scope, severity, message,
  fix, action}`; `scope` repo = opravit a commitnout, machine = opravit lokálně; `action` ∈
  init/update/config_commit/config_pull nebo null; stav instalace none/working_tree/base;
  exit 0/1/2; ahead/behind jen z lokálních refů (žádný fetch). Argumenty `--repo PATH`,
  `--offline` (`store_true`, help: "skip calls to the hosting (gh auth status, az account show)"),
  `--json`.
- `_check(args)`:
  - `run_check(Path(args.repo) if args.repo else Path.cwd(), offline=args.offline)`;
    `NotARepository` → `_emit_fail("not_a_repository", message, exit_code=2, path=...)` /
    text na stderr a 2.
  - JSON: `report.ok` → `_emit_ok(report.to_json())`; jinak
    `_emit_fail("checks_failed", f"{n} error(s): {kódy}", exit_code=1, data=report.to_json())`.
    Varování nedávej do `warnings` envelope (jsou ve `findings`).
  - Text: `install: base (main @ abc1234)`, pak řádek na nález
    `f"{severity:<7} {scope:<7} {code}: {message}"` a `       fix: ...` (`[action]`), na konec
    souhrn `N error(s), N warning(s), N info`. Návrat 0/1.
- Aktualizuj docstring modulu (seznam příkazů).

## 4. Kódy a skill

`aifactory/src/aifactory/skill/codes.py`:
- `_CODES`: `("checks_failed", "1", "factory check found errors; see data.findings")` (do
  sekce „Results of a command that ran“) a `("not_a_repository", "2", "the folder is not a git repository")`.
- `ISSUE_CODES["check"] = (...)` — všechny kódy nálezů z tabulek výše + `check_failed`.

`aifactory/src/aifactory/skill/skill.md`: do „Calling convention“ odrážku „Start with
`factory check --json`…“ a v `## Procedures` nová první sekce `### Check` (před `### Plan -> backlog`):
co vrací (`install`, `findings`, `scope`, `severity`, `action`), co dělat s `repo` vs `machine`,
`--offline`, že ahead/behind je z posledního fetch, exit kódy 0/1/2. Nepopisuj postup instalace
(HAIFA-S04-T02) ani opravné příkazy jako existující CLI — jen že `action` je jméno opravy.
Do bloku „What to do with the common ones“ přidej `checks_failed`.

## 5. Testy (`aifactory/tests/check/`)

Názvy souborů musí být v celé sadě unikátní (testy nemají `__init__.py`): helper
`factory_check_repo.py`, testy `test_factory_check.py`, `test_factory_check_cli.py`,
`test_justfile_recipes.py`. Repa stav pomocí `config_repo` (`make_repo`, `write`, `commit_all`,
`git`) — import `from config_repo import ...` funguje díky `pythonpath = ["tests"]`? Pozor:
`pythonpath` obsahuje jen `tests`, ne `tests/config`; ověř, jak to dělají ostatní testy (`grep -rn
"import config_repo\|from config_repo" aifactory/tests`). Pokud se nedá importovat, napiš si
vlastní minimální helper v `factory_check_repo.py` (git s `GIT_CONFIG_GLOBAL=os.devnull`,
`user.name`, `commit.gpgsign=false`).

Výchozí testovací repo: `.factory/` jako v `config_repo.FILES`, `test_command` nenastavený (→ `just
test`), `justfile` s receptem `test:`, `.gitignore` se všemi runtime záznamy, backlog s jedním
projektem/krokem/taskem `status: todo` a `workflow: plan-build`, vše commitnuté na `main`.
`FakeMachine(present={"just","claude","gh"}, logged_in=True)` vrací `HarnessStatus` s `path`/
`version` pro přítomné harnessy a zaznamenává volání `run` (pro ověření `--offline`).

Případy (každý ověří `code`, `scope`, `severity`, `action`):
1. Plně v pořádku → `install == "base"`, žádný error, `ok`.
2. Repo bez factory (jen commit README) → `install == "none"`, `factory_missing` (repo, error, `init`), žádné repo nálezy kromě něj.
3. Konfigurace jen v pracovním stromu (necommitnutá) → `install == "working_tree"`, `config_not_committed` s `config_commit`.
4. Neplatná konfigurace v base (např. `git_provider: nope` commitnuté) → `base_config_invalid` error.
5. Chybějící prompt v base (smazat `.factory/prompts/builder/user.md` a commitnout) → `base_config_invalid` se zprávou obsahující `missing prompt`.
6. Necommitovaná změna promptu → `config_uncommitted` warning `config_commit`.
7. Backlog s problémy v base (dva tasky se stejným id, neznámý `depends_on`) → `backlog_invalid` po kódech (`duplicate_id`, `unknown_ref`).
8. Task s neznámým workflow → `workflow_unknown`; workflow s neznámým agentem → `workflow_invalid`.
9. Justfile bez receptu `test` → `test_recipe_missing`; bez justfile → `justfile_missing`.
10. `test_command: [nosuchprog, -q]` → `test_program_missing` (machine, error).
11. Chybějící harness (`FakeMachine` bez `claude`) → `harness_missing` (machine, error).
12. `just` chybí → `just_missing` error.
13. Zpoždění za remote: holý klon jako remote (`git init --bare`, push, druhý commit do remote přes
    jiný klon, ve zkoumaném repu `git fetch` v testu — fetch dělá test, ne kontrola) →
    `base_behind_remote` warning `config_pull`, `behind == 1`; náskok → `base_ahead_of_remote`.
14. `--offline` s `git_provider: github` → žádné volání `gh auth status` ve `FakeMachine.calls`,
    `hosting_skipped` info; bez `--offline` a nepřihlášeném gh → `gh_not_logged_in`.
15. Checkout na jiné větvi → `checkout_not_on_base`.
16. `.gitignore` bez `.factory/local.yaml` → `gitignore_missing` warning `update`.
17. Přidaná skupina: `monkeypatch` na `aifactory.check.RULE_GROUPS` (append skupiny s jedním
    pravidlem) → její nález je ve výstupu `factory check --json` a `groups` ji obsahuje.
18. Nezměněné repo: před a po `run_check` porovnej `git status --porcelain=v1 -uall`, bajty
    `.git/index` (a jeho `st_mtime_ns`), `git for-each-ref`, existence `.git/index.lock` a seznam
    souborů v repu (`rglob`). Předtím `os.utime` na commitnutý soubor v `.factory/` (index je
    „stale“, bez `GIT_OPTIONAL_LOCKS=0` by `git diff` index přepsal). Ověř i, že nevznikl
    `.factory/trace.db`.
19. `GIT_OPTIONAL_LOCKS`: monkeypatch `subprocess.run` v `aifactory.config.source` zachytí `env`
    a ověří `env["GIT_OPTIONAL_LOCKS"] == "0"` (stačí jedno volání `config_changes`).

CLI testy (`run_json` z `cli_json`, `monkeypatch.chdir` nebo `--repo`, `monkeypatch.setattr(
"aifactory.check.default_machine", lambda: fake)`):
- OK repo → exit 0, `ok: true`, `data.findings` jsou dicty s přesně šesti klíči.
- S chybou → exit 1, `error.code == "checks_failed"`, `data.findings` vyplněné.
- `--repo` na ne-git složku (tmp_path) → exit 2, `not_a_repository`.
- Textový výstup bez `--json` vrací 1 a vypíše kód.

`test_skill.py`: přidej test, že každý literál prvního argumentu `Finding(` (AST, soubory
`src/aifactory/check/*.py`) je v `ISSUE_CODES["check"]` a naopak (žádný mrtvý kód). Proto v
pravidlech vytvářej nálezy vždy jako `Finding("kód", ...)` s literálem jako prvním pozičním
argumentem. Stávající `test_every_command_has_json` / `test_error_codes_complete` musí projít.

Testy nevolají síť ani model: žádný test nepoužije `SystemMachine` pro `gh`/`az`/harness.
Případný test `SystemMachine` jen s `which` na neexistující program.

## 6. Ověření

```
just test        # celá sada (spouští i web-test; frontend se nemění)
just typecheck   # mypy strict nad src a tests
just lint        # ruff check + ruff format --check
uv run --project aifactory factory check --json      # v tomto repu; ruční kontrola výstupu
uv run --project aifactory factory check --offline   # textový výstup
uv run --project aifactory factory --skill | grep -n "factory check"
```

## Mimo rozsah

Opravy (`init`, `update`, `config_commit`, `config_pull` jsou jen jména), onboarding (O1),
přihlášení harnessů a knihovna (P2), postup instalace ve skillu (HAIFA-S04-T02), dashboard,
sdílená trace DB, `git fetch`. `vendor/` a `prototype/` se nemění. Dokumentaci zapiš do
`app_docs/HAIFA-S01-T10-factory-check-kontrola-factory-v-repu-a.md` (stručně: příkaz, JSON,
kódy, jak přidat skupinu pravidel).
