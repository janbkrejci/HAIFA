---
id: HAIFA-S01-T30
title: "Detail běhu: celé zadání místo výtahu 500 znaků"
status: done
depends_on: []
---

## Zadání
Detail běhu ukazuje zadání oříznuté na 500 znaků bez výpustky. `session_request` v `aifactory/src/aifactory/engine/tracer.py` ukládá do `sessions.request` jen `request[:500]` a `RunDetail.vue` zobrazuje právě toto pole (`detail.session.request`). U resolve tasku HAIFA-S03-T11 tak popis končí uprostřed věty („keep what thi“), i když agent dostal zadání celé. Celé zadání je v trace v události fáze request.

Where: `aifactory/src/aifactory/engine/tracer.py`, API detailu běhu v `aifactory/src/aifactory/web/`, `aifactory/web/src/components/runs/RunDetail.vue`, `aifactory/web/src/lib/runs.ts`, testy (pytest, vitest), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Detail běhu ukazuje celé zadání běhu. Dlouhé zadání je sbalené a jde rozbalit.
- U starších běhů, které mají v `sessions.request` jen výtah, API vezme celé zadání z události fáze request.
- Kde se zadání dál zkracuje (třeba v seznamu), končí výpustkou „…“, ne uprostřed slova.
- Testy: API vrátí celé zadání delší než 500 znaků, i pro běh se zkráceným `sessions.request`. Vitest: dlouhé zadání je sbalené a po rozbalení celé.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: zadání v promptu agenta (je celé).

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/31 · náklady $1.27
