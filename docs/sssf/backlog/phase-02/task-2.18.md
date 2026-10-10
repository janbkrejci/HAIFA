Přidej akceptační scénář F2 do validace: na ukázkovém repu projde z CLI 5 úkolů, z toho 2 paralelně, od `factory task run` po mergnutý PR a stav `done` v `base`.

Where: `aifactory/validation/`, `aifactory/tests/`.

Done means:
- Scénář `F2` založí ukázkový backlog (2 moduly, 5 tasků s vazbami), spustí je přes `factory task run` a `--auto`, dva z nich současně, a všechny schválí přes `factory task approve`.
- Kontroly: 5 mergnutých PR, `status: done` u všech 5 tasků v `base`, žádný zápis mimo worktree, žádný zbylý worktree, `backlog check` projde.
- `just validate --remote local` projde se scénářem `F2` bez `failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: běh proti GitHubu (spustí engineer).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
