---
id: HAIFA-S01-T48
title: Zachovat vertikální scrollování stránky nad širokým kanbanem
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/components/backlog/KanbanBoard.vue, aifactory/web/src/components/backlog/KanbanBoard.test.ts, aifactory/web/src/views/BacklogView.vue, aifactory/tests/e2e/test_kanban_scroll_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Opravit situaci, kdy vodorovně přetékající kanban na obrazovce Backlog brání vertikálnímu posunu stránky kolečkem při kurzoru nad kanbanem. Kanban má růst podle obsahu a nemá mít vlastní omezenou výšku ani vertikálně scrollované sloupce.

Výchozí místo je aifactory/web/src/components/backlog/KanbanBoard.vue: .board používá overflow-x: auto, explicitní wheel handler zde není. Reprodukci a skutečnou příčinu ověřit před volbou opravy; nepředpokládat zachytávání událostí JavaScriptem. Prověřit také rodičovské rozložení v aifactory/web/src/views/BacklogView.vue a upravit je pouze tehdy, pokud se podílí na problému. Zachovat vodorovný posun kanbanu scrollbarem a horizontálním gestem, ovládání karet i drag and drop. Neměnit scrollování ostatních obrazovek ani přesměrovávat běžné vertikální kolečko na vodorovný posun.

Přidat aifactory/tests/e2e/test_kanban_scroll_browser.py podle existujících browser testů a helperů v aifactory/tests/e2e/f3_repo.py. Připravit deterministická lokální data pro kanban širší než dostupný prostor a stránku vyšší než viewport. Použít skutečné page.mouse.wheel nad viditelnou kartou i volným místem sloupce a měřit posun stránky; samotné dispatchEvent nebo kontrola CSS nestačí. Ověřit posun dolů i nahoru při vodorovném umístění kanbanu na začátku, uprostřed a na konci. Ověřit také horizontální posun a případ bez horizontálního přetečení. Neměnit sdílené testovací helpery. Pokud oprava přidá logiku do komponenty, pokrýt ji také v KanbanBoard.test.ts.

Před dokončením dohledat přímé volající změněných částí a související testy v celém aifactory/tests/. Spustit just lint, just typecheck, just web-test, just web-build a just pytest tests/e2e/test_kanban_scroll_browser.py -n0; případné další testy vybírat pouze podle dotčeného chování. Přegenerovaný distribuovaný frontend zahrnout do změny. Celou Python ani e2e sadu nespouštět.

Hotovo znamená:
- Při horizontálním přetečení kanbanu kolečko nad kartou i sloupcem posouvá stránku vertikálně oběma směry bez nutnosti přesunout kurzor mimo kanban.
- Chování funguje na začátku, uprostřed i na konci vodorovného rozsahu a také bez horizontálního přetečení.
- Vodorovné ovládání kanbanu zůstává funkční a kanban ani jeho sloupce nezískají omezenou výšku či vlastní vertikální scrollování.
- Nový browser test ověřuje skutečné posuny a prochází; všechny upravené testovací soubory byly spuštěny a uvedené kontroly prošly.
- Distribuovaný statický frontend odpovídá opravenému zdrojovému kódu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
