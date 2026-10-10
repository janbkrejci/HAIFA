Implementuj `factory backlog sync [--json]`: doplní `status: done` pro tasky, jejichž PR byl mergnut mimo HAIFA, a zapíše ho přes PR, ne přímo do `base`.

Where: `aifactory/src/aifactory/backlog/`, `review/`, CLI, `aifactory/tests/`.

Done means:
- Sync najde mergnuté PR tasků, které v `base` nemají `done`, a otevře jeden PR se změnou hlaviček a záznamy do sekce Běhy. Když není co měnit, PR nevytvoří.
- Sync aktualizuje `task_prs.state` (`merged`, `closed`). Zavřené PR stav tasku nemění.
- Výstup vrátí odkaz na PR sync a seznam tasků.
- Testy s providerem `local`: merge mimo HAIFA, sync otevře PR, po jeho merge je `done` v `base`. Druhý sync nic neotevře.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: automatický merge PR sync.

Pevná omezení:
- Sync nikdy necommituje přímo do `base`.
- `vendor/` a `prototype/` se nemění.
