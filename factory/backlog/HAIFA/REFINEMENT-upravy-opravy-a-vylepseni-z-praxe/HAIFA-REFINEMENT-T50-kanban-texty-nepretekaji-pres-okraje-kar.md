---
id: HAIFA-REFINEMENT-T50
title: "Kanban: texty nepřetékají přes okraje karet"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/components/backlog/KanbanBoard.vue, aifactory/web/src/components/backlog/KanbanBoard.test.ts, aifactory/src/aifactory/web/static/, aifactory/tests/e2e/test_f3_browser.py]
---

## Zadání
## Zadání
Na kanbanu stránky Backlog (`aifactory/web/src/components/backlog/KanbanBoard.vue`) přetékají texty přes okraj karty. Dlouhý název tasku nebo slovo bez mezer, dlouhé ID (např. `HAIFA-REFINEMENT-T49`) a název workflow vylezou z karty i ze sloupce, nebo sloupec roztáhnou.

## Příčina (k ověření)
- Mřížka `.board` má sloupce `minmax(170px, 1fr)`. Grid itemy (`.column`) mají výchozí `min-width: auto`, takže je dlouhý obsah roztáhne.
- `.card` je flex sloupec a jeho potomci (`.id`, `.title`, `.meta`) nemají `min-width: 0` ani pravidla pro zalamování (`overflow-wrap`).

## Co udělat
- Ve scoped stylech `KanbanBoard.vue` zajistit, že sloupec ani karta nejsou širší než jejich buňka mřížky (`min-width: 0` na `.column`, `.item` a `.card`).
- Název tasku (`.title`) se zalamuje i uvnitř dlouhých slov bez mezer (`overflow-wrap: anywhere`, případně `word-break`).
- ID tasku (`.id`, včetně pořadí `.rank`) a workflow v `.meta` nepřetečou: buď se zalomí, nebo se zkrátí výpustkou (`text-overflow: ellipsis`) a plná hodnota je vidět v atributu `title`.
- Štítky `neplatný status` a `přednostně` a řádek nástrojů `.tools` zůstávají uvnitř karty.
- Vodorovný scroll celé mřížky (`overflow-x: auto` na `.board`) při mnoha sloupcích zůstává. Karty se nesmí rozšiřovat nad šířku sloupce.
- Přegenerovat statický build dashboardu (`just web-build`) do `aifactory/src/aifactory/web/static/`. Statický build se commituje.

## Mimo rozsah
- Jiné obrazovky a komponenty (strom backlogu, detail tasku, Přehled).
- Změny chování drag and drop, fronty a API.

## Hotovo znamená:
- Na kanbanu nepřeteče přes okraj karty ani sloupce dlouhý název bez mezer (např. 120 znaků `a`), dlouhé ID ani dlouhý název workflow. Sloupec se kvůli nim nerozšíří nad svou buňku mřížky.
- Zkrácené hodnoty (pokud se zkracují) mají plný text v atributu `title`.
- `KanbanBoard.test.ts` je doplněný o test s dlouhým názvem, ID a workflow. Ověří, že se celý text vykreslí, a případně že je plná hodnota v `title`.
- `just web-test` a `just test` jsou zelené.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-19 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/117 · náklady $0.00
