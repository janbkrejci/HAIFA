# HAIFA-S07-T02: Kontrola stroje, knihovny a položek ve `factory check`

## Co se změnilo

`factory check` teď kolegovi řekne, co na stroji chybí pro HAIFA a jeho repa. Kontrola dál jen čte: nezapisuje do repa, trace DB, knihovny ani domova a nic nefetchuje.

- **Mimo git repo** (bez `--repo`) kontrola nespadne. Spustí jen pravidla s `needs_repo=False` (stroj a knihovna) a vrátí report s `in_repo: false`. Pole `repo`, `state`, `action`, `base` a další pole repa jsou `null`. Explicitní `--repo` mimo repo dál končí kódem 2. Návratové kódy zůstávají 0, 1 a 2.
- **Nový scope `library`** a skupina pravidel `LIBRARY_GROUP`. Nová akce `export`.
- **`--offline`** teď kromě hostingu vynechá i přihlášení harnessů (`claude auth status`, `codex login status`, `pi auth check`, `pi --list-models`). U workflow v repu offline jen ověří, že agenti jsou v rosteru (`_roster_only`), a neresolvuje modely přes pi.

### Nové nálezy

| Skupina | Kódy |
|---|---|
| Platforma a nástroje (`machine`) | `unsupported_platform` (jen darwin, linux, wsl), `git_missing`, `git_identity_missing` (bere ohled i na `GIT_AUTHOR_*`/`GIT_COMMITTER_*`), `uv_missing`, `node_missing` (roster s pi) |
| Harnessy (`machine`) | `harness_missing`: mimo repo `info` pro claude, codex i pi. `harness_login` z `claude auth status`, `codex login status` a `pi auth check --model M --json --no-refresh` (mimo repo `warning`, v repu `error`). `pi_model_unknown` z `pi --list-models` (chybí nebo je nejednoznačný, jen v repu) |
| Hosting | přejmenováno: `gh_not_logged_in` → `gh_login`, `az_not_logged_in` → `az_login`, `test_program_missing` → `test_command_missing` |
| Prostředí (`machine`) | `env_file_mode` (`$HAIFA_HOME/env` má jiný režim než 0600), `env_override` (nastavená `CLAUDE_SAFE_MODE`, `CLAUDE_MCP_CONFIG`, `CLAUDE_PERMISSION_MODE`, `CODEX_SAFE_MODE`, `CODEX_SANDBOX` nebo `PI_SAFE_MODE`) |
| Instalace a knihovna | `factory_outdated` (`machine`, `error`: knihovna má vyšší `min_factory_version`), `library_missing`, `library_dirty`, `library_behind`, `library_unpushed` (podle posledních refů, bez fetch) a `seed_update_available` |
| Položky v base (`repo`) | `item_local` (export), `item_missing` (update), `item_unknown` (adopt), `item_outdated` (update), `item_modified` (export) a `item_diverged` (update). Hlásí se jen u onboardovaného repa s manifestem |
| Konfigurace repa | `workflow_not_in_repo` (backlog jmenuje workflow, které repo s manifestem nemá), `roles_full_copy` (`.factory/roles.yaml` obsahuje `code_steps`) a `unknown_thinking` |

`codex_not_isolated` a `sssf_leftover` existovaly už dřív. Nově je popisuje `skill.md` a mají testy.

### Další změny

- `factory harness check --config CESTA` načítá roster loaderem HAIFA (`load_roster_file`). Chyby `ConfigError` vrací jako obálku. Roster s `prompt_engineering` už nespadne.
- `factory` bez příkazu vypíše za nápovědou řádek „První spuštění: factory check“.
- Knihovní historie dostala přepínač `save` / `save_cache=False`. Díky němu `factory check` čte stavy položek bez zápisu cache do `$HAIFA_HOME`.

## Kde to je

- `aifactory/src/aifactory/check/__init__.py`: `run_check(..., require_repo=)`, `_outside_report`, `LIBRARY_GROUP` v `RULE_GROUPS` a rozšířené `_EXPECTED` (`LibraryStoreError`, `ProviderError`).
- `check/context.py`: `in_repo`, líné `environ`, `library` (`library_status(fetch=False)`) a `items` (`repo_items(..., save_cache=False)`).
- `check/machine.py`: rozhraní `Machine` dostalo `run(cwd=)`, `platform()` (rozpozná WSL), `environment()` a `file_mode()`.
- `check/machine_rules.py`: pravidla `platform`, `tools`, `node`, `logins`, `environment`, nález `harness_missing` mimo repo a pomocné `pi_catalog` a `match_pi_model`.
- `check/library_rules.py` (nový soubor): pravidla `factory version`, `library` a `seed`.
- `check/repo_rules.py`: pravidla `items`, `roles` a `thinking`, nález `workflow_not_in_repo` a offline `_roster_only`.
- `check/model.py`: `Scope` s hodnotou `library`, `Action` s hodnotou `export`, `Rule.needs_repo` a `CheckReport.in_repo`.
- `cli.py`: nápověda a výpis `factory check`, `harness check --config` a hint „První spuštění“.
- `config/loader.py`: `load_roster_file`.
- `library/history.py` a `library/state.py`: parametr `save` / `save_cache`.
- `skill/codes.py` (nové kódy) a `skill/skill.md` (nálezy a opravy podle skupin).

## Jak ověřit

```bash
cd /tmp && factory check            # mimo repo: jen machine + library, in_repo false
factory check --offline --json      # v repu bez volání gh/az/claude/codex/pi
factory harness check --config .factory/agents.yaml
factory                             # nápověda + „První spuštění: factory check“
just test && just typecheck && just lint
```

Testy jsou v `aifactory/tests/check/` a stroj v nich nahrazuje `FakeMachine` z `factory_check_repo.py`:

- `test_factory_check_machine.py`: jeden test na každý kód stroje, přihlášení, knihovny a prostředí, `match_pi_model` a `--offline` bez přihlášení.
- `test_factory_check_items.py`: stavy položek, `workflow_not_in_repo`, `roles_full_copy`, `unknown_thinking` a `sssf_leftover`.
- `test_factory_check_system.py`: falešné binárky na PATH. Ověřuje, že offline nevolá přihlášení ani hosting, online volá všechna, běh mimo repo a že kontrola nezmění repo, knihovnu ani domov.
- `test_factory_check_cli.py`: běh mimo repo, exit 2 s explicitním `--repo` a hint bez příkazu.
- `aifactory/tests/harness/test_harness_check_cli.py`: roster HAIFA s relativní cestou a roster s `prompt_engineering` jako obálka.
