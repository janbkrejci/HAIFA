Doplň na konec běhu tasku pull request a jeho schválení podle kroků 4 až 7 v sekci „Běh úkolu“ a rozhodnutí D6, D8, D9 a D11 v `docs/product-brief.md`. Rozhraní `GitProvider` bude mít implementace `local` a `github`.

Where: `prototype/src/haifa_proto/providers/` (`base.py`, `local.py`, `github.py`), `prototype/src/haifa_proto/run.py`, CLI, testy v `prototype/tests/`.

Done means:
- `GitProvider`: vytvořit PR, stav PR (otevřený, mergnutelný, konflikt, mergnutý, zavřený), approve review, merge se strategií (`squash` výchozí, `merge`), komentář. Provider a strategie jsou v `.factory/config.yaml`.
- Po splnění `accept` běh pushne větev a vytvoří PR. Popis PR obsahuje zadání tasku, shrnutí agentů, výsledky gates a testů, verdikt revieweru a náklady z trace.
- `haifa-proto task approve <task-id>`: jeden commit do PR větve (`status: done` v hlavičce tasku a záznam do sekce `## Běhy`: datum, workflow, odkaz na PR, náklady), potom merge. Approve review jménem přihlášeného uživatele se posílá jen při `require_review: true` v `.factory/config.yaml` (výchozí `false`: GitHub nedovolí autorovi schválit vlastní PR a sandbox branch protection nemá). Když hosting approve review odmítne, příkaz to ohlásí a nic nemerguje.
- `haifa-proto task return <task-id> --note TEXT`: nový běh na téže větvi s poznámkou v promptu, PR se aktualizuje, stav tasku se nemění.
- `haifa-proto backlog sync`: najde PR mergnuté mimo HAIFA bez `status: done` v `base` a doplní ho jedním commitem do `base`.
- Po merge se worktree smaže.
- Provider `local`: PR je větev, schválení je lokální merge do `base`. Test end-to-end s lokálním bare repem jako remote: po approve je v `base` `status: done` i kód, vrácený PR stav nezmění, `backlog sync` doplní `done` po ručním merge.
- Provider `github`: volání `gh` jsou za jedním rozhraním. Testy nahradí `gh` falešným spustitelným souborem a ověří argv každé operace.

Out of scope: Azure DevOps (přijde ve F2), auto-continue, web.

Pevná omezení:
- `done` přichází jen commitem do PR při schválení, nikdy dřív.
- Testy nevolají model ani skutečný GitHub.
- `vendor/` se neupravuje.
