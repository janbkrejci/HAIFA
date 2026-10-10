# Detail tasku a PR: po kliknutí hned nová položka

V Backlogu (`#/backlog/<task>`) i v Review (`#/review/<task>`) se po přechodu na jinou položku
předchozí detail okamžitě skryje; místo něj je vidět id nové položky a „Načítám…“, dokud
nedorazí odpověď.

- Pozdní odpověď na dřívější požadavek (klik na A a hned na B) se zahodí – obrazovka skončí na B.
- Živé aktualizace předchozí položky se do nově otevřené nepromítnou.
- Obnovení téže položky (tlačítko Obnovit, živá aktualizace, načtení po akci) detail neskryje.

Implementace: `aifactory/web/src/views/BacklogView.vue`, `aifactory/web/src/views/ReviewView.vue`
(`detailFor`, `shownDetail`, `loadSeq`). Testy: `BacklogView.test.ts`, `ReviewView.test.ts`
(blok „switching the open …“).
