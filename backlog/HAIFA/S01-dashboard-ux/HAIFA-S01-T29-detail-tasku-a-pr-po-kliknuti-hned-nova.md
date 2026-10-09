---
id: HAIFA-S01-T29
title: "Detail tasku a PR: po kliknutí hned nová položka, ne předchozí"
status: done
depends_on: [HAIFA-S03-T11]
related: [HAIFA-S01-T28]
---

## Zadání
Stejná chyba jako u detailu běhu (HAIFA-S01-T28) je i v Backlogu a v Review: po kliknutí na jiný task nebo jiné PR zůstává až do příchodu odpovědi vidět detail předchozí položky. `loadDetail` v `aifactory/web/src/views/BacklogView.vue` a v `aifactory/web/src/views/ReviewView.vue` nechává `detail` předchozí položky a šablona ho ukazuje (`TaskDetail v-if="detail"`, `ReviewDetail v-if="detail"`), dokud nedorazí nový. Odpověď staršího požadavku navíc může přepsat novější. Detail PR jde přes hosting, takže v Review to trvá déle.

Where: `aifactory/web/src/views/BacklogView.vue`, `aifactory/web/src/views/ReviewView.vue`, testy (vitest), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Po kliknutí na jiný task v Backlogu nebo jiné PR v Review (nebo změně URL) se předchozí detail hned přestane zobrazovat. Okamžitě je vidět id nové položky a stav načítání.
- Odpověď na starší požadavek nepřepíše novější: klik na A a hned na B skončí na B, i když odpověď pro A dorazí později. Živé aktualizace staré položky se do nové nepromítnou.
- Obnovení téže položky (Obnovit, živá aktualizace, načtení po akci) detail neschová a neblikne.
- Vitest s odloženou odpovědí API (`test/deferred.ts`) pro Backlog i Review: po kliknutí se stará položka nezobrazí, pomalá starší odpověď nepřepíše novější, obnovení téže položky detail neschová.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: detail běhu (HAIFA-S01-T28), zrychlení API.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/35 · náklady $1.18
