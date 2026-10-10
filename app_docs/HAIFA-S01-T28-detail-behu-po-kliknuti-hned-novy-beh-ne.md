# HAIFA-S01-T28: Detail běhu – po kliknutí hned nový běh

## Co se změnilo
- `aifactory/web/src/views/RunsView.vue` – `loadDetail`:
  - Při přechodu na jiný běh okamžitě zahodí `detail`, `events` a kurzory předchozího běhu; zobrazí se „Načítám běh `<id>`…" (`data-test="detail-loading"`).
  - `fetchRun` a `fetchAllEvents` běží souběžně, ale detail se ukáže hned po `fetchRun`; události se doplní po `fetchAllEvents` (do té doby `eventsLoading`).
  - Každé načtení dostane pořadové číslo (`loadSeq`); odpověď staršího načtení (nebo pro jiný běh, než je v URL) se zahodí, takže klik A → B vždy skončí na B.
  - Živý tail (`tail`) si pamatuje `loadSeq` a jeho odpověď se po přepnutí běhu nezapíše.
  - Obnovení stejného běhu (Obnovit, Zastavit, resync) nechává zobrazený dosavadní detail, dokud nepřijde nový. Přepnutí fáze běh znovu nenačítá (watch je jen na `runId`).
- `RunDetail.vue` / `PhaseDetail.vue` – nový volitelný prop `eventsLoading`: „Načítám události…" (`data-test="events-loading"`, ve sloupci událostí `phase-events-loading`) místo „Žádné události.".
- Build v `aifactory/src/aifactory/web/static/` přegenerován.

## Testy
`aifactory/web/src/views/RunsView.switch.test.ts` (odložené odpovědi přes `test/deferred.ts`):
starý běh zmizí hned po kliku, detail před událostmi, pomalá starší odpověď nepřepíše novější,
starý živý tail se nepřimíchá, přepnutí fáze nenačítá znovu.
