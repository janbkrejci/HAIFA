# HAIFA-S05-T05: Harnessy načítají instrukce a skilly repa nativně

## Cíl

Agenti factory dnes běží izolovaně od repa (claude `--safe-mode`, codex `-c project_doc_max_bytes=0`) a pi bez řízení (načte i osobní rozšíření a skilly operátora). Po změně ve výchozím režimu:

- každý harness načte instrukce repa (CLAUDE.md, AGENTS.md) a skilly repa svým nativním mechanismem,
- osobní a globální konfigurace operátora (`~/.claude`, `~/.codex`, `~/.pi/agent`, `~/.agents`) se do běhu nedostane, pokud to harness umí; co vyloučit nejde, nahlásí `factory check` jako varování,
- `*_SAFE_MODE=1` vrátí úplnou izolaci,
- `factory skills sync` udržuje `.agents/skills/` jako přesnou kopii `.claude/skills/` a `factory check` hlásí rozdíl.

System prompt agenta (`--system-prompt` u claude a pi, `-c developer_instructions=…` u codexu) zůstává beze změny a dál nese roli agenta.

## Povolené cesty

`aifactory/`, `justfile`, tento spec, `app_docs/HAIFA-S05-T05-…md` (tu píše až dokumentační fáze, builder ji nechá být). `docs/`, `vendor/`, `prototype/`, `CLAUDE.md` se NEMĚNÍ. Nic se nezapisuje do `~/.claude`, `~/.codex`, `~/.agents` ani `~/.pi/agent`, ani v testech: testy dostanou falešný home přes `tmp_path`.

## Ověřené přepínače CLI (claude 2.1.289, codex-cli 0.157.1, pi 0.99.2)

- **claude**: `--setting-sources <user,project,local>` vybere zdroje nastavení. Bez `user` se nenačte `~/.claude/settings.json` (hooky, `enabledPlugins`, oprávnění), `~/.claude/CLAUDE.md`, `~/.claude/skills`, `~/.claude/agents` ani `~/.claude/commands`. Zdroje `project` a `local` načtou `.claude/settings.json`, `.claude/settings.local.json`, CLAUDE.md repa a `.claude/skills/`. `--strict-mcp-config` bez `--mcp-config` vypne MCP. `--bare` nepoužívat (rozbije OAuth), `--restricted` taky ne (odmítne `bypassPermissions`).
- **codex** (`exec` i `exec resume`): `--ignore-user-config` nenačte `$CODEX_HOME/config.toml` (MCP servery, profily, hooky z configu). Autentizace z `CODEX_HOME` dál funguje. AGENTS.md repa se čte, dokud se nenastaví `project_doc_max_bytes=0`. `.agents/skills/` repa codex objeví sám. Vyloučit nejde `~/.codex/AGENTS.md` a `AGENTS.override.md` (globální instrukce), `~/.codex/skills/` a `~/.agents/skills/` (uživatelské skilly).
- **pi**: `--approve` udělí důvěru projektu pro jeden proces. Bez ní pi v `-p` režimu podle `defaultProjectTrust` (výchozí `ask`) projektové `.agents/skills` přeskočí. `--no-skills` vypne objevené a nakonfigurované skilly (`~/.pi/agent/skills`, `~/.agents/skills`, projektové), ale explicitní `--skill <path>` se načte. `--no-extensions` vypne objevená, nakonfigurovaná i vestavěná rozšíření, explicitní `-e` se načte (rozšíření z `harness_engineering` tedy fungují dál). `--no-prompt-templates` vypne šablony promptů. `--no-context-files` vypne AGENTS.md a CLAUDE.md, a to i globální; ty z `~/.pi/agent` (`AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`) proto bez ztráty instrukcí repa vyloučit nejde. Totéž platí pro `~/.pi/agent/APPEND_SYSTEM.md`. `--no-approve` ignoruje soubory projektu chráněné důvěrou. Adresář agenta lze přesměrovat přes `PI_CODING_AGENT_DIR`, factory to ale nedělá (přišla by o auth a `models.json`).

## Návrh

### 1. Sdílený parser přepínače: `engine/utils.py`

Přidej (se značkou `# aifactory:`):

```python
# aifactory: *_SAFE_MODE switches are read at call time so a test (or an operator's
# env) flips them without re-importing; default off = native repo loading.
def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "no", "off")
```

### 2. claude: `engine/agent_cc.py`

- Smaž modulovou konstantu `SAFE_MODE` a nahraď ji funkcí `safe_mode() -> bool: return env_flag("CLAUDE_SAFE_MODE")`. Přepiš i komentář nad ní: výchozí je nativní načítání repa, `CLAUDE_SAFE_MODE=1` vrací `--safe-mode`. Konstantu `SETTING_SOURCES = "project,local"` dej do modulu.
- Konec sestavení `cmd` v `run()` (každá změněná řádka nebo blok má komentář `# aifactory:`):

```python
if MCP_CONFIG:
    cmd += ["--mcp-config", MCP_CONFIG, "--strict-mcp-config"]
else:
    cmd.append("--strict-mcp-config")
if safe_mode():
    if not MCP_CONFIG:
        cmd.append("--safe-mode")          # as before: safe mode and MCP exclude each other
else:
    cmd += ["--setting-sources", SETTING_SOURCES]   # repo settings, CLAUDE.md, .claude/skills; never ~/.claude
```

- Pozor na `--disallowedTools`: je variadický a musí za ním následovat volba. `--strict-mcp-config` za ním je dál vždy, pořadí se nemění.
- Docstring modulu: doplň odstavec o nativním načítání repa (`--setting-sources project,local`, `--strict-mcp-config`) a o `CLAUDE_SAFE_MODE=1`.

### 3. codex: `harness/codex.py`

- `CODEX_SAFE_MODE` nahraď funkcí `safe_mode() -> bool: return env_flag("CODEX_SAFE_MODE")` (import z `aifactory.engine.utils`).
- V `build_command` přidej do `common` vždy `"--ignore-user-config"`. Osobní `config.toml` se nenačte v žádném režimu, protože „kde to harness umí“ platí i pro safe mode. Jen když platí `safe_mode()`, přidej `-c project_doc_max_bytes=0`. Funguje to pro `exec` i `exec resume`, protože obojí sdílí `common`.
- Docstring modulu: nový bod **Repo instructions** (AGENTS.md a `.agents/skills/` repa nativně, `--ignore-user-config`, co vyloučit nejde a hlásí `factory check` jako `codex_not_isolated`, `CODEX_SAFE_MODE=1`).

### 4. pi: `engine/agent_pi.py`

- Přidej `safe_mode() -> bool: return env_flag("PI_SAFE_MODE")` a funkci (se značkou `# aifactory:`):

```python
REPO_SKILLS_DIR = (".agents", "skills")

def isolation_args(cwd: str) -> list[str]:
    """pi flags for repo-native loading, or full isolation under PI_SAFE_MODE=1."""
    if safe_mode():
        return ["--no-approve", "--no-context-files", "--no-skills",
                "--no-extensions", "--no-prompt-templates"]
    args = ["--approve",            # project trust: unattended -p would skip .agents/skills
            "--no-skills",          # drops ~/.pi/agent/skills and ~/.agents/skills ...
            "--no-extensions",      # ... personal/discovered extensions (explicit -e still load)
            "--no-prompt-templates"]
    skills = Path(cwd).joinpath(*REPO_SKILLS_DIR)
    if skills.is_dir():
        args += ["--skill", str(skills.resolve())]   # ... and loads the repo's skills explicitly
    return args
```

- V `_attempt` vlož `*isolation_args(request.cwd)` za `--system-prompt` a před `--tools` a `-e`. Pokud cesta nemá `cwd`, dej `request.cwd` (`PiRequest` ho dědí, viz `data_types.py:428`, `cwd: str = "."`). Relativní cwd se resolvuje proti procesu, proto `resolve()`.
- Docstring modulu doplň o nativní načítání, důvěru, přepínač a to, co vyloučit nejde.

### 5. Zrcadlo skillů: nový modul `aifactory/src/aifactory/harness/repo_skills.py`

Čistá logika bez CLI, sdílená `factory skills sync` a `factory check`:

```python
SOURCE = ".claude/skills"
MIRROR = ".agents/skills"

@dataclass(frozen=True)
class SkillsDiff:
    missing: tuple[str, ...]   # in SOURCE, not in MIRROR
    changed: tuple[str, ...]   # in both, different files/bytes/exec bit
    extra: tuple[str, ...]     # in MIRROR only
    @property
    def clean(self) -> bool: ...

def group_by_skill(files: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """{"<skill>/<rel>": key} -> {"<skill>": {"<rel>": key}}; a top-level file is its own entry with rel ""."""

def diff_snapshots(source: Mapping[str, str], mirror: Mapping[str, str]) -> SkillsDiff:
    """Compare two snapshots {path relative to the skills dir: key}; names sorted."""

def worktree_snapshot(root: Path, rel_dir: str) -> dict[str, str]:
    """Files under root/rel_dir (recursive, regular files and symlinks as files): key = sha256 of bytes + ':x' if executable. Missing dir -> {}."""

def commit_snapshot(root: Path, commit: str, rel_dir: str) -> dict[str, str]:
    """From `git ls-tree -r -z <commit> -- <rel_dir>` (via config.source.git_try, read-only): key = '<mode> <oid>'. No such tree -> {}."""

@dataclass(frozen=True)
class SyncResult:
    added: tuple[str, ...]; updated: tuple[str, ...]; removed: tuple[str, ...]

def sync(root: Path) -> SyncResult:
    """Make root/MIRROR an exact copy of root/SOURCE.

    For each name in diff.missing + diff.changed: rmtree/unlink the target and copy it
    (shutil.copytree(..., symlinks=False, copy_function=shutil.copy2) or copy2 for a
    top-level file), so modes and the exec bit carry over. For each name in diff.extra:
    remove it. When SOURCE does not exist and MIRROR is empty after removal, remove MIRROR
    too (and an empty `.agents/` it leaves behind). Does not touch anything else in `.agents/`.
    """
```

- Jednotkou je jméno záznamu nejvyšší úrovně pod `skills/`, tedy adresář skillu (soubor nejvyšší úrovně se bere jako vlastní záznam). Stejný snímek obou stran (sha256 v pracovním stromu, nebo `mode oid` z gitu) dá stejnou odpověď.
- Pro git čtení použij `aifactory.config.source.git_try` (`GIT_OPTIONAL_LOCKS=0`). Výstup s `-z` rozděl podle `\0`, každý záznam má tvar `"<mode> <type> <oid>\t<path>"`. Vezmi jen `type == "blob"`, cestu oddělenou od `rel_dir + "/"`.
- Chyby I/O z `sync` propadnou jako `OSError`. CLI je převede na kód (viz bod 6).

### 6. CLI: `factory skills sync` v `cli.py`

- Do `SUBCOMMANDS` přidej `("skills", "keep the repo's skills mirror for codex and pi in sync")`, do `build_parser` větev `_add_skills_commands`, do `_dispatch` větev `skills` → `_skills(args)`. Aktualizuj docstring modulu (seznam příkazů).
- `_add_skills_commands`: stejný vzor jako `harness`/`workflow` (`set_defaults(skills_parser=parser)`, `add_subparsers(dest="skills_command")`). Podpříkaz `sync` s `description` ve smyslu: „Write `.agents/skills/` as an exact copy of `.claude/skills/` (new, changed and deleted skills), so codex and pi read the same skills as claude. Writes the working tree only; commit the result. No symlinks.“ Argumenty `--repo PATH` (výchozí: git repo aktuálního adresáře) a `--json`.
- `_skills(args)`: bez podpříkazu vypíše nápovědu a vrátí 0. Jinak `root = repo_root(Path(args.repo) if args.repo else Path.cwd())`. `ConfigError` předej do `_fail_from_exception(exc, args.json, "factory skills sync")`. Pak `repo_skills.sync(root)`. `OSError` → `_emit_fail("skills_sync_failed", str(exc), exit_code=2)`, případně stderr a návratový kód 2.
- Úspěch s `--json`: `_emit_ok({"repo": str(root), "source": SOURCE, "mirror": MIRROR, "added": [...], "updated": [...], "removed": [...]})`. Bez `--json` řádky `added <name>`, `updated <name>`, `removed <name>` a souhrn, případně „.agents/skills is up to date“. Exit 0.
- Ověř, že `skill/commands.py` nový podpříkaz projde generickým průchodem a v `factory --skill` se objeví sám (test v `test_skill.py`, bod 9).

### 7. `factory check`

**a) Zrcadlo skillů: `check/repo_rules.py`**, nové pravidlo `skills_mirror` (zaregistruj v `REPO_GROUP` jako `Rule("skills mirror", skills_mirror)`):

- Když `ctx.commit is None`, vrať se. Jinak `diff_snapshots(commit_snapshot(ctx.main, ctx.commit, SOURCE), commit_snapshot(ctx.main, ctx.commit, MIRROR))`. Čte se base, protože běhy vidí base.
- Pro každé jméno jeden `Finding` s literálním kódem jako prvním argumentem, scope `repo`, severity `warning`:
  - `Finding("skill_mirror_missing", "repo", "warning", f"skill '{name}' is in .claude/skills but not in .agents/skills of {ctx.base}; codex and pi do not see it", "run factory skills sync and commit .agents/skills")`
  - `skill_mirror_differs`: skill je v `.agents/skills`, ale liší se od `.claude/skills`.
  - `skill_mirror_extra`: skill je v `.agents/skills`, ale v `.claude/skills` už není.

**b) Globální konfigurace operátora: `check/machine_rules.py`**, nové pravidlo `isolation` (zaregistruj v `MACHINE_GROUP` jako `Rule("harness isolation", isolation)`):

- `Machine` (protokol v `check/machine.py`) dostane metodu `home(self) -> Path`. `SystemMachine.home()` vrací `Path.home()`.
- Pravidlo: když `ctx.roster is None`, vrať se. Pro `harnesses_in_config(ctx.roster)`:
  - **codex**, pokud `ctx.machine.env("CODEX_SAFE_MODE")` neznamená zapnuto (použij `env_flag`-ekvivalent nad hodnotou z `ctx.machine.env`; přidej pomocnou funkci `flag_value(value: str | None) -> bool` do `engine/utils.py` a `env_flag` na ní postav): `codex_home = Path(ctx.machine.env("CODEX_HOME") or ctx.machine.home() / ".codex")`. Kandidáti: `codex_home/AGENTS.md`, `codex_home/AGENTS.override.md`, `codex_home/skills` a `home/.agents/skills` (adresáře jen když jsou neprázdné). Pokud existuje aspoň jeden, vrať `Finding("codex_not_isolated", "machine", "warning", f"codex loads the operator's global {', '.join(paths)} into every run (agents: …); it has no switch to leave them out", "move them out of the way, or set CODEX_SAFE_MODE=1 for full isolation")`.
  - **pi**, pokud není `PI_SAFE_MODE`: `agent_dir = Path(ctx.machine.env("PI_CODING_AGENT_DIR") or home / ".pi" / "agent")`. Kandidáti: `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`, `APPEND_SYSTEM.md` v `agent_dir`. Výsledek je `Finding("pi_not_isolated", "machine", "warning", …)` se stejnou stavbou a fixem „…or set PI_SAFE_MODE=1“.
  - claude nic nehlásí, protože `--setting-sources project,local` vyloučí vše z `~/.claude`.
- Pravidlo jen čte (`is_file`, `is_dir`, `any(iterdir())`), nic nezapisuje.

**c) `tests/check/factory_check_repo.py`**: `FakeMachine` dostane pole `home_dir: Path = field(default_factory=lambda: Path("/nonexistent/fake-home"))` a metodu `home()`. Stávající testy tak varování nedostanou.

### 8. Kódy: `skill/codes.py`

- Do `_CODES` (sekce výsledků nebo vstupu) přidej `("skills_sync_failed", "2", "factory skills sync could not write .agents/skills")`.
- Do `ISSUE_CODES["check"]` přidej `skill_mirror_missing`, `skill_mirror_differs`, `skill_mirror_extra`, `codex_not_isolated` a `pi_not_isolated`. `test_check_codes_complete` vyžaduje přesnou shodu s literály `Finding("…")` v `check/`.

### 9. `factory --skill`: `skill/skill.md`

Nová sekce pod `## Procedures`, například `### Repo instructions and skills`:

- Agenti běží jako harness spuštěný z CLI v repu. claude čte CLAUDE.md, `.claude/settings*.json` a `.claude/skills/` (`--setting-sources project,local`) a MCP je vypnuté. codex čte AGENTS.md a `.agents/skills/` a `~/.codex/config.toml` vynechá. pi čte AGENTS.md, CLAUDE.md a `.agents/skills/` s důvěrou v projekt (`--approve`), osobní skilly, rozšíření a šablony vynechá. Role agenta zůstává v jeho system promptu.
- Skill má zdroj v `.claude/skills/<name>/` a edituje se tam. `.agents/skills/` je jeho přesná kopie bez symlinků. Po změně spusť `factory skills sync` a commitni obojí. `factory check` hlásí `skill_mirror_missing`, `skill_mirror_differs` a `skill_mirror_extra`.
- Globální soubory operátora, které harness vyloučit neumí, hlásí `factory check` jako `codex_not_isolated` a `pi_not_isolated` (scope machine).
- `CLAUDE_SAFE_MODE=1`, `CODEX_SAFE_MODE=1` a `PI_SAFE_MODE=1` vrátí úplnou izolaci (claude `--safe-mode`, codex `project_doc_max_bytes=0`, pi bez kontextových souborů, skillů, rozšíření a důvěry). Výchozí stav je vypnuto.

Pokud `skill.md` obsahuje seznam check kódů v textu nebo seznam příkazů ručně, doplň je. Většina se generuje z `codes.py` a argparse, takže ověř výstup `uv run factory --skill`.

## Testy (bez modelu a sítě, nikdy skutečné CLI)

Nový soubor `aifactory/tests/harness/test_harness_repo_native.py`. Používá `fake_popen` a `fake_pi_catalog` z `harness_fakes.py` a `_request`-like helper (zkopíruj vzor z `test_harness_contract.py`, nebo ho přesuň do `harness_fakes.py` jako `make_request`). Spawny jdou přes `FakeSpawner` a čte se `spawner.calls[0].cmd`. Fixtury `claude_*.jsonl`, `pi_*.jsonl` a `codex_turn.jsonl` už existují (`stream(name, envelope_text(...))` je taky k dispozici). Ve všech testech `monkeypatch.delenv("CLAUDE_SAFE_MODE", raising=False)` (a stejně CODEX/PI), aby test nezávisel na prostředí operátora.

1. **claude výchozí**: argv obsahuje `--setting-sources project,local` (sousední položky) a `--strict-mcp-config`, neobsahuje `--safe-mode` a `--system-prompt` je system prompt requestu.
2. **claude `CLAUDE_SAFE_MODE=1`** (`monkeypatch.setenv`): argv obsahuje `--safe-mode` a `--strict-mcp-config`, neobsahuje `--setting-sources`.
3. **claude s `MCP_CONFIG`** (monkeypatch `agent_cc.MCP_CONFIG`): výchozí stav má `--mcp-config` a `--setting-sources`. V safe mode chybí `--safe-mode`, jako dřív.
4. **codex výchozí**, `exec` i `exec resume` (`build_command(request)` a `build_command(request, THREAD_ID)`): `--ignore-user-config` přítomný, `project_doc_max_bytes=0` chybí a `developer_instructions=…` je přítomný.
5. **codex `CODEX_SAFE_MODE=1`**: `-c project_doc_max_bytes=0` přítomný a `--ignore-user-config` taky.
6. **pi výchozí s `.agents/skills`** (vytvoř `tmp_path/repo/.agents/skills/demo/SKILL.md`, cwd requestu = repo): argv obsahuje `--approve`, `--no-skills`, `--skill <abs path>`, `--no-extensions` a `--no-prompt-templates`. Neobsahuje `--no-context-files` ani `--no-approve`. `--system-prompt` je přítomný. Request s `extensions=["/x/ext.ts"]` má dál `-e /x/ext.ts`.
7. **pi výchozí bez `.agents/skills`**: `--approve` je, `--skill` chybí.
8. **pi `PI_SAFE_MODE=1`**: `--no-approve`, `--no-context-files`, `--no-skills`, `--no-extensions` a `--no-prompt-templates`. Chybí `--approve` a `--skill`.
9. **přes engine** (volitelně, parametrizace přes `NAMES` s `make_env`/`start_run`/`agent_phase`): výchozí argv každého harnessu nemá izolační přepínač (`--safe-mode`, `project_doc_max_bytes=0`, `--no-context-files`).

`env_flag`: hodnoty `"1"`, `"true"`, `"yes"` jsou zapnuto, `""`, `"0"`, `"false"`, `"no"` a nenastaveno vypnuto.

Nový soubor `aifactory/tests/harness/test_repo_skills.py`:

- `sync` v `tmp_path`: `.claude/skills/a/SKILL.md`, `.claude/skills/b/SKILL.md` + spustitelný `b/run.sh`, `.agents/skills/b/SKILL.md` (jiný obsah), `.agents/skills/old/SKILL.md`. Po `sync` platí `added == ("a",)`, `updated == ("b",)`, `removed == ("old",)`, stromy jsou bajtově shodné, `run.sh` má exec bit a druhé volání `sync` vrátí prázdný výsledek.
- Smazaný `.claude/skills`: sync odstraní `.agents/skills`, ale jiný obsah `.agents/` nechá.
- `diff_snapshots` na ručně zadaných slovnících: missing, changed i extra.
- `commit_snapshot` na dočasném git repu s commitem.

CLI (`aifactory/tests/` vedle stávajících CLI testů, například `tests/harness/test_skills_sync_cli.py`; podívej se na vzor v `tests/harness/test_harness_check_cli.py` a `tests/cli_json.py`):

- `factory skills sync --repo <tmp repo> --json`: `ok: true`, `data.added`, soubory zapsané, exit 0.
- Bez `--json`: výpis `added a`, exit 0.
- Mimo git repo: `ok: false`, exit 2.

`factory check` (`tests/check/test_factory_check.py`, helpery z `factory_check_repo.py`):

- Repo s commitnutým `.claude/skills/{a,b}` a `.agents/skills/{b (jiný obsah), c}`: findings obsahují `skill_mirror_missing` (a), `skill_mirror_differs` (b) a `skill_mirror_extra` (c), vše scope `repo` a severity `warning`. Po `sync` a commitu žádné `skill_mirror_*` nezbývá.
- Roster s harnessem codex (nebo pi) a `FakeMachine(home_dir=tmp_path/"home")` se souborem `home/.codex/AGENTS.md` (pi: `home/.pi/agent/AGENTS.md`): finding `codex_not_isolated` / `pi_not_isolated`, scope `machine`, severity `warning`. Se `environ={"CODEX_SAFE_MODE": "1"}` finding nevznikne. Bez souborů finding nevznikne.

`tests/test_skill.py`: test, že `render_skill()` obsahuje `factory skills sync`, `.agents/skills`, `CLAUDE_SAFE_MODE`, `CODEX_SAFE_MODE` a `PI_SAFE_MODE`. Stávající `test_check_codes_complete` a `test_error_codes_complete` musí projít.

Stávající testy: projdi `grep -rn "safe-mode\|SAFE_MODE\|project_doc" aifactory/tests` (dnes nic). Kdyby některý test porovnával celé argv, uprav ho na nové výchozí argv.

## Ověření

Z kořene worktree:

```
just test
just typecheck
just lint        # ruff check + ruff format --check; v případě potřeby `cd aifactory && uv run ruff format .`
cd aifactory && uv run factory --skill | grep -n "skills sync\|SAFE_MODE"
```

Všechny tři `just` recepty musí skončit exit 0.

## Pevná pravidla pro buildera

- Každá změna logiky v `aifactory/src/aifactory/engine/` (`agent_cc.py`, `agent_pi.py`, `utils.py`) nese komentář `# aifactory:` (styl `# aifactory 2.9:` / `# aifactory:` jako v `runner.py`).
- Kódy check findingů jsou literály v prvním argumentu `Finding(...)`.
- Žádné zápisy mimo repo, testy používají `tmp_path` jako home.
- `vendor/`, `prototype/` a `docs/` se nemění. Rozhodnutí už je v `docs/decisions.md` („Instrukce a skilly repa“).
- Mimo rozsah: `skills:` agentů v `.factory/`, `.factory/skills/`, rejstřík skillů v promptu, rozšíření pi z `.factory/`, instalace skillů z knihovny, dashboard a ověření proti skutečným CLI.
