Oprav dvě chyby, které ukázala validace proti GitHubu s rosterem `claude-haiku` (běh `github-180539`):

1. Agent sám commituje ve worktree. Builder na claude haiku po své práci spustil `git commit`, hlídač zápisů commit vrátil a fáze selhala (`builder changed paths outside its task run: worktree: HEAD — agent committed`). Stalo se to v R2, R3, R4, R10 a F2. Commity dělá kód workflow, agent nikdy.
2. `factory backlog sync` pushuje větev `factory-sync/<n>`, která už na remote existuje z dřívějších běhů, a push skončí `non-fast-forward` (R3, `push_failed`).

Where: prompty agentů v `aifactory/` (výchozí konfigurace i `aifactory/validation/template/.factory/prompts/`), `aifactory/src/aifactory/backlog/` nebo `review/` (sync), `aifactory/tests/`.

Done means:
- Prompty všech agentů, kteří mění soubory (builder, fix, revise, resolve, documenter, planner), výslovně říkají: necommituj, nepushuj a neměň git větve, commit udělá workflow. Test ověří, že to říká každý takový prompt.
- Hlídač zápisů se nemění: commit agenta dál vrátí a fázi shodí.
- `backlog sync` zvolí název větve, který neexistuje lokálně ani na remote. Test proti falešnému remote, kde `factory-sync/1` už existuje: sync použije jiný název a push projde.
- `just validate --remote local` projde bez `failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna hlídače zápisů, změna modelů v rosterech.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.
