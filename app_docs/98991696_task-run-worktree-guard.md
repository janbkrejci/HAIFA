# `factory task run`: běh úkolu ve vlastním worktree s hlídáním zápisů

Tahle změna přidává příkaz `factory task run <task-id> [--note TEXT] [--force]`. Příkaz spustí jeden úkol z backlogu v novém git worktree a na nové větvi. Po každém volání agenta zkontroluje hlavní checkout i worktree a vrátí všechno, co agent změnit neměl. Pokrývá kroky 1 až 3 sekce „Běh úkolu“ v `docs/product-brief.md`. Push a PR (2.12) a auto-continue (2.15) do rozsahu nepatří. Plán práce je v `specs/98991696_task-run-worktree-guard.md`.

## Co běh dělá

1. **Kontrola před startem** (`run/task.py`, `run_task`). Backlog se čte z commitu `base` (`gitops.extract_backlog` → `git archive` do dočasného adresáře). Konfigurace se bere z `load_run_config`, tedy také z `base`. Úkol, který je jen v pracovním stromu, skončí chybou `task_not_in_base`. Dále se kontroluje, že úkol ještě neběží, že má splněné `depends_on` (`--force` přeskočí jen tuto kontrolu), že má neprázdné `writes` (vlastní nebo zděděné) a že jeho workflow jde najít. Workflow se hledá nejdřív v `.factory/workflows/` v `base`, pak mezi zabalenými workflow, a musí projít `preflight`. Když některá kontrola selže, vyhodí se `TaskRunError(code, message)` a nevznikne nic. CLI pak skončí s kódem 2.
2. **Worktree a větev.** Worktree vznikne v `<worktrees_dir>/<run-id>`, výchozí je `.factory/worktrees/<run-id>`. Větev `factory/<task-id>-<n>` dostane `n` o jedna vyšší než jakákoli existující větev nebo zaznamenaný běh (`gitops.next_branch`). Worktrees, session runtime a trace DB se zapíšou do `info/exclude` sdíleného `.git`.
3. **Workflow ve worktree.** Proces udělá `chdir` do worktree a `run_workflow` dostane `repo_root=worktree`, `write_guard`, `prompt_variables` (`task_id`, `spec_path`, `doc_path`, `workdir`) a `label=task_id`. Náhradní commit message má tvar `<task-id>: <summary>` místo `sssf(<run-id>): …`. Session runtime leží v `.factory/data/sessions/<run-id>` v hlavním checkoutu (pokud `agents.yaml` nenastaví jiný `data_dir`).

Prompt úkolu (`task_prompt`) obsahuje hlavičku (id, title, nadřazené kontejnery, source/target), absolutní cestu k worktree, povolené cesty, cestu ke spec a dokumentaci, text úkolu a nakonec `## Note` s obsahem `--note`. Jediná absolutní cesta v promptu je worktree.

## Výstupy pojmenované podle úkolu (`run/scope.py`)

- spec: `<specs_dir>/<task-id>-<slug>.md`
- dokumentace: `<docs_dir>/<task-id>-<slug>.md`

`slug` je název souboru úkolu bez prefixu `<task-id>-`. Když ho nejde odvodit, vezme se `slugify(title)`. Rozsah úkolu (`TaskScope`) tvoří `effective_writes(task)` a přesně tyto dva soubory. Ve worktree musí zápis povolit agent (`permissions.permitted`) **a zároveň** rozsah úkolu, tedy jde o průnik obou. `permissions.always_writable` zůstává zapisovatelné i nadále. Soubor jako `specs/<run-id>_plan.md` se tedy vrátí a fáze selže.

## Hlídání zápisů (`run/guard.py`, `TaskWriteGuard`)

Engine zavolá `snapshot` před fází agenta a `enforce` po ní:

- **Worktree:** každá změněná cesta mimo agenta nebo rozsah úkolu se vrátí (`roll_back`: smazání, `checkout HEAD` nebo `rm --cached`). Commit, který agent udělal sám, se zruší přes `git reset --soft` na HEAD před fází a jeho soubory se pak kontrolují jako jakákoli jiná změna.
- **Hlavní checkout:** vrátí se každá nová změna kromě worktrees, session runtime a trace DB. Posunutý HEAD nebo přepnutá větev se jen nahlásí, nevrací se.
- Změny, které existovaly už před fází, zůstanou beze změny.
- Při porušení se vyhodí `PermissionBreach` a zpráva jmenuje každý soubor ve tvaru `worktree: <path> — …` nebo `main checkout: <path> — …`.
- Známé omezení: git nevidí soubory ignorované přes `.gitignore`, takže zápis do nich guard nezachytí.

## Úpravy v enginu (označené `# aifactory 2.9:`)

- `engine/runner.py`: `Run` má nová pole `write_guard` (výchozí `None`, pak se použije modul `permissions`) a `prompt_variables`.
- `engine/agents.py`: proměnné běhu se vykreslí do promptu, při kolizi vyhrají proměnné enginu. Guard nahrazuje `permissions`. Odeslání, parsování a gates jsou vyčleněné do `_send_and_check`. Když fáze selže (harness, JSON, gate), `_enforce_after_failure` přesto zkontroluje a vrátí zápisy. Nalezené porušení nahradí původní chybu a je na ni zřetězené.
- `engine/gates.py`: `artifacts_exist` přijme artefakt jen uvnitř `repo_root` (worktree) nebo `session_dir`. Relativní cesta se vyhodnotí od `repo_root`, ne od cwd.
- `workflow/interpreter.py`: `run_workflow` přijímá `repo_root`, `write_guard`, `prompt_variables` a `label`.
- `pyproject.toml`: komentáře teď říkají, že engine už není bajtově shodný se sssf a že změny jsou v kódu označené.

## Záznam běhů (`run/store.py`)

Tabulka `task_runs` je v trace DB. Obsahuje `run_id`, `task_id`, `branch`, `worktree`, `base`, `base_sha`, `head_sha`, `state` (`running|succeeded|failed|aborted`), časy, `pid`, `workflow`, `note` a `error`.

- `claim` zapisuje v `BEGIN IMMEDIATE`, takže druhý start běžícího úkolu skončí chybou `already_running`, i když ho `--force` požaduje.
- Řádek `running`, jehož proces už neexistuje, se přepne na `aborted`.
- Store před otevřením Traceru přepne DB do WAL, s opakovanými pokusy.

Běh skončí jako `succeeded` jen tehdy, když workflow projde (`accepted` a `exit_code == 0`). Jinak skončí jako `failed` a chyba se uloží. Worktree i větev zůstanou.

## CLI (`cli.py`)

- `factory task run ID [--note TEXT] [--force] [--json] [--repo PATH]`
  - Textový výstup: `run <id> <state>: branch …, worktree …`.
  - S `--json` se výpis enginu přesměruje na stderr a stdout obsahuje jen `{"ok", "run", "warnings"}`.
  - Návratové kódy: 0 znamená úspěch, 1 znamená, že běh začal a selhal, 2 je `TaskRunError`.
- `factory task show ID` teď vypisuje sekci `runs:` (nebo `no runs`) a v JSON klíč `runs`. Když trace DB neexistuje, nic nevytvoří.

## Ověření

Testy nevolají model. Používají falešné harnessy (`install_fake_harnesses` v `tests/workflow/workflow_fakes.py`) a repozitář z `tests/run/run_repo.py`.

- `tests/run/test_task_run.py` ověřuje:
  - vznik worktree, větve a řádku v DB a číslování `-1`, `-2`;
  - výstupy pojmenované podle úkolu a `run-id` nikde v promptu kromě cest;
  - zápis do hlavního checkoutu (pro claude, codex i pi), který se vrátí a fáze selže;
  - zápis mimo `writes` a commit agenta mimo `writes`;
  - vrácení zápisu i ve chvíli, kdy selže gate;
  - odmítnutí artefaktu z hlavního checkoutu;
  - prázdný commit, který projde (`committed is False`);
  - druhý start, který skončí `already_running`;
  - mrtvý běh, který se změní na `aborted`;
  - cesty v promptu jen uvnitř worktree nebo session;
  - kontroly před startem;
  - `--force`;
  - konfiguraci z `base`.
- `tests/run/test_task_run_cli.py` ověřuje JSON a textový výstup, kód 1 při selhání, `task show` s během i bez běhu a kód 2 při neznámém úkolu.
- `tests/engine/test_task_run_hooks.py` ověřuje umístění artefaktů, vrácení zápisů při selhaném gate, `write_guard` místo `permissions` a vykreslení `prompt_variables`.

Spuštění: `just test`, `just typecheck`, `just lint`.
