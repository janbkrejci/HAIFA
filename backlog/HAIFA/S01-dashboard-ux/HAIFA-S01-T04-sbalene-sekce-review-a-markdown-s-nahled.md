---
id: HAIFA-S01-T04
title: Sbalené sekce Review a markdown s náhledem a zdrojem
status: done
depends_on: [HAIFA-S01-T03]
---

## Zadání
Všechny skládací sekce v detailu PR na obrazovce Review začínají sbalené. Všechny markdown sekce se ukazují jako náhled, přepnutelný záložkou na zdroj.

Where: `aifactory/web/src/` (`components/review/ReviewDetail.vue`, `components/review/DiffView.vue`, `components/review/ReviewActions.vue`, `components/runs/DetailSection.vue`, `components/backlog/TaskDetail.vue`, `style.css` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`. Zdroj rendereru: `vendor/sssf/apps/visualizer/src/lib/markdown.ts` a `vendor/sssf/apps/visualizer/src/lib/highlight.ts`.

Done means:
- Po otevření PR jsou sbalené sekce Popis PR, Běhy, Gates a testy, Verdikt revieweru, Diff i každý soubor diffu. Po přechodu na jiný PR se znovu sbalí.
- Akce (Schválit, Vrátit, Vyřešit konflikt, Dorovnat s base) nejsou skládací sekce a jsou vždy vidět nad ostatními (rozhodnutí v `docs/decisions.md`).
- Sdílená markdown komponenta má záložky Náhled a Zdroj, výchozí je Náhled. Používá ji Zadání v detailu tasku a Popis PR.
- Náhled vykreslí nadpisy, odstavce, seznamy, kód a odkazy. HTML komentáře v náhledu nejsou. Renderer escapuje celý vstup, takže HTML z textu se nevykoná, a odkazy jsou jen http(s). Renderer je převzatý z visualizeru sssf.
- Unit testy (vitest): renderer escapuje `<script>`, vynechá komentář a vykreslí nadpis, seznam a blok kódu. Komponenta začne v náhledu a přepne na zdroj. Sekce Review jsou sbalené po načtení i po změně PR.
- Prohlížečový test schválí PR bez otevírání sekcí.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: detail běhu (vlastní úkoly), tabulky v markdownu, editace zadání.

Pevná omezení:
- Žádná nová závislost frontendu, žádná knihovna na markdown.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/16 · náklady $2.15
