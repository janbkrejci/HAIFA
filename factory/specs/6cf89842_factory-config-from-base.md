# Plán 2.4: konfigurace `.factory/` z commitu v `base`

## Cíl

Nový balíček `aifactory.config` načte konfiguraci projektu z `.factory/`, a to buď z pracovního stromu (pro prohlížení a dashboard), nebo ze stromu commitu v `base` bez checkoutu (pro běh). Necommitnuté změny sdílené konfigurace proti `base` se hlásí jako varování, a to přes `factory config status [--json]` i v konfiguraci běhu (`RunConfig.warnings`). `.factory/local.yaml` se čte vždy jen z pracovního stromu.

Zdroje: `docs/product-brief.md`, sekce „Architektura“ a „Dashboard / Nastavení projektu“. Jako předloha (jen ke čtení, **neměnit**) poslouží `prototype/src/haifa_proto/config.py`.

## Mimo rozsah

- Commit konfigurace tlačítkem (dashboard, F4) a spouštění běhů (`task run`, 2.9). Úkol 2.9 jen zavolá `load_run_config()` a jeho `warnings` přepošle do výstupu.
- Validace workflow proti registru (2.7). Workflow se zde jen načtou jako YAML mapy.
- Změny ve `vendor/`, `prototype/`, `adws/`, `docs/product-brief.md` a v portovaných souborech enginu (`aifactory/src/aifactory/engine/*.py`).

## Soubory

Nové:

```
aifactory/src/aifactory/config/__init__.py     # re-export veřejného API
aifactory/src/aifactory/config/errors.py       # ConfigIssue, ConfigError
aifactory/src/aifactory/config/source.py       # git helpery, WorktreeSource, CommitSource
aifactory/src/aifactory/config/settings.py     # ProjectSettings (config.yaml), LocalSettings (local.yaml)
aifactory/src/aifactory/config/loader.py       # FactoryConfig, AgentPrompts, load_config, load_worktree_config, write_prompts
aifactory/src/aifactory/config/status.py       # ConfigChange, config_changes, change_warnings
aifactory/src/aifactory/config/run.py          # RunConfig, load_run_config
aifactory/tests/config/config_repo.py          # helpery pro dočasné git repo (žádné fixtures)
aifactory/tests/config/test_config_settings.py
aifactory/tests/config/test_config_loader.py
aifactory/tests/config/test_config_commit.py
aifactory/tests/config/test_config_status.py
aifactory/tests/config/test_config_cli.py
```

Upravit:

- `aifactory/src/aifactory/cli.py`: podpříkazy `config status` a `config show`.
- `.gitignore`: přidat `.factory/trace.db*` (výchozí cesta trace DB z `local.yaml`). `.factory/local.yaml` už ignorovaný je.

**Pozor na testy:** do `aifactory/tests/config/` **nepřidávej `conftest.py`**. `tests/engine/conftest.py` už existuje a mypy (`files = ["src", "tests"]`, adresáře bez `__init__.py`) by hlásil duplicitní modul `conftest`. Všechny názvy testovacích modulů musí být v celém `tests/` unikátní (proto prefix `test_config_`). Sdílené helpery patří do `config_repo.py` a importují se jako `from config_repo import ...`, stejně jako to dělá `engine_fakes`.

## Rozložení `.factory/` a výchozí hodnoty

| Soubor | Zdroj pro běh | Když chybí | Když je neplatný |
|---|---|---|---|
| `.factory/config.yaml` | commit v `base` | `ProjectSettings()` s výchozími hodnotami | `ConfigError` s cestou |
| `.factory/local.yaml` | **vždy pracovní strom** | `LocalSettings()` | `ConfigError` s cestou |
| `.factory/agents.yaml` | commit v `base` | prázdný roster (`agents: []`, výchozí `defaults`) | `ConfigError` s cestou |
| `.factory/roles.yaml` | commit v `base` | balíčkový `aifactory/engine/defaults/roles.yaml` (`load_roles()`) | `ConfigError` s cestou |
| `.factory/prompts/<agent>/{system,user}.md` | commit v `base` | pro agenta z `agents.yaml` je to chyba s cestou chybějícího souboru. Adresáře bez agenta se načtou, pokud existují | — |
| `.factory/workflows/*.yaml` | commit v `base` | `{}` | `ConfigError` s cestou (neplatný YAML nebo kořen, který není mapa) |

„Cesta“ v chybě je **label zdroje**: pro pracovní strom absolutní cesta k souboru, pro commit `"<base>@<sha7>:<relpath>"`, např. `main@1a2b3c4:.factory/agents.yaml`.

### `ProjectSettings` (`config.yaml`, sdílené)

Použij pydantic `BaseModel` s `model_config = ConfigDict(frozen=True, extra="forbid")`. Pole a výchozí hodnoty:

| Klíč | Typ | Výchozí | Validace |
|---|---|---|---|
| `workdir` | str | `"."` | relativní cesta k repu (pracovní adresář agentů: kořen nebo podadresář) |
| `backlog_dir` | str | `"backlog"` | neprázdná relativní cesta |
| `levels` | tuple[str, ...] | `("module","step","task")` | aspoň 2 unikátní neprázdné položky |
| `specs_dir` | str | `"specs"` | relativní |
| `docs_dir` | str | `"app_docs"` | relativní |
| `worktrees_dir` | str | `".factory/worktrees"` | relativní |
| `base` | str | `"main"` | neprázdný, ořezaný |
| `remote` | str | `"origin"` | neprázdný |
| `git_provider` | Literal | `"local"` | `local` \| `github` \| `azure` |
| `merge_strategy` | Literal | `"squash"` | `squash` \| `merge` |
| `test_command` | tuple[str, ...] \| None | `None` | list neprázdných řetězců. Řetězec se rozdělí přes `shlex.split` |
| `protected_files` | tuple[str, ...] | `(".factory/",)` | list řetězců |

Neznámý klíč je chyba (překlepy). Pro `port` a `trace_db` v `config.yaml` vrať konkrétní zprávu: `"'port' is machine-local; put it in .factory/local.yaml"`. Pydantic `ValidationError` převeď na `ConfigIssue` (`path=label`, `message="<loc>: <msg>"`). Prázdný soubor nebo `null` znamená výchozí hodnoty a kořen, který není mapa, je chyba.

### `LocalSettings` (`local.yaml`, lokální, mimo git)

| Klíč | Typ | Výchozí | Validace |
|---|---|---|---|
| `port` | int | `4700` | 1–65535, bool neplatí |
| `trace_db` | str | `".factory/trace.db"` | neprázdný. Relativní se bere od kořene repa |

`extra="forbid"`. Funkce `load_local(root: Path) -> LocalSettings` čte **jen** `root / ".factory/local.yaml"` z disku. Metoda nebo pomocník `trace_db_path(root) -> Path` vrátí absolutní cestu.

## API

### `errors.py`

```python
@dataclass(frozen=True)
class ConfigIssue:
    path: str      # label zdroje (viz výše)
    message: str
    def to_dict(self) -> dict[str, str]: ...

class ConfigError(Exception):
    def __init__(self, issues: list[ConfigIssue]) -> None: ...
    # str(): "path: message" pro každý problém, oddělené "\n"
```

Loader sbírá problémy ze všech souborů a nakonec vyhodí jednu `ConfigError`, ne jen první chybu.

### `source.py`

```python
FACTORY_DIR = ".factory"
LOCAL_FILE = ".factory/local.yaml"

class GitError(ConfigError)  # nebo ConfigError s issue; zpráva obsahuje git příkaz a stderr

def git(root: Path, *args: str) -> str            # subprocess.run(["git", *args], cwd=root, capture_output, text), rc != 0 -> GitError
def repo_root(start: Path) -> Path                # git rev-parse --show-toplevel; mimo repo -> ConfigError("<start>: not a git repository")
def resolve_commit(root: Path, ref: str) -> str   # git rev-parse --verify --quiet "<ref>^{commit}"; selže -> ConfigError("base '<ref>' does not resolve to a commit in <root>")

class ConfigSource(Protocol):
    def read_text(self, rel: str) -> str | None   # None = soubor neexistuje
    def list_files(self, rel_dir: str) -> list[str]  # repo-relativní posix cesty pod rel_dir, rekurzivně, seřazené
    def label(self, rel: str) -> str

class WorktreeSource:   # root: Path; čte z disku
class CommitSource:     # root: Path, ref: str, sha: str
```

`CommitSource`:
- Při vytvoření jednou zavolá `git ls-tree -r -z --name-only <sha> -- .factory` a uloží množinu cest. `list_files` a existenci bere z ní.
- `read_text(rel)` spustí `git cat-file blob <sha>:<rel>`, a to jen pro cesty z množiny, jinak vrátí `None`. **Žádný checkout, žádný `git worktree`, žádná změna indexu.**
- `read_text(".factory/local.yaml")` → `ValueError("local.yaml is never read from a commit")`. Obrana pevného omezení. Loader na `local.yaml` přes zdroj nikdy nesahá.
- `label(rel)` → `f"{ref}@{sha[:7]}:{rel}"`.

`WorktreeSource.label(rel)` → `str(root / rel)`. `list_files` přes `Path.rglob`, jen soubory, výstup ve formě posix a relativně k root.

### `loader.py`

```python
@dataclass(frozen=True)
class AgentPrompts:
    system: str   # text
    user: str

@dataclass(frozen=True)
class FactoryConfig:
    settings: ProjectSettings
    agents: SSSFConfig                  # aifactory.harness.config.SSSFConfig
    roles: RoleRegistry                 # aifactory.engine.role_registry
    prompts: Mapping[str, AgentPrompts] # jméno agenta -> texty
    workflows: Mapping[str, dict[str, Any]]  # stem souboru -> surová YAML mapa
    files: Mapping[str, str]            # rel cesta -> surový text každého přečteného souboru (bez local.yaml)
    source: str                         # např. "main@1a2b3c4" nebo absolutní cesta k root

    @property
    def digest(self) -> str: ...        # sha256 přes seřazené (rel, text) z `files`

def load_config(source: ConfigSource) -> FactoryConfig
def load_worktree_config(root: Path) -> FactoryConfig   # load_config(WorktreeSource(repo_root(root)))
def write_prompts(config: FactoryConfig, dest: Path) -> SSSFConfig
```

`load_config`:
1. `config.yaml` → `ProjectSettings` (viz výše).
2. `agents.yaml`: `yaml.safe_load`, kořen musí být mapa. Pokud má agent `prompt_engineering`, jde o chybu `"agent '<name>': prompt_engineering is not allowed; prompts live in .factory/prompts/<name>/"`. Potom `aifactory.harness.config.normalize_raw(raw)`, jehož `HarnessConfigError.problems` převeď na issues s labelem `agents.yaml`. Každému agentovi doplň `prompt_engineering = {"system": ".factory/prompts/<name>/system.md", "user": ".factory/prompts/<name>/user.md"}` a zavolej `SSSFConfig.model_validate(...)` (`ValidationError` → issues). `harness.config.validate()` (kontrola modelů) se tady **nevolá**.
3. `roles.yaml`: když existuje, `yaml.safe_load` + `role_registry.parse_roles(data)`, jinak `load_roles()`. `RolesError.issues` převeď na `ConfigIssue(label, f"{i.path}: {i.code}: {i.message}")`, neplatný YAML rovněž.
4. Prompty: vezmi agenty z rosteru a k nim adresáře pod `.factory/prompts/` (z `list_files`). Pro deklarovaného agenta chybějící `system.md`/`user.md` znamená issue s labelem chybějícího souboru a zprávou `"missing prompt for agent '<name>'"`. U nedeklarovaného adresáře se načte, co existuje, a chybějící soubor dostane prázdný řetězec.
5. Workflows: přímí potomci `.factory/workflows/` s příponou `.yaml` (ne rekurzivně). YAML se parsuje, kořen musí být mapa a klíčem je stem.
6. Do `files` ulož text každého přečteného souboru. Nakonec vyhoď `ConfigError(issues)`, pokud nějaké jsou.

`write_prompts(config, dest)`: zapíše `dest/<agent>/{system,user}.md` a vrátí kopii `config.agents` s `prompt_engineering` ukazujícím na tyto soubory (absolutní cesty). Engine čte prompty z cest, takže běh (2.9) je materializuje do adresáře session. Pro tento úkol stačí funkce a jeden test.

### `status.py`

```python
SHARED_FILES = (".factory/config.yaml", ".factory/agents.yaml", ".factory/roles.yaml")
SHARED_DIRS = (".factory/prompts/", ".factory/workflows/")

def is_shared_config_path(rel: str) -> bool   # rel == jeden ze SHARED_FILES nebo začíná SHARED_DIRS; nikdy local.yaml

@dataclass(frozen=True)
class ConfigChange:
    path: str     # repo-relativní
    status: Literal["modified", "added", "deleted", "untracked"]
    def to_dict(self) -> dict[str, str]: ...

def config_changes(root: Path, sha: str) -> list[ConfigChange]
def change_warnings(changes: list[ConfigChange], base: str, sha: str) -> list[str]
```

`config_changes` porovná pracovní strom (včetně indexu) s commitem v `base`:
- `git diff --name-status -z --no-renames <sha> -- .factory` přiřadí statusy M→modified, A→added, D→deleted (T/ostatní → modified). Porovnává pracovní strom s commitem, takže zachytí unstaged, staged i změny commitnuté na jiné větvi, které v `base` nejsou.
- `git ls-files -z --others --exclude-standard -- .factory` → untracked.
- Filtruj `is_shared_config_path` (to vyřadí `local.yaml`, worktrees i trace DB), odstraň duplicity a seřaď podle cesty.

`change_warnings`: jedna věta na změnu, anglicky, stabilní formát:
`"<path> is <status> in the working tree but not committed to <base> (<sha7>); runs use the committed version"`.

### `run.py`

```python
@dataclass(frozen=True)
class RunConfig:
    base: str
    commit: str               # plné sha
    config: FactoryConfig     # ze stromu commitu
    local: LocalSettings      # z pracovního stromu
    changes: tuple[ConfigChange, ...]
    warnings: tuple[str, ...]
    def to_json(self) -> dict[str, Any]: ...

def load_run_config(root: Path, base: str | None = None) -> RunConfig
```

Postup:
1. `root = repo_root(root)`.
2. Jméno `base`: argument, jinak klíč `base` z `.factory/config.yaml` v **pracovním stromu** (jen tento klíč, přes `ProjectSettings` z `WorktreeSource`), jinak `"main"`. Kvůli vejci a slepici: `base` říká, odkud číst. Když se hodnota v pracovním stromu liší od commitnuté, ukáže to varování o změně `config.yaml`.
3. `sha = resolve_commit(root, base)`.
4. `config = load_config(CommitSource(root, base, sha))`.
5. Když `config.settings.base != base`, přidej varování `"committed base is '<x>' but the run uses '<base>'"`.
6. `local = load_local(root)`, `changes = config_changes(root, sha)`, `warnings = change_warnings(...)` a k nim případné varování z bodu 5.

`to_json()` vrací: `{"base", "commit", "source", "digest", "agents": [jména], "roles": [known_steps], "workflows": [stemy], "prompts": [agenti], "settings": settings.model_dump(mode="json"), "local": {"port", "trace_db"}, "changes": [...], "warnings": [...]}`.

Dva běhy ze stejného commitu dostanou stejný `digest` a stejné hodnoty. Obsah závisí jen na `sha` a `local.yaml`.

### `__init__.py`

Re-export: `ConfigError, ConfigIssue, ProjectSettings, LocalSettings, load_local, FactoryConfig, AgentPrompts, load_config, load_worktree_config, write_prompts, WorktreeSource, CommitSource, ConfigChange, config_changes, RunConfig, load_run_config`.

## CLI (`aifactory/src/aifactory/cli.py`)

Podle vzoru `_add_harness_commands` / `_harness` přidej `_add_config_commands` a `_config`. Příkaz `factory config` bez podpříkazu vypíše help a vrátí 0. Import `aifactory.config` dělej líně uvnitř funkce, stejně jako harness. Kořen repa se bere z `Path.cwd()`.

- `factory config status [--json] [--base REF]`
  - Najde root, určí `base` (argument, pak worktree `config.yaml`, pak `main`), zavolá `resolve_commit`, `config_changes` a `change_warnings`. Obsah konfigurace **nevaliduje**, aby status fungoval i při rozbitém YAML.
  - `--json` vypíše na stdout `{"ok": true, "base": ..., "commit": ..., "clean": bool, "changes": [{"path","status"}], "warnings": [...]}`.
  - Textový výstup: čisto → `config in sync with <base> (<sha7>)`. Jinak řádek na změnu `<status:<9> <path>` a nakonec `runs use <base> (<sha7>); commit these changes to include them`.
  - Návratový kód je 0 i se změnami (jde o varování), při `ConfigError` (repo, base) 2. V `--json` se chyba vypíše jako `{"ok": false, "error": str, "issues": [...]}` na stdout, v textovém režimu `factory config status: <chyba>` na stderr.
- `factory config show [--json] [--base REF]`
  - `load_run_config(...)`. `--json` vypíše `{"ok": true, **run.to_json()}`, takže je tu pole `warnings`, jaké bude vracet spuštění běhu. Text: base/commit, seznamy agentů, workflow a promptů, port a trace DB, pak varování, každé s prefixem `warning: ` na stderr.
  - `ConfigError` → 2, ve stejném tvaru jako výše (`issues` = `[i.to_dict() ...]`).

Uprav docstring modulu (`harness check` a `config status/show`).

## Testy (`aifactory/tests/config/`)

`config_repo.py` (typovaný, bez pytest fixtures):
- `git(repo, *args) -> str` volá `subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args], cwd=repo, check=True, capture_output=True, text=True)` s `env` = kopie `os.environ` + `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=os.devnull`.
- `make_repo(path) -> Path`: `git init -b main`, zapíše vzorovou `.factory/` a `.gitignore` s `.factory/local.yaml`, commitne. Vzor:
  - `config.yaml`: `base: main`, `test_command: [pytest, -q]`
  - `agents.yaml`: `defaults: {harness: claude, model: sonnet}` a agenti `planner` (`model: opus`, `writes: [specs/]`) a `builder`
  - `prompts/planner/{system,user}.md`, `prompts/builder/{system,user}.md` (user obsahuje `{{prompt}}`)
  - `workflows/plan-build.yaml`: `name: plan-build`, `steps: [plan, build]`
  - `roles.yaml` vynechat, aby se ověřil default
- `write(repo, rel, text)` a `commit_all(repo, msg)`.

`test_config_settings.py`:
- chybějící `config.yaml` i `local.yaml` → výchozí hodnoty (`base == "main"`, `port == 4700`, `trace_db == ".factory/trace.db"`)
- prázdný soubor → výchozí hodnoty
- vlastní hodnoty včetně `test_command: "dotnet test --no-build"` → `("dotnet","test","--no-build")`
- parametrizované neplatné vstupy (neplatný YAML, list jako kořen, `levels: [task]`, absolutní `backlog_dir`, `git_provider: svn`, neznámý klíč, `port` v `config.yaml`) → `ConfigError`, jehož `str` obsahuje cestu k souboru
- `local.yaml` s `port: 0` / `port: true` → chyba s cestou

`test_config_loader.py` (`load_worktree_config` nad `make_repo`):
- agenti mají harness `claude`, `planner.model == "opus"`, `builder` zdědí `sonnet`. `prompts["planner"].user` obsahuje `{{prompt}}`
- chybějící `roles.yaml` → `roles.is_role("plan")`
- neplatný `roles.yaml` (např. neznámý `output_type`) → `ConfigError` s cestou `roles.yaml`
- agent bez harnessu (bez `defaults.harness`) → chyba s cestou `agents.yaml`
- smazaný `prompts/builder/system.md` → chyba obsahující `.factory/prompts/builder/system.md`
- `prompt_engineering` v `agents.yaml` → chyba
- workflow s neplatným YAML → chyba s cestou souboru. Workflows se načtou pod klíčem `plan-build`
- chybějící `agents.yaml` → prázdný roster bez chyby
- víc chyb najednou (rozbitý `config.yaml` + chybějící prompt) → `len(err.issues) >= 2`
- `write_prompts` zapíše soubory a vrácený `SSSFConfig` má `prompt_engineering.system` s existující cestou pod `dest`

`test_config_commit.py` (jádro zadání):
- **necommitnutý prompt i `agents.yaml`**: po `make_repo` změň `prompts/planner/system.md` a v `agents.yaml` `planner.model` na `haiku`, bez commitu. `load_run_config(repo)`:
  - `config.prompts["planner"].system` je commitnutý text, `planner.model == "opus"`
  - `warnings` obsahují `.factory/prompts/planner/system.md` i `.factory/agents.yaml`, `changes` mají status `modified`
- **dva běhy ze stejného commitu**: `a = load_run_config(repo)`, pak změň prompt/workflow v pracovním stromu (i nový untracked workflow), `b = load_run_config(repo)` → `a.commit == b.commit`, `a.config.digest == b.config.digest`, `a.config.agents == b.config.agents`, `a.config.prompts == b.config.prompts`, `a.config.workflows == b.config.workflows`. Untracked workflow není v `b.config.workflows` a je v `b.changes` jako `untracked`
- **bez checkoutu**: `git rev-parse HEAD`, `git status --porcelain` a obsah změněného souboru jsou po načtení stejné jako před ním. `git worktree list` má jediný záznam
- **`local.yaml` nikdy z base**: `local.yaml` s `port: 1111` commitni přes `git add -f`, v pracovním stromu nastav `port: 2222` → `run.local.port == 2222`, `local.yaml` není v `changes`. Navíc `CommitSource(...).read_text(".factory/local.yaml")` vyhodí `ValueError`
- **base ≠ HEAD**: `git checkout -b feature`, commitni změnu promptu na `feature` → `load_run_config(repo)` čte z `main` (starý prompt), změna je ve `warnings`. `load_run_config(repo, base="feature")` vrátí nový prompt a nemá žádná varování
- **neexistující base**: `base: develop` v commitnutém i pracovním `config.yaml` → `ConfigError` se zprávou o `develop`
- **mimo git repo**: `tmp_path` bez `git init` → `ConfigError`

`test_config_status.py`:
- čisté repo → `config_changes == []`
- změny `modified` / `deleted` (smazaný prompt) / `untracked` (nový workflow) / staged nový soubor (`added`) se správným statusem a seřazené
- necommitnutý `local.yaml`, soubor v `.factory/worktrees/x` a `.factory/trace.db` se neobjeví
- `change_warnings` obsahuje cestu, `base` a sha7

`test_config_cli.py` (`aifactory.cli.main([...])` + `monkeypatch.chdir(repo)` + `capsys`):
- `config status --json` na čistém repu → rc 0, `clean is True`, `warnings == []`
- po změně promptu a `agents.yaml` → `clean is False`, obě cesty v `changes` i `warnings`
- textový `config status` vypíše obě cesty
- `config show --json` → rc 0, klíč `warnings` obsahuje změnu, `agents == ["planner","builder"]`
- rozbitý `agents.yaml` commitnutý v `base` → `config show --json` vrátí rc 2 a `ok is False`, `issues[0]["path"]` obsahuje `agents.yaml`. `config status` na stejném repu vrátí rc 0
- mimo repo → rc 2
- `factory config` bez podpříkazu → rc 0

## Postup

1. `errors.py`, `source.py`, `settings.py`, poté testy settings.
2. `loader.py` a testy loaderu.
3. `status.py`, `run.py` a testy commit/status.
4. CLI a testy CLI.
5. `.gitignore`: `.factory/trace.db*`.
6. `cd aifactory && uv run ruff format .` (mimo excludované soubory enginu), pak ověření.

## Ověření

```bash
just test          # celé pytest, včetně tests/config
just typecheck     # mypy --strict nad src i tests
just lint          # ruff check + ruff format --check
just factory config status --json   # v HAIFA repu: rc 0 (repo nemá .factory/ config, clean true)
```

Úspěch se posuzuje podle návratového kódu, ne podle textu výstupu.

## Rizika a poznámky

- `aifactory.harness.config.SSSFConfig` / `AgentConfig` jsou podtřídy typů enginu. `prompt_engineering` je v enginu povinné, proto se doplňuje před `model_validate`.
- mypy strict: engine je netypovaný (`untyped_calls_exclude`). U `RoleRegistry` a `SSSFConfig` stačí anotace typů. `Mapping` pro frozen dataclass pole: ukládej `dict` a pro hashovatelnost použij `field(compare=True, hash=False)` nebo nepoužívej `frozen` hash (`@dataclass(frozen=True, eq=True)` s dict polem nevadí, dokud se nevolá `hash()`).
- Git výstupy čti s `-z` kvůli cestám s mezerami.
- Nenahrazuj a neměň `prototype/src/haifa_proto/config.py`, slouží jen jako předloha.
