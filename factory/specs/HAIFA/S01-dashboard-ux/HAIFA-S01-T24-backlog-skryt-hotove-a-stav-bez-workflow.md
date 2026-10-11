# HAIFA-S01-T24: Backlog – skrýt hotové a stav Bez workflow

## Zadání

Přidat na obrazovku Backlog přepínač „Skrýt hotové“ a přejmenovat stav `todo` z „K přípravě“ na „Bez workflow“.

## Řešení

1. `lib/backlog.ts`
   - `STATE_LABELS.todo` = „Bez workflow“, `STATE_TOOLTIPS.todo` = „Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).“
   - `OPTIONAL_STATES` (`todo`) a `presentStates(states, counts)`: volitelný stav jen s nenulovým počtem.
   - `stateCounts(data)`: `state_counts` z API, jinak spočítané z `tasks`.
   - Přepínač: `HIDE_DONE_KEY` (`haifa.backlog.hideDone`, `'1'`/`'0'`), `hideDone()`, `setHideDone()`, `resetHideDoneForTests()` (volá ho i `resetTreeForTests`).
   - `pruneDone(items)`: strom bez tasků Hotovo/Zrušeno a bez kontejnerů, kterým nezůstal žádný task. `graphWithoutDone(graph)`: graf bez takových tasků a jejich hran.
2. `BacklogFilters.vue`: checkbox `data-test="hide-done"` (emit `update:hideDone`). Prop `counts` skryje volbu Bez workflow, pokud v tom stavu není žádný task. Vybraný filtr zůstane v nabídce.
3. `KanbanBoard.vue`: sloupce podle prop `states`, šířka mřížky podle jejich počtu, tooltip u nadpisu sloupce Bez workflow.
4. `StateChip.vue`: tooltip u stavu `todo`.
5. `BacklogView.vue`: stav přepínače, prořezaný strom, kanban bez hotových tasků a sloupců, sloupec Bez workflow jen s nenulovým počtem, graf bez hotových tasků. Přepínač je i v hlavičce grafu.
6. `web/backlog.py`: `/api/backlog` vrací `state_counts`, tedy počet tasků v každém stavu přes celý backlog bez ohledu na filtr stavu. Odvozování stavu v core se nemění.
7. Nový build do `aifactory/src/aifactory/web/static/`.

## Testy

vitest: `lib/backlog.test.ts`, `BacklogFilters.test.ts`, `KanbanBoard.test.ts`, `StateChip.test.ts`, `BacklogView.test.ts`. pytest: `tests/web/test_web_backlog.py` (`state_counts`).
