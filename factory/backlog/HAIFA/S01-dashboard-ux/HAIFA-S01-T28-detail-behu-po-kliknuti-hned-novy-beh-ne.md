---
id: HAIFA-S01-T28
title: "Detail běhu: po kliknutí hned nový běh, ne předchozí"
status: done
depends_on: [HAIFA-S02-T02]
---

## Zadání
Když v Bězích rozkliknu běh, nejdřív se ukáže detail běhu, který byl otevřený předtím, a až asi po dvou sekundách ten rozkliknutý. Příčina: `loadDetail` v `aifactory/web/src/views/RunsView.vue` nechává `detail` a `events` předchozího běhu, dokud nedorazí `fetchRun` i `fetchAllEvents` nového běhu. Odpověď pomalejšího staršího požadavku navíc může přepsat novější (klik na A a hned na B).

Where: `aifactory/web/src/views/RunsView.vue`, `aifactory/web/src/components/runs/`, testy (vitest), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Po kliknutí na jiný běh (nebo změně URL na jiný běh) se předchozí běh hned přestane zobrazovat. Okamžitě je vidět id nového běhu a stav načítání.
- Detail běhu se ukáže, jakmile dorazí `fetchRun`. Události se doplní, až dorazí `fetchAllEvents`.
- Odpověď na starší požadavek nepřepíše novější: klik na A a hned na B skončí na B, i když odpověď pro A dorazí později. Živé aktualizace starého běhu se do nového nepřimíchají.
- Přepnutí fáze v rámci stejného běhu běh znovu nenačítá a nezobrazí prázdný stav.
- Vitest s odloženou odpovědí API (`test/deferred.ts`): po kliknutí se starý běh nezobrazí, detail se ukáže před událostmi, pomalá starší odpověď nepřepíše novější.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: zrychlení API detailu běhu, detail tasku v Backlogu a detail PR v Review.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/34 · náklady $0.85
