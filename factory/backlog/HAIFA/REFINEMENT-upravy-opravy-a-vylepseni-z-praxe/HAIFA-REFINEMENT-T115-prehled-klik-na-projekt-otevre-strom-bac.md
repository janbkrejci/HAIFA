---
id: HAIFA-REFINEMENT-T115
title: "Přehled: klik na projekt otevře strom backlogu filtrovaný na projekt s rozbalenou první úrovní"
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T114]
writes: [aifactory/web/src/components/overview/RepoWork.vue, aifactory/web/src/components/overview/RepoCard.test.ts, aifactory/web/src/views/OverviewView.test.ts, aifactory/web/src/lib/router.ts, aifactory/web/src/lib/router.test.ts, aifactory/web/src/views/BacklogView.vue, aifactory/web/src/views/BacklogView.test.ts, aifactory/tests/e2e/test_multi_repo_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Na Přehledu v kartě repa s dlaždicemi po projektech (`aifactory/web/src/components/overview/RepoWork.vue`, nadpis `h3.project-name` v sekci `data-test="project-section"`) udělat z kódu a názvu projektu odkaz. Klik otevře Backlog tohoto repa v režimu Strom s filtrem na tento projekt (filtr z HAIFA-REFINEMENT-T114, uložený pro repo) a s rozbaleným kontejnerem projektu, takže jsou vidět jeho stepy (první úroveň pod projektem). Ostatní rozbalení stromu se nemění.

Návrh řešení: v `lib/router.ts` přidat konstantu a funkci pro odkaz (např. `#/r/<repo>/backlog/project/<id>`, `projectBacklogHref(repoId, projectId)`) po vzoru `GRAPH`/`graphHref`. `BacklogView.vue` při této cestě nastaví a uloží filtr projektu (`setBacklogProject`), přepne režim na Strom, rozbalí projekt přes `expandKeys([nodeKey(...)])` z `lib/backlog.ts` a nahradí adresu běžným `…/backlog` (bez nového záznamu v historii), aby reload nebo další navigace nefiltrovaly znovu napevno. Projekt, který v backlogu neexistuje, otevře strom bez filtru. Odkaz musí být přístupný z klávesnice a nesmí rozbít rozložení karty ani chipy souhrnu stavů.

Před změnou dohledat přímé volající `RepoWork`, `parseRoute`/`repoHref` a selektorů `project-section`/`project-name` ve webových testech (`RepoCard.test.ts`, `OverviewView.test.ts`, `lib/router.test.ts`) i v `aifactory/tests/` a upravit jejich očekávání.

Mimo rozsah: samotný filtr projektu a jeho ukládání (HAIFA-REFINEMENT-T114), změny API přehledu.

Hotovo znamená:
- Nadpis projektu v dlaždici po projektech je odkaz na Backlog repa pro tento projekt (test v `RepoCard.test.ts`).
- `lib/router.test.ts` ověří tvar odkazu a jeho rozpoznání.
- Test v `BacklogView.test.ts`: otevření odkazu nastaví filtr na projekt, režim Strom, uloží filtr pro repo, rozbalí projekt (vidět jsou jeho stepy) a adresa se změní na `…/backlog`. Neznámý projekt otevře nefiltrovaný strom.
- Browser test v `tests/e2e/test_multi_repo_browser.py`: klik na projekt na Přehledu otevře strom jen s tímto projektem a jeho rozbalenými stepy a přepnutí na Kanban zachová filtr.
- Projdou `just lint`, `just typecheck`, `just web-test`, všechny editované testovací soubory a `just pytest tests/e2e/test_multi_repo_browser.py -n0`.
- Proběhne `just web-build` a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
