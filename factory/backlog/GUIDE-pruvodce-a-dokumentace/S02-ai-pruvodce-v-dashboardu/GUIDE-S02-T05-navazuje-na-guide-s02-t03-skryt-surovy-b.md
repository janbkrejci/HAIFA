---
id: GUIDE-S02-T05
title: "Navazuje na GUIDE-S02-T03: skrýt surový blok haifa-action během streamování"
status: done
archived: true
workflow: build-test-review
depends_on: [GUIDE-S02-T03]
writes: [aifactory/web/src/lib/assistant.ts, aifactory/web/src/lib/assistant.test.ts, aifactory/web/src/components/assistant/, aifactory/tests/e2e/test_assistant_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
Navazuje na GUIDE-S02-T03 (PR #80). Během streamování odpovědi průvodce je blok `haifa-action` krátce vidět jako surový kód, než ho po dokončení nahradí karta.

Zadání:
1. Rozepsaný (neuzavřený) blok `haifa-action` se během streamování nezobrazí jako kód. Místo něj se ukáže zástupná karta „Připravuji návrh akce…“.
2. Po uzavření bloku a dokončení odpovědi se zobrazí stávající karta s náhledem a tlačítky Provést/Zahodit, beze změny chování.
3. Ostatní bloky kódu se při streamování renderují jako dosud.

Hotovo znamená:
- Vitest na render částečné odpovědi s neuzavřeným blokem `haifa-action` (žádný surový JSON, zástupná karta).
- Browser test asistenta stále prochází.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

Mimo rozsah: backend parsování a ukládání návrhů, prompt agenta `guide`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/105 · náklady $1.11
