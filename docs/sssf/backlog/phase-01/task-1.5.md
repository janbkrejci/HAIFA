Implementuj `haifa-proto task run <task-id> [--note TEXT] [--force]`: spuštění tasku z backlogu ve vlastním git worktree a větvi podle kroků 1 až 3 v sekci „Běh úkolu“ v `docs/product-brief.md`.

Where: `prototype/src/haifa_proto/run.py`, `prototype/src/haifa_proto/scope.py`, CLI, testy v `prototype/tests/`.

Done means:
- Před startem kontrola: task existuje, není právě spuštěný a všechny jeho `depends_on` jsou hotové v `base`. `--force` kontrolu závislostí přeskočí, běžící task nikdy.
- Běh vytvoří worktree `.factory/worktrees/<run-id>` a větev `factory/<task-id>-<n>` z `base` (`base` a `worktrees_dir` v `.factory/config.yaml`, výchozí `main` a `.factory/worktrees`).
- Workflow tasku (z 1.4) běží s cwd ve worktree. Session runtime a trace DB zůstávají v hlavním checkoutu, sdílené všemi běhy.
- Agent smí měnit jen `writes` tasku (zděděné z `index.md` podle 1.2), navíc k omezení samotného agenta. Zápis mimo rozsah se vrátí a fáze selže. Rozšíření `permissions.py` je v `prototype/`, ne ve `vendor/`.
- Prompt agentů začíná hlavičkou tasku: id, titulek, modul a step, `source`, `target`, povolené cesty. Za ní text tasku a poznámka `--note`, pokud je.
- Vazba běh → task je v trace DB (vlastní tabulka `task_runs`: run-id, task-id, větev, worktree, base sha, head sha, stav, začátek, konec). `haifa-proto task show <task-id> [--json]` vypíše běhy tasku.
- Integrační test v dočasném git repu s falešným harnessem: běh vytvoří větev a worktree, commit je jen na větvi, hlavní checkout zůstane beze změny, `task_runs` má řádek. Druhý test: zápis mimo `writes` se vrátí a běh selže. Třetí test: druhé spuštění běžícího tasku skončí chybou.

Out of scope: push a PR (1.6), auto-continue (1.7), web.

Pevná omezení:
- Stav `done` se v tomto úkolu do souboru tasku nezapisuje. Přijde až se schválením v 1.6.
- `vendor/` se neupravuje.
- Testy nevolají model.
