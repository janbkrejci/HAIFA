Odstraň z produktu vlastníka modulu, tedy pole `owner` v `index.md` modulu a stepu, a všechna místa, kde se zobrazuje nebo podle něj filtruje. Rozhodnutí engineera z 2026-10-01: institut vlastníka se nepoužívá.

Where: `aifactory/src/aifactory/backlog/model.py`, `aifactory/src/aifactory/web/backlog.py`, `aifactory/src/aifactory/web/review.py`, `aifactory/src/aifactory/skill/skill.md`, frontend `aifactory/web/src/` (`components/backlog/BacklogFilters.vue`, `KanbanBoard.vue`, `TreeNode.vue`, `TaskDetail.vue`, `views/BacklogView.vue`, `components/review/ReviewList.vue`, `ReviewDetail.vue`, `views/ReviewView.vue`, `lib/backlog.ts`, `lib/review.ts`, testovací fixtures), testy v `aifactory/tests/`.

Done means:
- `owner` není mezi poli, která tasky dědí z `index.md`. API backlogu ani Review nevrací `owner`, `owners`, `me` ani `filters.owner` a parametr `?owner=` se nepoužívá.
- Existující `index.md` nebo task s polem `owner` zůstane platný: `factory backlog check` ho neodmítne a pole se ignoruje. Hlídá to test.
- Obrazovka Review nemá výběr „Vlastník“, tlačítko „Jen moje moduly“, hlášku o párování z git config ani sloupec „Vlastník“. Párování podle git config (`user.email`, `user.name`, `$USER`) je odstraněné. Sekce „Čeká na mé review“ se jmenuje „Čeká na review“, protože nikdy nebyla vázaná na osobu.
- Obrazovka Backlog nemá filtr „Vlastník“ a strom, kanban ani detail tasku vlastníka neukazují.
- Volba vlastníka uložená v prohlížeči (`factory.review.owner` v localStorage) se už nečte ani nezapisuje.
- `factory --skill` vlastníka nezmiňuje.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: filtr nebo přepínání podle modulu, změna `docs/product-brief.md`.

Pevná omezení:
- `owner` ve významu vlastníka fáze v enginu a trace zůstává beze změny: sloupec `phases.owner`, `roles.yaml`, kód `missing_owner` v `engine/role_registry.py`, `review/prbody.py`, `web/runs.py` a `lib/runs.ts`. Beze změny zůstává i `owner/name` GitHub repa ve validaci.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
