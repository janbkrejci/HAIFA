Implementuj tok PR podle kroků 4, 5 a 7 v sekci „Běh úkolu“ v `docs/product-brief.md`: vytvoření PR na konci běhu, `factory task approve`, `factory task return` a úklid worktree. Schválení zatím approve review v hostingu neposílá a rovnou merguje.

Where: `aifactory/src/aifactory/review/`, `run/`, CLI, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/review.py`, `prbody.py`.

Done means:
- Po splnění `accept` push a PR s popisem: zadání, shrnutí agentů, výsledky gates a testů, verdikt revieweru, náklady. Vazba v tabulce `task_prs`.
- `task approve <task-id>` přidá do PR commit se `status: done` a záznamem do sekce Běhy a merguje. Approve review se neposílá: v kódu i v nápovědě je to označené jako dočasné (D11, k dodělání).
- `task return <task-id> --note TEXT` spustí nový běh na téže větvi s poznámkou v promptu a PR se aktualizuje.
- Zavřený PR se v `task_prs` zapíše jako `closed`. Approve zavřeného PR vrátí `pr_not_open`.
- Po merge core dotáhne `base` z remote (fetch a fast-forward), aby další běh začal z aktuální base.
- Worktree se smaže po merge. `factory task clean [--json]` smaže worktree zavřených a opuštěných běhů.
- Testy s providerem `local`: approve, return, zavřený PR, dotažení base, úklid.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: `backlog sync` (2.13), `resolve` (2.14), approve review jménem uživatele.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
