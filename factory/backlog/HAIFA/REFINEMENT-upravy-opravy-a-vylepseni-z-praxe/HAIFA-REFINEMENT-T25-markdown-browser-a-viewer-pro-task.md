---
id: HAIFA-REFINEMENT-T25
title: Markdown browser a viewer pro task
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T21, HAIFA-REFINEMENT-T11, HAIFA-S01-T04, HAIFA-S10-T03]
writes: [aifactory/]
---

## Zadání
Navrhni a implementuj funkci, která umožní prohlížet markdowny související s taskem, tedy např. položku backlogu, specs a docs. Pokud to není možné, tak pro repo můžeme udělat takový viewer, který nebude obsahovat nic než markdowny z celého repa (kromě složek v .gitignore).

## Kontext
- Dokumenty tasku jsou pod `docs_root` (viz `.factory/config.yaml` a `aifactory/src/aifactory/config/settings.py`):
  - položka backlogu: `<docs_root>/backlog/...`, cestu už zná detail tasku (`task.path`),
  - spec: `<docs_root>/specs/<project>/<step>/<task-id>-<slug>.md`,
  - doc: `<docs_root>/docs/<project>/<step>/<task-id>-<slug>.md`.
- Markdown se v dashboardu vykresluje přes `MarkdownView.vue` a `lib/markdown.ts`. Tento render použij znovu, nezaváděj druhý.

## Požadavky
1. V detailu tasku v dashboardu půjdou zobrazit markdowny, které k tasku patří: položka backlogu, spec a doc, pokud existují. Soubor, který neexistuje, se jako dokument nenabízí nebo je zřetelně označený jako chybějící.
2. Backend poskytne seznam těchto dokumentů a jejich obsah. Dokumenty se hledají podle ID tasku, ne podle zadané cesty, takže API nepřečte nic mimo repo.
3. Pokud se ukáže, že dokumenty tasku spolehlivě dohledat nejde, udělej místo toho viewer markdownů celého repa. V něm jsou jen soubory `*.md` a vynechané jsou soubory ignorované gitem (`.gitignore`). V tom případě svou volbu zdůvodni ve výsledku.
4. Prohlížení dokumenty jen čte, nic nezapisuje.

## Akceptační kritéria
- U tasku, který má spec nebo doc (např. HAIFA-REFINEMENT-T21), jdou z detailu tasku otevřít a vykreslit položka backlogu, spec i doc.
- U tasku bez specu a docu se ukáže jen položka backlogu a nic nespadne.
- API nevrátí obsah souboru mimo repo ani soubor, který není markdown.
- Jsou testy backendu (pytest) i frontendu (vitest), `just test` prochází a zbuildovaný bundle ve `web/static` je aktualizovaný přes `just web-build`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/38 · náklady $2.32
