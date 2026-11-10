---
id: HAIFA-REFINEMENT-T111
title: Zabránit přetékání seznamu běhů s mnoha fázemi
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T110]
writes: [aifactory/web/src/components/runs/RunsList.vue, aifactory/web/src/components/runs/RunsList.test.ts, aifactory/web/src/components/runs/PhaseDots.vue, aifactory/web/src/components/runs/PhaseDots.test.ts, aifactory/tests/e2e/test_runs_overflow_browser.py, aifactory/src/aifactory/web/static/, aifactory/web/src/App.vue]
---

## Zadání
Opravit seznam běhů v aifactory/web/src/components/runs/RunsList.vue a vykreslení fází v PhaseDots.vue. PhaseDots nyní používá inline-flex bez zalamování a tabulka nemá omezení, které by zabránilo roztažení stránky při velkém počtu fází. Dlouhý běh nesmí zvětšit šířku celé stránky za viewport. Zvolit omezenou šířku sloupce a zalamování ikon; pokud se tabulka na úzkém viewportu celá nevejde, umožnit horizontální posun pouze uvnitř seznamu. Všechny fáze musí zůstat dostupné s tooltipy a ovládáním klávesnicí, zachovat kliknutí na řádek, odkazy a akce archivace či mazání. Neřešit přetékání pouhým oříznutím obsahu nebo globálním overflow-x:hidden.

Doplnit relevantní komponentové testy RunsList.test.ts a PhaseDots.test.ts. Skutečnou geometrii ověřit novým browser testem aifactory/tests/e2e/test_runs_overflow_browser.py se syntetickými daty bez živých modelů a služeb: alespoň 100 fází, dlouhý název tasku a běžný i úzký viewport. Před implementací dohledat přímé použití PhaseDots a související testy v celém repozitáři.

Hotovo znamená:
- Seznam se 100 fázemi nevytvoří horizontální overflow dokumentu při běžné ani úzké šířce okna.
- Všechny fáze jsou dostupné; jejich počet a pořadí odpovídají vstupu a tooltipy i akce řádku zůstávají funkční.
- Browser test měří šířku dokumentu vůči viewportu a případný scroll zůstává uvnitř seznamu.
- Projdou just lint, just typecheck, just web-test a just pytest tests/e2e/test_runs_overflow_browser.py -n0; spustí se každý další editovaný testovací soubor.
- Proběhne just web-build a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
