Implementuj `factory task run <task-id> [--note TEXT] [--force]` podle kroků 1 až 3 v sekci „Běh úkolu“ v `docs/product-brief.md` a zajisti, že agent nezmění nic mimo worktree svého běhu a mimo povolené cesty.

Where: `aifactory/src/aifactory/run/`, CLI, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/run.py`, `scope.py`.

Done means:
- Kontrola před startem, worktree `.factory/worktrees/<run-id>`, větev `factory/<task-id>-<n>`, tabulka `task_runs` a `task show` jako v prototypu. Konfigurace běhu z commitu v `base` (2.4).
- Agent běží s cwd ve worktree a v promptu dostává jen cesty uvnitř worktree nebo session adresáře. Žádná cesta v promptu nevede do hlavního checkoutu mimo session adresář.
- Po každém volání agenta kód zkontroluje hlavní checkout i worktree. Změna v hlavním checkoutu nebo změna ve worktree mimo `writes` tasku a agenta se vrátí a fáze selže s chybou, která soubor jmenuje. Platí stejně pro claude, codex i pi.
- Gate `artifacts_exist` přijme jen artefakt uvnitř worktree nebo session adresáře běhu.
- Krok commit, který nemá co commitnout, běh neshodí.
- Výstupy agentů se jmenují podle tasku, aby člověk poznal, k čemu patří: spec `specs/<task-id>-<slug>.md`, dokumentace `app_docs/<task-id>-<slug>.md` (adresáře podle `.factory/config.yaml`). `run-id` zůstává jen v trace.
- Testy s falešným harnessem: zápis do hlavního checkoutu se vrátí a fáze selže, zápis mimo `writes` se vrátí a fáze selže, prázdný commit projde, výstupy mají název podle tasku, druhé spuštění běžícího tasku skončí chybou.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: push a PR (2.12), auto-continue (2.15).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
