# Spec HAIFA-S01-T28: Detail běhu – po kliknutí hned nový běh, ne předchozí

## Problém
`loadDetail` v `RunsView.vue` nechával detail předchozího běhu, dokud nedorazily `fetchRun` i `fetchAllEvents` nového; pomalejší starší odpověď mohla přepsat novější.

## Řešení
1. Při změně `runId` na jiný běh okamžitě vyčistit `detail`, `events`, `cursors`; zobrazit id nového běhu a stav načítání.
2. Spustit `fetchRun` a `fetchAllEvents` souběžně; detail nastavit hned po `fetchRun`, události po `fetchAllEvents` (`eventsLoading` → indikátor v `RunDetail`/`PhaseDetail`).
3. Sekvenční čítač `loadSeq`: výsledky zastaralého načtení (i chyby) se ignorují; `tail` se po změně `loadSeq` nezapisuje.
4. Přepnutí fáze téhož běhu nic nenačítá (beze změny – watch jen na `runId`).
5. Vitest `RunsView.switch.test.ts` s `deferred`; přebuildit `static/`.
