---
id: HAIFA-S01-T47
title: "Kanban: archivovat hotové, přepínač Zobrazit archivované v Hotovo a Zrušeno"
status: done
archived: true
workflow: plan-build-test
depends_on: [HAIFA-S01-T46]
writes: [aifactory/web/src/lib/backlog.ts, aifactory/web/src/lib/backlog.test.ts, aifactory/web/src/components/backlog/KanbanBoard.vue, aifactory/web/src/components/backlog/KanbanBoard.test.ts, aifactory/web/src/views/BacklogView.vue, aifactory/web/src/views/BacklogView.test.ts, aifactory/src/aifactory/guide/04-backlog.md, aifactory/src/aifactory/web/static/]
---

## Zadání
Kanban na obrazovce Backlog podle příznaku `archived` z T46 schovává archivované tasky ve sloupcích Hotovo a Zrušeno. Zrušené se archivují rovnou. Hotové archivuje člověk ručně, až si je přečte.

Co udělat:
- `aifactory/web/src/lib/backlog.ts`: do `TaskNode` přidej pole `archived?: boolean`. Přidej funkci `setArchived(taskId, archived)`, která volá `POST <taskPath>/archive`, podle vzoru `setAutoExcluded`. Přidej také stav přepínače „Zobrazit archivované“ zvlášť pro sloupec Hotovo a zvlášť pro Zrušeno. Prohlížeč si ho pamatuje v localStorage stejně jako „Skrýt hotové“. Výchozí stav je vypnuto.
- `aifactory/web/src/components/backlog/KanbanBoard.vue`: v záhlaví sloupců `done` a `cancelled` je malý přepínač (ikona s Tooltipem) „Zobrazit archivované (N)“. Při vypnutém přepínači sloupec archivované karty nezobrazuje. Počet ve sloupci ukazuje viditelné karty a počet archivovaných je vidět u přepínače. Při zapnutém přepínači jsou archivované karty ztlumené. Karta hotového tasku, který ještě není archivovaný, má v `tools` tlačítko „Archivovat“ (vzal jsem na vědomí). Archivovaná hotová karta má tlačítko „Obnovit“. Obě tlačítka vyšlou event `archive: [id, archived]` a během `busy` čekají. Zrušené karty tlačítko nemají, protože jsou archivované vždy.
- `aifactory/web/src/views/BacklogView.vue`: event `archive` obsluž voláním `setArchived` a znovunačtením backlogu, stejně jako `exclude`. Chyba se ukáže stejně jako u ostatních zápisů fronty. Přepínač „Skrýt hotové“ dál funguje jako dosud.
- Testy: `aifactory/web/src/components/backlog/KanbanBoard.test.ts` (skrytí archivovaných, přepínač po sloupcích, tlačítka Archivovat a Obnovit a jejich event), `aifactory/web/src/views/BacklogView.test.ts` (volání API a znovunačtení) a `aifactory/web/src/lib/backlog.test.ts` (paměť přepínače). Před dokončením projdi grepem testy na změněné selektory a texty.
- Příručka `aifactory/src/aifactory/guide/04-backlog.md`: v sekci Strom a kanban jednou větou popiš archivaci (zrušené rovnou, hotové tlačítkem Archivovat, přepínač v záhlaví sloupce, necommituje se). Dosavadní Python testy příručky musí dál projít beze změny.
- Statický build přegeneruj přes `just web-build` do `aifactory/src/aifactory/web/static/`.

Mimo rozsah: strom, graf a detail tasku. Ve stromu se nic nemění.

Hotovo znamená:
- V kanbanu nejsou bez zapnutého přepínače vidět zrušené tasky ani archivované hotové tasky. Přepínač v záhlaví Hotovo nebo Zrušeno je ukáže ztlumené a jeho stav přežije obnovení stránky.
- Tlačítko Archivovat na hotové kartě kartu schová (přes API z T46) a Obnovit ji vrátí.
- Webové testy projdou včetně nových testů v `KanbanBoard.test.ts`, `BacklogView.test.ts` a `backlog.test.ts`. Projdou i dosavadní testy souladu příručky s UI.
- `aifactory/src/aifactory/web/static/` obsahuje přegenerovaný build.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-24 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/154 · náklady $0.00
