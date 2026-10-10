# Konfigurace projektu v `.factory/` čtená z commitu `base`

## Co se změnilo a proč

Přibyl balíček `aifactory.config`, který načítá celou konfiguraci projektu z `.factory/`. Běh ji nečte z pracovního stromu, ale ze stromu commitu, na který ukazuje `base`, a to přímo z objektové databáze (`git ls-tree` / `git cat-file`). Nedělá se checkout, nezakládá se worktree a index zůstává beze změny. Dva běhy spuštěné ze stejného commitu tak dostanou stejnou konfiguraci, i když se pracovní strom mezi nimi změní. Necommitnuté úpravy sdílené konfigurace se vracejí jako varování.

`.factory/local.yaml` (port, cesta k trace DB) se čte vždy jen z disku. `CommitSource.read_text(".factory/local.yaml")` vyhodí `ValueError`. `.gitignore` teď kromě `local.yaml` ignoruje i `.factory/trace.db*`.

## Soubory

| Soubor | Obsah |
|---|---|
| `aifactory/src/aifactory/config/source.py` | `ConfigSource` (Protocol), `WorktreeSource` (disk), `CommitSource` (strom commitu bez checkoutu), `repo_root`, `resolve_commit`, `GitError` |
| `aifactory/src/aifactory/config/settings.py` | `ProjectSettings` (`config.yaml`) a `LocalSettings` (`local.yaml`, výchozí `port: 4700`, `trace_db: .factory/trace.db`), `load_local` |
| `aifactory/src/aifactory/config/loader.py` | `load_config(source)` → `FactoryConfig` (settings, agents, roles, prompts, workflows, `digest`), `load_worktree_config`, `write_prompts` |
| `aifactory/src/aifactory/config/run.py` | `load_run_config(root, base=None)` → `RunConfig` (včetně `warnings`), `worktree_base` |
| `aifactory/src/aifactory/config/status.py` | `config_changes(root, sha)`, `change_warnings(...)`, `ConfigChange` |
| `aifactory/src/aifactory/config/errors.py` | `ConfigError` se seznamem `ConfigIssue(path, message)` |
| `aifactory/src/aifactory/config/__init__.py` | veřejné API balíčku |
| `aifactory/src/aifactory/cli.py` | příkazy `factory config status` a `factory config show` |
| `aifactory/tests/config/*` | testy v dočasných git repech (pomocník `config_repo.py`) |
| `aifactory/tests/test_smoke.py` | `config` už nepatří mezi neimplementované příkazy |
| `specs/6cf89842_factory-config-from-base.md` | plán |

## Chování načítání

- **`config.yaml`**: chybějící nebo prázdný soubor dává výchozí hodnoty (`base: main`, `levels: [module, step, task]`, `git_provider: local`, `merge_strategy: squash`, `protected_files: [.factory/]` …). Neznámé klíče jsou chyba. `port` a `trace_db` v něm jsou chyba s odkazem na `local.yaml`. `test_command` lze zapsat jako řetězec (rozdělí se přes `shlex`) i jako seznam.
- **`agents.yaml`**: chybějící soubor znamená prázdný seznam agentů. Klíč `prompt_engineering` je zakázaný, protože cesty k promptům se doplní automaticky na `.factory/prompts/<agent>/{system,user}.md`.
- **`roles.yaml`**: pokud chybí, použije se zabalený výchozí registr (`load_roles()`).
- **`prompts/<agent>/{system,user}.md`**: když chybí prompt agenta deklarovaného v `agents.yaml`, je to chyba. Nalezené prompty nedeklarovaných agentů se také načtou.
- **`workflows/*.yaml`**: čtou se jen soubory přímo v adresáři s příponou `.yaml` a klíčem je název souboru bez přípony. Kořen souboru musí být mapping.
- Chyby ze všech souborů se posbírají a vyhodí najednou jako `ConfigError`. Každá nese cestu: u disku absolutní, u commitu ve tvaru `main@abc1234:.factory/agents.yaml`.
- `base` se bere z argumentu, jinak z klíče `base` v `config.yaml` **v pracovním stromu**. Jen tento jediný klíč se čte z disku, protože určuje, odkud číst zbytek. Pokud soubor ani klíč neexistuje, platí `main`. Když se commitnutý `base` liší od použitého, přidá se varování.
- `FactoryConfig.digest` je sha256 přes všechny přečtené soubory. Stejný digest znamená stejnou konfiguraci.

## Varování

`config_changes` sestavuje seznam z výstupů `git diff --name-status <sha> -- .factory` a `git ls-files --others --exclude-standard`. Hlásí jen sdílené cesty: `config.yaml`, `agents.yaml`, `roles.yaml`, `prompts/` a `workflows/`. Stavy jsou `modified`, `added`, `deleted` a `untracked`. `local.yaml`, worktrees a trace DB se nehlásí nikdy. Pro každou změnu vznikne jedno varování:
`<path> is <status> in the working tree but not committed to <base> (<sha7>); runs use the committed version`.

## Použití

```sh
factory config status [--json] [--base REF]  # necommitnuté změny v .factory/ proti base
factory config show   [--json] [--base REF]  # konfigurace, kterou by použil běh (+ warnings)
```

`status --json` vrací `{ok, base, commit, clean, changes, warnings}`. `show --json` vrací `RunConfig.to_json()` (base, commit, source, digest, agents, roles, workflows, prompts, settings, local, changes, warnings). Při chybě konfigurace nebo gitu vrací příkaz exit kód 2 a `{ok: false, error, issues}`. `config` bez podpříkazu vypíše nápovědu.

Z kódu:

```python
from aifactory.config import load_run_config
run = load_run_config(Path.cwd())      # RunConfig: .config, .local, .changes, .warnings
```

## Ověření

```sh
just test tests/config   # nebo celé: just test
just typecheck
just lint
```

Klíčové testy jsou v `aifactory/tests/config/test_config_commit.py`:
- `test_uncommitted_prompt_and_agents_stay_out_of_the_run`: necommitnutá úprava promptu i `agents.yaml` se do běhu nedostane a objeví se ve `warnings`,
- `test_two_runs_from_one_commit_get_the_same_config`: dva běhy mají stejný digest,
- `test_loading_does_not_touch_the_checkout`: HEAD, `git status` ani seznam worktree se nezmění,
- `test_local_yaml_is_never_read_from_base`.
