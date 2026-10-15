---
id: HAIFA-REFINEMENT-T41
title: "Stav „Čeká na review“ je někdy zavádějící: rozlišit čekání na review a na automerge PR"
status: done
workflow: simple-sdlc
depends_on: []
related: [HAIFA-REFINEMENT-T33, HAIFA-REFINEMENT-T37, HAIFA-REFINEMENT-T28, HAIFA-REFINEMENT-T39]
writes: [aifactory/src/aifactory/, aifactory/web/src/, aifactory/tests/]
---

## Zadání
Když má task zapnutý automerge, nečeká na review, ale na mergnutí PR. Dashboard ho přesto ukazuje jako „Čeká na review“. Tyto dva stavy se mají rozlišit na Přehledu a všude jinde:

- **Čeká na review**: PR tasku je otevřené a automerge pro task vypnutý (efektivní hodnota `auto_merge` včetně dědičnosti z projektu/stepu). Je potřeba zásah uživatele.
- **Čeká na automerge PR**: PR tasku je otevřené a automerge je zapnutý. Factory ho mergne sama, uživatel nemusí nic dělat.

## Kde rozlišit
- Přehled: souhrnná tlačítka/filtry, sekce na kartě repa (RepoCard) a pořadí podle naléhavosti. Repo, které jen čeká na automerge, nemá být řazené ani počítané jako čekající na uživatele.
- Přepínač rep (počty u rep).
- Stránka Review (skupiny v ReviewList).
- Backlog/strom/kanban a detail tasku (stav „v review“ a jeho chip/legenda).
- Návod dashboardu (guide 04-dashboard.md, 07-review.md).

## Akceptační kritéria
- Backend v API přehledu, review a backlogu u tasku s otevřeným PR rozliší, zda čeká na review uživatele, nebo na automerge. Počty v souhrnu jsou oddělené.
- UI na všech výše uvedených místech ukazuje text „Čeká na review“, resp. „Čeká na automerge PR“ (stejné formulace všude).
- Filtr/počet „Čeká na review“ nezahrnuje tasky čekající na automerge.
- Stávající testy jsou upravené a nové pokrývají oba případy (automerge zapnutý/vypnutý) v backendu i frontendu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/54 · náklady $6.50
