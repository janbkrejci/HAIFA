# HAIFA-S01-T29: Detail tasku a PR: po kliknutí hned nová položka, ne předchozí

## Problém
`loadDetail` v `BacklogView.vue` a `ReviewView.vue` nechával `detail` předchozí položky, dokud
nedorazila odpověď pro novou; odpověď staršího požadavku navíc mohla přepsat novější.

## Řešení
- Obě view si k `detail` pamatují `detailFor` (id tasku, ke kterému detail patří) a šablona
  ukazuje jen `shownDetail` – detail, jehož `detailFor` odpovídá aktuálnímu id z URL.
- `loadDetail` při přechodu na jinou položku detail hned zahodí; při obnovení téže položky
  (Obnovit, načtení po akci) ho nechá zobrazený.
- Čítač `loadSeq`: odpověď načtení, které už není poslední (nebo id z URL se mezitím změnilo),
  se zahodí a nemění ani `loading`, ani `error`.
- Živé obnovení zapíše detail jen tehdy, když id stále odpovídá otevřené položce.
- Během načítání je vidět id nové položky (`data-test="loading-id"`) a „Načítám…“.

## Testy
Vitest s `src/test/deferred.ts` v `BacklogView.test.ts` a `ReviewView.test.ts`: stará položka
se po kliknutí nezobrazí, pomalá starší odpověď nepřepíše novější, obnovení téže položky detail
neschová (Backlog navíc: živá aktualizace staré položky se do nové nepromítne).

## Build
`aifactory/src/aifactory/web/static/` přegenerováno `bun run build`.
