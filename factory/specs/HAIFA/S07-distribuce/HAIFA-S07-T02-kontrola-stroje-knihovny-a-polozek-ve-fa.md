# HAIFA-S07-T02: Kontrola stroje, knihovny a položek ve `factory check`

## Cíl

`factory check` řekne kolegovi, co na stroji chybí pro HAIFA a jeho repa. Mimo git repo kontroluje jen stroj a knihovnu (`scope` `machine` a `library`). V repu navíc hlásí stavy položek a další nálezy konfigurace. Kontrola **nic nezapisuje** (repo, knihovna, `$HAIFA_HOME`), nic nefetchuje a s `--offline` nevolá hosting ani přihlášení. Zdroj pravdy: `docs/design/library-onboarding-distribution.md`, AR40 až AR42 a AR23.

## Co už existuje (nepřepisovat, rozšířit)

- `aifactory/src/aifactory/check/`: `__init__.py` (`run_check`, `RULE_GROUPS`, `_run_rule`), `model.py` (`Finding`, `Rule`, `RuleGroup`, `CheckReport`, literály `Scope`/`Action`), `context.py` (`CheckContext`, `main_checkout`, `NotARepositoryError`), `machine.py` (`Machine` Protocol, `SystemMachine`), `machine_rules.py` (`harness_missing`, `just_missing`, `test_program_missing`, `local_*`, `gh_*`, `az_*`, `hosting_skipped`, `codex_not_isolated`, `pi_not_isolated`), `repo_rules.py` (install/state, `sssf_leftover`, workflows, test command, gitignore, skills mirror).
- `skill/codes.py`: `ISSUE_CODES["check"]` musí přesně odpovídat všem `Finding("<literál>", ...)` v `check/**/*.py` (`tests/test_skill.py::test_check_codes_complete`). **Kód je vždy řetězcový literál jako první argument `Finding(...)`**, nikdy proměnná.
- Knihovna: `library/remote.py::library_status(fetch=False, environ)` vrací `dirty`, `ahead`, `behind`, `remote`, `last_fetch`, `min_factory_version`, `compatible`, `seed_update_available`, `seed_updates`; bez knihovny vyhodí `LibraryStoreError("library_missing")`. S `fetch=False` nebere zámek ani nevytváří `$HAIFA_HOME` (ověř to a neměň).
- `library/state.py::repo_items(path, base, environ)` počítá stavy položek z base do dočasného adresáře mimo repo.
- `home.py::env_file(environ)`, `harness/override.py::THINKING_LEVELS`, `harness::CLI_BINARIES`, `harness/check.py::harnesses_in_config`.
- Testovací pomůcky: `tests/check/factory_check_repo.py` (`FakeMachine`, `make_check_repo`, `write`, `commit_all`), `tests/fake_exe.py::make_executable`, `tests/cli_json.py::run_json`. Autouse fixture v `conftest.py` dává každému testu dočasný `HAIFA_HOME` a hlídá, že se skutečný domov nezmění.

## Rozhodnutí návrhu

1. **Mimo repo:** bez `--repo` a s cwd mimo git repo vrátí `run_check` zprávu jen se skupinami `machine` a `library` (exit 0 bez chyb, 1 s chybami). Výslovné `--repo PATH`, které není git repo, dál vrací `not_a_repository` s exit 2 (stávající test zůstane). Tím zůstávají návratové kódy 0, 1 a 2.
2. **Nový scope `library`** (`Scope = Literal["repo", "machine", "library"]`). `factory_outdated` má scope `machine` (instalace na stroji), `library_*` a `seed_update_available` scope `library`.
3. **Přejmenování kódů podle AR40:** `test_program_missing` → `test_command_missing`, `gh_not_logged_in` → `gh_login`, `az_not_logged_in` → `az_login` (jen ve `check/`; `az_not_logged_in` jako `error.code` provideru Azure v `_CODES` zůstává). `gh_missing`, `az_missing`, `az_devops_missing`, `hosting_skipped` zůstávají.
4. **Stavy položek:** kód podle stavu, každý s literálem: `item_local` (info, `export`), `item_missing` (warning, `update`), `item_unknown` (warning, `adopt`), `item_outdated` (info, `update`), `item_modified` (info, `export`), `item_diverged` (warning, `update`). `synced` nehlásí nic. Do `Action` přidej `"export"`. Mapování akcí odpovídá tabulce AR23.
5. **Pravidlo mimo repo:** `Rule` dostane pole `needs_repo: bool = True`. Pravidla stroje a knihovny, která repo nepotřebují, mají `needs_repo=False` a `needs_install=False`. Mimo repo se pouští jen pravidla s `needs_repo=False`, ve všech skupinách.

## Změny po souborech

### `aifactory/src/aifactory/check/model.py`
- `Scope` přidej `"library"`, `Action` přidej `"export"`.
- `Rule`: nové pole `needs_repo: bool = True` (docstring).
- `CheckReport`: `repo: str | None`, `state: State | None`, `action: RepoAction | None`, `base: str | None`, nové pole `in_repo: bool = True`; `to_json` přidá `"in_repo"`. Ostatní klíče zůstanou, mimo repo jsou `null` (`backlog` `{}`, `sssf_leftover`/`alternate_rosters` `false`).

### `aifactory/src/aifactory/check/machine.py`
Rozšiř `Machine` Protocol a `SystemMachine` (vše jen čte):
- `run(self, argv, timeout=15, cwd: Path | None = None)`: `cwd` předej do `subprocess.run`.
- `platform(self) -> str`: `"darwin"`, `"linux"`, `"wsl"` nebo jiná hodnota `sys.platform`. Na linuxu je to `"wsl"`, když je nastaveno `WSL_DISTRO_NAME` nebo `/proc/sys/kernel/osrelease` obsahuje `microsoft` (case-insensitive, čtení chráněné `OSError`).
- `environment(self) -> Mapping[str, str]`: `dict(os.environ)`; předává se do `library_root`/`haifa_home`/`library_status`/`repo_items` jako `environ`.
- `file_mode(self, path: Path) -> int | None`: `stat.S_IMODE(path.stat().st_mode)` pro existující soubor, jinak None. Tím lze v testech napodobit mód.

### `aifactory/src/aifactory/check/context.py`
- `CheckContext.__init__(start, *, offline, machine, require_repo: bool = True)`: zkusí `main_checkout(start)`. Při `NotARepositoryError` a `require_repo=False` nastaví `self.main = None`, jinak výjimku propustí. Vlastnost `in_repo -> bool`.
- Všechny vlastnosti závislé na repu (`base`, `commit`, `state`, `settings`, `roster`, `remotes`, …) se volají jen v repu. Bezpečné výjimky: `roster` vrátí None a `settings` vrátí `ProjectSettings()`, když `main is None`. Typy uprav tak, aby mypy prošlo: `main: Path | None` a `assert self.main is not None` v repových vlastnostech, nebo zvlášť `_main` s vlastností, která asertuje. Zvol čistší variantu.
- Nové cached properties:
  - `environ -> Mapping[str, str]` = `self.machine.environment()`.
  - `library -> dict[str, Any] | None` a `library_error -> str | None`: jedno volání `library_status(fetch=False, environ=self.environ)`. `LibraryStoreError` s kódem `library_missing` dá `library=None`; jiné chyby (`LibraryStoreError`, `ProviderError`, `OSError`) propadnou z pravidla jako `check_failed`.
  - `items -> list[dict[str, Any]]`: jen pro stav `onboarded` bez `manifest_error`, jinak `[]`. Volá `repo_items(self.main, self.base, self.environ)["items"]`; `repo_items` si base rozbalí do dočasného adresáře mimo repo.

### `aifactory/src/aifactory/check/__init__.py`
- `RULE_GROUPS = [REPO_GROUP, MACHINE_GROUP, LIBRARY_GROUP]`.
- `run_check(repo, *, offline=False, machine=None, groups=None, require_repo=True)`. Mimo repo (`not ctx.in_repo`) přeskoč pravidla s `needs_repo=True`, `installed` nepočítej a vrať `CheckReport(repo=None, state=None, action=None, base=None, commit=None, remote=None, ahead=None, behind=None, in_repo=False, ...)`.
- `_EXPECTED` doplň o `LibraryStoreError` a `ProviderError` (`aifactory.providers.base`).
- Docstring modulu: tři scope, chování mimo repo, `--offline`.
- Exportuj `LIBRARY_GROUP`.

### `aifactory/src/aifactory/check/machine_rules.py` (úpravy a nová pravidla)
Pomocná funkce `_outside(ctx) -> bool` = `not ctx.in_repo`.
- `platform` (`needs_repo=False, needs_install=False`): `unsupported_platform`, error, když `ctx.machine.platform()` není v `{"darwin", "linux", "wsl"}`. Oprava: „HAIFA runs on macOS, Linux and WSL; on Windows use WSL“.
- `tools` (`needs_repo=False, needs_install=False`):
  - `git_missing` (error) bez `git` na PATH;
  - `git_identity_missing` (error), když chybí `user.name` nebo `user.email`. Hodnota platí, když jsou nastaveny obě proměnné `GIT_AUTHOR_*` a `GIT_COMMITTER_*` (přes `ctx.machine.env`), jinak rozhoduje `ctx.machine.run(["git", "config", "--get", key], cwd=ctx.main)` s rc 0 a neprázdným stdout. S chybějícím gitem se přeskočí. Oprava: `git config --global user.name/user.email`;
  - `uv_missing` (warning): `uv` instaluje a aktualizuje HAIFA, `factory upgrade`.
- `harnesses` (`needs_install=False, needs_repo=False`): v repu s rosterem jako dosud (error podle rosteru). V repu bez rosteru nic. **Mimo repo** projde všechny tři `HARNESSES`; chybějící dá `harness_missing` se severity `info`, zprávou „not installed (optional; needed by repos whose roster uses it)“ a opravou instalace.
- `node` (`needs_repo=True`): `node_missing` (error), když roster používá `pi` a `node` není na PATH.
- `test_program` → kód `test_command_missing` (logika stejná).
- `logins` (`needs_repo=False, needs_install=False`), celé přeskočit s `ctx.offline`:
  - Binárka harnessu je `ctx.machine.env(CLI_BINARIES[name][0]) or CLI_BINARIES[name][1]`. Kontroluj jen harnessy, jejichž binárka je na PATH (`ctx.machine.which`), aby se nález neopakoval s `harness_missing`.
  - Které harnessy: v repu ty z rosteru (severity error), mimo repo všechny nainstalované (severity warning).
  - claude: `[bin, "auth", "status"]`; codex: `[bin, "login", "status"]`; pi: pro každý odlišný model pi agentů `[bin, "auth", "check", "--model", model, "--json", "--no-refresh"]`. Mimo repo pi bez modelu přeskoč.
  - Neúspěch znamená `None` nebo rc != 0, u pi navíc stdout jako JSON objekt s `ok` nebo `authenticated` rovným `false`; nečitelný JSON při rc 0 je úspěch. Nález `harness_login` se zprávou „<harness> is not logged in (agents: …)“ a opravou `claude auth login` / `codex login` / `pi auth login` (pi: „log in to the provider of <model>“).
  - `pi_model_unknown` (error, jen v repu s pi): jednou `ctx.machine.run([pi_bin, "--list-models"], timeout=30)`. Parsuj jako `agent_pi._pi_catalog` (přeskoč hlavičku, sloupce 0 a 1 = provider a id) a porovnej jako `agent_pi.resolve_model`: `provider/id` přesně, jinak jediná přesná nebo jediná podřetězcová shoda. Logiku napiš jako čistou funkci `match_pi_model(catalog, pattern) -> Literal["ok", "missing", "ambiguous"]` v `check/`; `engine/agent_pi.py` neměň a nevolej `_pi_catalog` (jde mimo `Machine`). Model `missing` nebo `ambiguous` dá nález s opravou „register/authenticate it in pi, or fix model in .factory/agents.yaml“. Když `--list-models` selže (None nebo rc != 0), `pi_model_unknown` nehlas; chybu pokryje `harness_login`.
- `hosting`: kódy `gh_login` a `az_login` místo starých. Mimo repo se nespouští (`needs_repo=True`, jako dosud). `hosting_skipped` zůstává a jeho zpráva bude „--offline: logins to <provider> and the harnesses were not checked“. Mimo repo s `--offline` žádný nový nález nevzniká, stačí `data.offline: true`.
- `environment` (`needs_repo=False, needs_install=False`):
  - `env_file_mode` (warning): `path = env_file(ctx.environ)`, `mode = ctx.machine.file_mode(path)`; nález, když mode není None, není 0o600 a platforma není `win32`. Oprava `chmod 600 <path>`.
  - `env_override` (info) pro každou proměnnou z `("CLAUDE_SAFE_MODE", "CLAUDE_MCP_CONFIG", "CLAUDE_PERMISSION_MODE", "CODEX_SAFE_MODE", "CODEX_SANDBOX", "PI_SAFE_MODE")`, která je neprázdná: „<VAR>=<value> is set on this machine; it changes how every run of this harness behaves“. Oprava „unset it unless you want it (in the shell or $HAIFA_HOME/env)“. Hodnotu `CLAUDE_MCP_CONFIG` vypiš celou, je to cesta.
- `isolation` (`codex_not_isolated`, `pi_not_isolated`) zůstává jen v repu s rosterem.
- `factory_outdated` (scope `machine`, error, `needs_repo=False, needs_install=False`): `ctx.library` existuje a `compatible is False`. Zpráva „the library needs factory <min>, installed <__version__>“, oprava `factory upgrade`. Pravidlo může sedět v `library_rules.py`, ale scope nálezu je `"machine"`.

### Nový `aifactory/src/aifactory/check/library_rules.py`
`LIBRARY_GROUP = RuleGroup("library", (...), scope="library")`, všechna pravidla `needs_repo=False, needs_install=False`:
- `library_missing` (warning, `ctx.library is None`): „no library at <library_root(environ)>“, oprava „factory library clone URL (team library) or factory library init“. Ostatní pravidla knihovny se pak přeskočí.
- `library_dirty` (warning, `data["dirty"]`): počet a první položky `uncommitted`, oprava „commit or discard them in <path> (git -C <path> status)“.
- `library_behind` (warning, `behind > 0`), oprava `factory library pull`; `library_unpushed` (warning, `ahead > 0`), oprava `factory library push`. Zpráva uvede „as of the last fetch (<last_fetch or never>)“. Bez remote nic.
- `seed_update_available` (info, `data["seed_update_available"]`): seznam `seed_updates` (zkrácený, viz `_ids` v `repo_rules`), oprava `factory library seed`.
- `factory_outdated` (viz výše).

### `aifactory/src/aifactory/check/repo_rules.py`
- `items` (`needs_install=True`): pro každý řádek `ctx.items` se stavem != `synced` jedna `Finding` podle rozhodnutí 4. Literál volej ve větvích `if/elif` nad stavem. Zpráva „<type> <name> is <state> (repo <short>, manifest <short>, library <short>)“; zkratky jsou v řádku `short`. Opravy: `factory config export`/`update`/`adopt` (popis slovy; příkazy update a export zatím neexistují, viz skill).
- `workflows`: když `cfg.manifest is not None` a `TaskRunError.code == "unknown_workflow"`, vydej `workflow_not_in_repo` (error) se zprávou „backlog in <base> names workflow '<name>' (tasks …), which this repo with a manifest does not have in .factory/workflows/“ a opravou „factory config add workflow <name>, or change the tasks“. Bez manifestu dál `workflow_unknown`.
- `roles` (`needs_install=True`): `roles_full_copy` (info), když `ctx.base_file(".factory/roles.yaml")` je YAML mapping s klíčem `code_steps`. Oprava „keep only the roles you change (no code_steps) so the file overlays the packaged registry“. Nečitelný YAML ignoruj, pokryje ho `base_config_invalid`.
- `thinking` (`needs_install=True`): `unknown_thinking` (warning) pro každého agenta rosteru s `thinking` mimo `THINKING_LEVELS`. Oprava „set thinking to one of off|minimal|…|max in .factory/agents.yaml“.
- `sssf_leftover` už existuje, nech ho.

### `aifactory/src/aifactory/config/loader.py`
Přidej `load_roster_file(path: str | Path) -> SSSFConfig`: malý `ConfigSource`, který na `AGENTS_FILE` vrátí text souboru `path` a pro `label` vrátí `str(path)`. Projde `_Reader` a `_load_agents`. Chybějící nebo nečitelný soubor (`OSError`, `UnicodeDecodeError`) i issues vyhodí `ConfigError(issues)`.

### `aifactory/src/aifactory/cli.py`
- `_harness`: `--config` načti přes `load_roster_file`; `ConfigError` (a `OSError`) předej `_fail_from_exception(exc, args.json, "factory harness check")`, tedy obálku `invalid_config` s exit 2. Nápověda `--config`: „HAIFA roster (.factory/agents.yaml)…“. Import `harness.config.load_config` tu odpadne.
- `_check`: `require_repo=args.repo is not None`; `run_check(start, offline=..., require_repo=...)`. Text mimo repo vypíše „state:   outside a git repository (machine and library only)“, řádky `remote:` vynechá a `scope` vypíše šířkou 7 (`library` se vejde).
- Popis parseru `check` (`_add_check_command`): scope `library`, chování mimo repo (bez `--repo`), `--offline` vynechá hosting, přihlášení harnessů a katalog pi, akce `export`. Exit 2 jen pro `--repo`, které není git repo.
- `_dispatch` s `command is None`: po `parser.print_help()` vypiš prázdný řádek a „První spuštění: factory check“ (přesně tento text).
- Docstring modulu nech, případně doplň.

### `aifactory/src/aifactory/skill/codes.py`
`ISSUE_CODES["check"]`: odstraň `test_program_missing`, `gh_not_logged_in` a `az_not_logged_in`. Přidej `unsupported_platform`, `git_missing`, `git_identity_missing`, `uv_missing`, `node_missing`, `test_command_missing`, `harness_login`, `pi_model_unknown`, `gh_login`, `az_login`, `factory_outdated`, `library_missing`, `library_dirty`, `library_behind`, `library_unpushed`, `seed_update_available`, `env_file_mode`, `env_override`, `item_local`, `item_missing`, `item_unknown`, `item_outdated`, `item_modified`, `item_diverged`, `workflow_not_in_repo`, `roles_full_copy` a `unknown_thinking`. Seznam musí přesně sedět s literály v `check/`. Pokud codes.py jinde vyjmenovává hodnoty `Action` nebo scope (grep `config_pull`), přidej tam `export` a `library`.

### `aifactory/src/aifactory/skill/skill.md`
Sekce `### Check` (zachovej texty, které testy hledají: „factory check“, „--offline“, „scope: repo“, „scope: machine“, „action“, „only by reading“):
- mimo repo jen stroj a knihovnu (`data.in_repo: false`, `repo`/`state`/`action` jsou `null`);
- `scope: library` (opravuje se v knihovně v `$HAIFA_HOME`);
- tabulka nebo seznam nových kódů po skupinách (instalace, platforma a nástroje, harnessy, hosting, knihovna, prostředí, položky, repo navíc), u každého oprava;
- `--offline` vynechá `gh auth status`, `az account show`, přihlášení harnessů a `pi --list-models`;
- akce `export` a stavy položek → kódy `item_*`;
- exit 2 jen pro `--repo`, které není git repo;
- zmínka „První spuštění: factory check“ u úvodní rady (ř. ~12).

### Testy (`aifactory/tests/`)
Uprav `tests/check/factory_check_repo.py::FakeMachine`:
- `present` výchozí `{"just", "claude", "gh", "az", "git", "uv", "node"}`;
- pole `platform_name: str = "linux"` a metoda `platform()`;
- `environment()` vrátí `{"HAIFA_HOME": os.environ["HAIFA_HOME"], **self.environ}` (dočasný domov z conftest);
- výchozí `environ` obsahuje `GIT_AUTHOR_NAME`, `GIT_COMMITTER_NAME`, `GIT_AUTHOR_EMAIL` a `GIT_COMMITTER_EMAIL`, aby nebyl potřeba `git config`;
- `file_mode()` vrátí mód skutečného souboru, případně přepis ze slovníku `modes`;
- `run(argv, timeout, cwd=None)`;
- pole `outputs: dict[tuple[str, ...], Probe]` na scénáře (pi JSON, `--list-models`).

Pak oprav počty v existujících testech: `library_missing` (warning) se objeví všude, kde knihovna chybí, a podobně nové nálezy. Raději test zapiš nad množinou kódů než nad `counts`, nebo počty přepočítej. Přejmenované kódy oprav v `tests/check/test_factory_check.py` (ř. ~220, 306, 327, 330).

Nové testy:
- `tests/check/test_factory_check_machine.py` (FakeMachine): pro **každý** nový kód jeden test, který ho vyvolá, a negativní varianta. Konkrétně:
  - `unsupported_platform` (`platform_name="win32"`);
  - `git_missing`, `git_identity_missing` (bez env, `run` vrací rc 1), `uv_missing`;
  - `harness_missing` mimo repo jako `info` pro všechny tři;
  - `node_missing` (roster s pi), `test_command_missing`;
  - `harness_login` pro claude, codex i pi (rc 1, pi JSON `{"ok": false}`), `pi_model_unknown`;
  - `gh_login`, `az_login`;
  - `factory_outdated`, `library_missing`, `library_dirty`, `library_behind`, `library_unpushed`, `seed_update_available`;
  - `env_file_mode` (`env` s 0644 v `HAIFA_HOME`), `env_override` (každá z šesti proměnných, parametrizovaně), `codex_not_isolated`.

  Knihovnu stav v dočasném `HAIFA_HOME` přes `factory library init` (`aifactory.library.store.init_library`) s holým remote (`git init --bare`) a push. „Behind“ dosáhneš commitem v druhém klonu, pushem a `git fetch` v knihovně **v testu**. „Unpushed“ lokálním commitem v knihovně. Dirty vytvoříš souborem navíc. `min_factory_version` nastav commitem `library.yaml` s vysokou verzí. Seed update vznikne úpravou `seed` v `library.yaml`. Najdi existující helpery knihovny v `tests/library/` a použij je.
- `tests/check/test_factory_check_items.py`: onboarded repo (manifest) s položkami ve stavech local, outdated, modified, diverged, missing a unknown. Najdi helpery v `tests/library/` (stavy položek) nebo `tests/onboard/` a použij je. Ověř kód a akci. Dál `workflow_not_in_repo` (manifest a backlog s workflow mimo `.factory/workflows/`), `roles_full_copy`, `unknown_thinking` (`thinking: auto`) a `sssf_leftover` (už existuje, stačí aserce).
- `tests/check/test_factory_check_cli.py`:
  - mimo repo (cwd = `tmp_path` bez gitu, bez `--repo`): rc 0 nebo 1, `data.in_repo is False`, scope všech nálezů v `{"machine", "library"}`;
  - `--repo` mimo repo dál vrací rc 2.
- **Falešné binárky na PATH** (`tests/check/test_factory_check_system.py`, `SystemMachine`, `fake_exe.make_executable`):
  - fake skripty `claude`, `codex`, `pi`, `gh` a `az`; **git** zůstane skutečný, jinak nefungují repo testy;
  - každý skript zapíše svůj argv do logu v `tmp_path` a vrátí rc podle proměnné;
  - `PATH` = jen bin s fakes a adresář skutečného gitu (`shutil.which("git")`). Aby `uv`/`node` chyběly záměrně, nedávej celý systémový PATH;
  - test `--offline`: žádné volání hostingu ani přihlášení. `<harness> --version` (z `harnesses`) je povolené. Aserce: log neobsahuje `auth`, `login`, `account` ani `--list-models` a nejsou v něm volání `gh` ani `az`;
  - bez `--offline` log obsahuje `claude auth status`, `codex login status`, `pi auth check --model … --json --no-refresh` a `gh auth status …`.
- **Kontrola nic nemění:** snímek repa (`git status --porcelain`, `git rev-parse HEAD`, výpis souborů s mtime), knihovny (HEAD, status, refs) a `HAIFA_HOME` (rekurzivní výpis souborů a obsahů) před a po `main(["check", "--json"])` v repu i mimo něj. Musí být shodné, včetně toho, že bez knihovny nevznikne `$HAIFA_HOME/library` ani `library.lock`.
- `tests/harness/test_harness_check_cli.py`:
  - `_config` přepiš na roster HAIFA bez `prompt_engineering`;
  - nový test `harness check --config .factory/agents.yaml` (relativní cesta, `monkeypatch.chdir` do repa z `make_check_repo`) vrátí rc podle fake binárek;
  - test, že roster s `prompt_engineering` vrátí obálku `invalid_config` s exit 2 (`--json`), ne traceback;
  - test chybějícího souboru → obálka.
- `tests/test_smoke.py` nebo CLI test: `main([])` vypíše nápovědu a „První spuštění: factory check“, rc 0.
- `tests/test_skill.py`: projde s novými kódy. Případně přidej aserci „scope: library“ do `test_skill_describes_check`.

Testy nevolají model ani síť. Všechny `gh`, `az` a harnessy jsou fakes nebo `FakeMachine`, remote knihovny je lokální holé repo.

## Ověření

```bash
just test          # celá sada, nebo nejdřív: uv run pytest aifactory/tests/check aifactory/tests/harness aifactory/tests/test_skill.py -q
just typecheck
just lint
```
Ručně: `cd /tmp && factory check` (mimo repo, scope machine/library), `factory check --offline --json`, `factory harness check --config .factory/agents.yaml --json`, `factory` (nápověda a řádek „První spuštění: factory check“).

## Mimo zadání
Instalace nástrojů a přihlašování, `git fetch`, dashboard, `factory upgrade`, změny `engine/agent_pi.py`, `vendor/`, `prototype/`, `.factory/`.

## Rizika a pozor
- `library_status` vyhodí výjimku i u knihovny bez commitu (`library_missing`). Ostatní chyby nech propadnout jako `check_failed`.
- `repo_items` s `base` volá `resolve_commit` a `extract_factory` do tempdir. Volat jen pro `onboarded` stav; `ConfigError` pro neznámý formát manifestu pokryje `_EXPECTED`.
- `hist.history` čte knihovnu; ověř, že nevytváří `$HAIFA_HOME` (`_home_dir` se volá jen v `write_lock`).
- Změna typů `CheckReport` a `CheckContext.main` na Optional: mypy strict, oprav všechny použití.
- Kódy `Finding` vždy literálem (AST test).
