---
id: HAIFA-S01-T40
title: "Položka backlogu, spec a dokumentace v detailu tasku nepotřebují záložky Zdroj"
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T42, HAIFA-REFINEMENT-T45, HAIFA-S01-T04, HAIFA-REFINEMENT-T25]
writes: [aifactory/web/src/components/backlog/TaskDocuments.vue, aifactory/web/src/components/backlog/TaskDocuments.test.ts, aifactory/src/aifactory/web/static/]
---

## Zadání
## Cíl

V detailu tasku (karta se záložkami Zadání / Položka backlogu / Spec / Dokumentace, komponenta `TaskDocuments.vue`) se dokumenty Položka backlogu, Spec a Dokumentace zobrazují jen jako vykreslený markdown. Nemají vnitřní záložky **Náhled** / **Zdroj**, stejně jako je teď nemá Zadání.

## Současný stav

`TaskDocuments.vue` vykresluje obsah dokumentu přes `<MarkdownView … data-test="doc-content" />` bez `preview-only`, a proto se pod ním objeví záložky Náhled/Zdroj. Zadání už `preview-only` má.

## Požadavky

- MarkdownView pro dokumenty tasku (`doc-content`) se zobrazí v režimu `preview-only`. V kartě dokumentů tasku nezůstanou žádné záložky Náhled/Zdroj (`md-tab-preview`, `md-tab-source`) ani zdrojový pohled (`md-source`).
- Ostatní se nemění: cesta k souboru (`doc-path`), hláška u obsahu, který nejde zobrazit (`doc-problem`), prázdný dokument („Dokument je prázdný.“), chybějící dokumenty a front matter položky backlogu vykreslený v náhledu.
- Komponenta `MarkdownView` a její použití jinde (nastavení projektu/stepu, PR v Review, detail fáze běhu, RunDialog) zůstanou beze změny, Náhled/Zdroj tam zůstává.
- Upravit komentář v hlavičce `TaskDocuments.vue`, pokud po změně neodpovídá.
- Přegenerovat statický build dashboardu (`just web-build`), aby změnu viděl i nainstalovaný dashboard.

## Akceptační kritéria

- Unit test v `TaskDocuments.test.ts` ověří, že po otevření záložky Položka backlogu, Spec i Dokumentace se zobrazí `md-preview` a neexistuje `md-tab-source`, `md-tab-preview` ani `md-source`.
- Stávající testy `TaskDocuments`, `MarkdownView`, `ContainerSettings` a `PhaseDetail` projdou (`just web-test`).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/96 · náklady $0.74
