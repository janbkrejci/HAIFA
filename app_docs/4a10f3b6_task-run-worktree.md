# `haifa-proto task run` / `task show`: spuštění tasku ve vlastním worktree

Spec: `specs/4a10f3b6_task-run-worktree.md`

## Co se změnilo

Task z backlogu se dá spustit příkazem `haifa-proto task run <task-id>`. Běh dostane vlastní git worktree a větev vytvořenou z `base`, workflow tasku v něm poběží s cwd ve worktree a agenti smí měnit jen `writes` tasku. Každý běh má řádek v tabulce `task_runs` v trace DB. `haifa-proto task show <task-id>` vypíše task a jeho běhy. Implementuje kroky 1–3 sekce „Běh úkolu“ z produktového briefu. Push, PR a zápis `status: done` do souboru tasku tu nejsou.

## Průběh běhu (`run.py`, `run_task`)

1. **Kontroly před startem.** Pokud některá selže, vyhodí se `TaskRunError(code, message)` a nic se nevytvoří. Kódy chyb:
   - `unknown_task`: task neexistuje nebo id patří kontejneru.
   - `task_not_in_base`: task je jen ve working tree, ne v commitu `base`.
   - `already_running`: task už běží. `--force` tuto kontrolu nikdy nepřeskočí.
   - `unmet_dependencies`: `depends_on` nejsou hotové v `base`. `--force` tuto kontrolu přeskočí.
   - `no_writes`, `invalid_writes`: task nemá použitelné `writes`.
   - `no_workflow`, `unknown_workflow`, `invalid_workflow`: workflow tasku chybí, nenajde se nebo je neplatné.
   - `invalid_config`, `unknown_base`: chyba konfigurace nebo `base` neukazuje na commit.
2. **Odkud se co čte.** Backlog, `.factory/workflows/` a `.factory/roles.yaml` se berou z commitu `base`. Rozbalí se přes `git archive` do dočasného adresáře, working tree se nepoužívá. Workflow se hledá nejdřív v `.factory/workflows/<name>.yaml` v `base` a potom mezi zabalenými workflow. Z hlavního checkoutu se čte `.factory/config.yaml` a konfigurace agentů (`agents_config`).
3. **Worktree a větev.** Worktree vzniká v `<worktrees_dir>/<run-id>` a větev se jmenuje `factory/<task-id>-<n>`. Číslo `n` je o jedna vyšší než nejvyšší číslo mezi existujícími větvemi a větvemi zapsanými v `task_runs`. Adresář worktrees se přidá do `.git/info/exclude`, takže hlavní checkout zůstane v `git status` čistý.
4. **Spuštění workflow.** Workflow běží přes `os.chdir(worktree)` a `run_workflow(..., adw_id=run_id)`. Konfigurace sssf se před během zkopíruje a `defaults.data_dir` a `observability.db` se v kopii nastaví na absolutní cesty do hlavního checkoutu. Díky tomu session runtime a trace DB sdílejí všechny běhy. Signal handlery enginu se po běhu obnoví.
5. **Konec běhu.** Stav je `succeeded`, jen když workflow skončí s `accepted` a `exit_code == 0`. Jinak je `failed` s textem chyby. Do řádku se zapíše `head_sha` worktree. Worktree neúspěšného běhu zůstává na disku.

**Prompt agentů** (`task_prompt`) má tuto strukturu:
- hlavička `# Task <id>: <title>`,
- řádky id, title, kontejnery (modul/step), `source`, `target` (`(not set)`, pokud chybí), `allowed paths` a upozornění, že zápis mimo povolené cesty se vrátí,
- tělo tasku,
- sekce `## Note` s obsahem `--note`, pokud je zadaná.

## Omezení zápisu (`scope.py`)

- `effective_writes(task)` vrátí vlastní `writes` tasku. Když je task nemá, převezme je od nejbližšího kontejneru (`extra` nebo `defaults`). Pokud tam hodnota není seznam řetězců, vyhodí `ScopeError`.
- `TaskScope.paths` obsahuje `writes` a navíc `specs_dir/` a `docs_dir/`. Jde o záměrnou odchylku od briefu: planner a documenter zapisují plán a dokumentaci do repa.
- `matches()` používá stejné porovnávání cest jako engine. Cesta bez wildcardu navíc pokrývá celý svůj podstrom.
- `enforce_task_scope(scope)` na dobu běhu dočasně nahradí `permissions.permitted` a `permissions.enforce` z enginu. Cesta je povolená, jen když ji povolí agent **i** task (průnik). `always_writable` zůstává zapisovatelné. Při porušení se do `PermissionBreach` doplní text „task … may only change […]“. Engine změny mimo rozsah vrátí a fáze selže. Po skončení se vrátí původní funkce. `vendor/` se nemění.

## Tabulka `task_runs` a CLI

- Tabulka `task_runs` je v trace DB na vlastním sqlite spojení. Sloupce: `run_id`, `task_id`, `branch`, `worktree`, `base`, `base_sha`, `head_sha`, `state`, `started_at`, `ended_at`, `pid`, `workflow`, `note`, `error`.
- Stavy: `running`, `succeeded`, `failed`, `aborted`.
- `claim()` v transakci `BEGIN IMMEDIATE` atomicky zkontroluje, že task neběží, a vloží řádek. Řádek `running`, jehož proces už neexistuje (podle `pid`), se před kontrolou přepíše na `aborted`.
- Cesta k DB se bere z `observability.db` v konfiguraci agentů, výchozí je `adws/adw_data/sssf.db`.
- `task_runs_for(repo, task_id)` vrací běhy tasku od nejnovějšího.
- `cli.py`: přibyly `task run <id> [--note] [--force]` a `task show <id>`, oba s volbami `--repo` a `--json`.
  - `run` vrátí exit 0 jen při `succeeded`.
  - S `--json` jde průběh běhu na stderr a stdout obsahuje jen JSON: `{"ok", "run"}`, případně `{"ok": false, "error": {code, message}}`.
  - `show` vypíše task (stav, `writes`, workflow) a jeho běhy.
- `config.py`: nové klíče `base` (výchozí `main`), `worktrees_dir` (`.factory/worktrees`), `agents_config` (`adws/adw_sssf_config/sssf.config.yaml`), `specs_dir` (`specs`) a `docs_dir` (`app_docs`). Cesty musí být neprázdné a relativní vůči repu.

## Soubory

| Soubor | Role |
|---|---|
| `prototype/src/haifa_proto/run.py` | `run_task`, `TaskRunStore`, git operace, prompt |
| `prototype/src/haifa_proto/scope.py` | `effective_writes`, `TaskScope`, `enforce_task_scope` |
| `prototype/src/haifa_proto/cli.py` | podpříkazy `task run` / `task show` |
| `prototype/src/haifa_proto/config.py` | nové klíče konfigurace |
| `prototype/tests/task_repo.py` | dočasné git repo s commitnutým backlogem a workflow `build-commit` |
| `prototype/tests/workflow_fakes.py` | falešný harness zaznamenává `cwd`, `Script.on()` simuluje zápisy agenta |
| `prototype/tests/test_task_run.py`, `test_scope.py`, `test_cli_task.py`, `test_config.py` | testy |

## Ověření

```sh
cd prototype && uv run pytest tests/test_task_run.py tests/test_scope.py tests/test_cli_task.py tests/test_config.py
```

Testy v `test_task_run.py`:
- `test_run_creates_branch_and_worktree`: vznikne větev a worktree, commit je jen na větvi, hlavní checkout je beze změny a `task_runs` má řádek.
- `test_write_outside_scope_is_reverted_and_fails`: zápisy do `README.md` a `other/new.py` se vrátí, běh skončí `failed` a `head_sha == base_sha`.
- `test_second_run_of_running_task_fails`: vrátí `already_running` i s `--force`, nevznikne větev ani worktree.
- Další testy pokrývají zastaralý řádek `running`, závislosti s `--force`, číslování větví, task bez `writes` a task, který není v `base`.

Žádný test nevolá model, všechny používají falešný harness.

Ručně:

```sh
haifa-proto task run M01-S01-T01 --note "…"
haifa-proto task show M01-S01-T01 --json
```
