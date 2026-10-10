# HAIFA-S05-T05: Harnessy načítají instrukce a skilly repa nativně

## Co se změnilo a proč

Agenti factory dosud běželi úplně izolovaně: claude s `--safe-mode`, codex s `project_doc_max_bytes=0` a pi bez kontextu repa. Teď je výchozí **nativní načítání repa**. Agent běží, jako by harness spustil člověk z CLI v repu: čte CLAUDE.md, AGENTS.md a skilly repa. Osobní konfiguraci operátora harness nenačte všude, kde to umí. Roli agenta dál určuje jeho system prompt (`--system-prompt`, u codexu `developer_instructions`).

| Harness | Výchozí režim | `*_SAFE_MODE=1` |
|---|---|---|
| claude | `--setting-sources project,local` (načte `.claude/settings*.json`, CLAUDE.md a `.claude/skills/` repa, nic z `~/.claude`), dál `--strict-mcp-config` | `--safe-mode` (když není nastavené `CLAUDE_MCP_CONFIG`) |
| codex | čte AGENTS.md a `.agents/skills/`. Nově `--ignore-user-config` v obou režimech, takže se nenačte `~/.codex/config.toml` | navíc `-c project_doc_max_bytes=0` |
| pi | `--approve` (důvěra v projekt pro běh `-p`), `--no-skills --no-extensions --no-prompt-templates` a `--skill <repo>/.agents/skills`, pokud složka existuje | `--no-approve --no-context-files --no-skills --no-extensions --no-prompt-templates` |

Přepínače `CLAUDE_SAFE_MODE`, `CODEX_SAFE_MODE` a `PI_SAFE_MODE` mají teď výchozí hodnotu **vypnuto**. Dřív bylo výchozí `"1"`. Čtou se při každém volání přes `env_flag()`, ne při importu. Za zapnuté se bere cokoli kromě prázdné hodnoty, `0`, `false`, `no` a `off`.

### Zrcadlo skillů

Zdroj skillu je v `.claude/skills/<jméno>/`, odkud ho čte claude. Přesná kopie bez symlinků leží v `.agents/skills/<jméno>/`, odkud ji čtou codex a pi. Nový příkaz `factory skills sync` kopii zapíše do pracovního stromu: přidá nové skilly, přepíše změněné a smaže ty, které ve zdroji už nejsou. Za změnu se počítá i samotná změna exec bitu. Ostatního obsahu `.agents/` se příkaz nedotkne. Commit výsledku zůstává na vás.

### Nová hlášení `factory check`

- Scope `repo`, pravidlo „skills mirror“: porovnává oba stromy v **base commitu** přes `git ls-tree` a hlásí varování `skill_mirror_missing`, `skill_mirror_differs` a `skill_mirror_extra`.
- Scope `machine`, pravidlo „harness isolation“: hlásí globální soubory operátora, které harness neumí vynechat. Kontroluje jen harnessy použité v rosteru, a to mimo safe mode.
  - `codex_not_isolated`: `$CODEX_HOME` (výchozí `~/.codex`) `/AGENTS.md`, `/AGENTS.override.md`, `/skills` a dále `~/.agents/skills`.
  - `pi_not_isolated`: `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md` a `APPEND_SYSTEM.md` v `$PI_CODING_AGENT_DIR` (výchozí `~/.pi/agent`). Pi je neumí vypustit, aniž by zahodil i AGENTS.md a CLAUDE.md repa.

  Prázdné adresáře se nehlásí. Domovský adresář se jen čte, a to přes novou metodu `Machine.home()`.

## Kde to je

- `aifactory/src/aifactory/engine/agent_cc.py`: místo konstanty `SAFE_MODE` funkce `safe_mode()` a konstanta `SETTING_SOURCES`. Sestavuje argv.
- `aifactory/src/aifactory/harness/codex.py`: `safe_mode()`, přidaný `--ignore-user-config` v `build_command`.
- `aifactory/src/aifactory/engine/agent_pi.py`: `safe_mode()`, `isolation_args(cwd)` a `REPO_SKILLS_DIR`.
- `aifactory/src/aifactory/engine/utils.py`: `flag_value()` a `env_flag()`.
- `aifactory/src/aifactory/harness/repo_skills.py` (nový): `SOURCE`, `MIRROR`, `sync()`, `diff_snapshots()`, `worktree_snapshot()` a `commit_snapshot()`.
- `aifactory/src/aifactory/cli.py`: podpříkaz `skills` / `skills sync [--repo PATH] [--json]`.
- `aifactory/src/aifactory/check/repo_rules.py` (`skills_mirror`), `check/machine_rules.py` (`isolation`) a `check/machine.py` (`home()`).
- `aifactory/src/aifactory/skill/skill.md`: nová sekce „Repo instructions and skills“. `skill/codes.py`: kód chyby `skills_sync_failed` (exit 2) a nové kódy nálezů pro `factory check`.
- Úpravy v `engine/` mají značku `# aifactory`.

## Jak to použít a ověřit

```sh
factory skills sync              # vypíše added/updated/removed, nebo "… is up to date"
factory skills sync --json       # data.added, data.updated, data.removed, data.source, data.mirror
factory check                    # skill_mirror_* (repo), codex_not_isolated / pi_not_isolated (machine)
CLAUDE_SAFE_MODE=1 CODEX_SAFE_MODE=1 PI_SAFE_MODE=1 factory task run …   # úplná izolace jako dřív
```

Když cesta není git repo, `factory skills sync` vrátí kód 2 s chybou konfigurace. Když nejde zapsat zrcadlo, vrátí kód 2 s chybou `skills_sync_failed`.

Testy (nevolají model ani síť, harness podvrhují přes `fake_popen` z `tests/harness/harness_fakes.py`):

- `aifactory/tests/harness/test_harness_repo_native.py`: argv claude, codex a pi ve výchozím režimu i se `*_SAFE_MODE=1`, kombinace s `CLAUDE_MCP_CONFIG`, důvěra v projekt a `--skill` u pi a vyhodnocení přepínačů.
- `aifactory/tests/harness/test_repo_skills.py`: přesná kopie, samotný exec bit jako změna, úklid zrcadla bez zdroje a shoda snapshotu z commitu se snapshotem z pracovního stromu.
- `aifactory/tests/harness/test_skills_sync_cli.py`: výstup CLI v JSON i jako text, běh mimo repo, chyba zápisu a nápověda.
- `aifactory/tests/check/test_factory_check.py`: nálezy `skill_mirror_*` a `*_not_isolated`. Roster jen s claude nehlásí nic. `FakeMachine` v `tests/check/factory_check_repo.py` dostal `home()`.
- `aifactory/tests/test_skill.py`: kontroluje novou sekci skillu. `aifactory/tests/test_smoke.py`: `skills` patří mezi implementované podpříkazy.

Spuštění: `just test`, `just typecheck`, `just lint`.
