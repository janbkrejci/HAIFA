# HAIFA-S01-T24: Backlog – skrýt hotové a stav Bez workflow

## Co se změnilo

- **Přepínač „Skrýt hotové“** je ve filtrech Backlogu a v hlavičce grafu závislostí. Když je zapnutý, zmizí tasky ve stavu Hotovo a Zrušeno ze stromu, z kanbanu (včetně sloupců Hotovo a Zrušeno) i z grafu (i jejich šipky). Projekt nebo step, kterému nezůstane žádný viditelný task, se ve stromu nezobrazí. Výchozí stav je vypnuto. Volbu si prohlížeč pamatuje v `localStorage` pod klíčem `haifa.backlog.hideDone` (`'1'`/`'0'`).
- **Stav `todo` se jmenuje „Bez workflow“** (dřív „K přípravě“). Odznak stavu a nadpis sloupce v kanbanu mají tooltip „Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).“
- **Sloupec Bez workflow a volba Bez workflow ve filtru stavu** se zobrazí jen tehdy, když v tom stavu nějaký task je. Počty bere dashboard z nového pole `state_counts` v `/api/backlog`, které počítá stavy přes celý backlog bez ohledu na filtr. Pokud je Bez workflow právě vybraný filtr, volba v nabídce zůstane.

## Kde to je

| Soubor | Změna |
|---|---|
| `aifactory/web/src/lib/backlog.ts` | `STATE_LABELS.todo`, `STATE_TOOLTIPS`, `OPTIONAL_STATES`, `DONE_STATES`, `presentStates`, `stateCounts`, `HIDE_DONE_KEY`, `hideDone`/`setHideDone`, `pruneDone`, `graphWithoutDone` |
| `aifactory/web/src/components/backlog/BacklogFilters.vue` | checkbox `hide-done`, prop `counts` a `hideDone` |
| `aifactory/web/src/components/backlog/KanbanBoard.vue` | tooltip sloupce (`column-tip`), počet sloupců mřížky podle `states` |
| `aifactory/web/src/components/backlog/StateChip.vue` | tooltip u `todo` (`state-tip-chip`) |
| `aifactory/web/src/views/BacklogView.vue` | aplikuje přepínač na strom, kanban a graf; počítá sloupce kanbanu |
| `aifactory/src/aifactory/web/backlog.py` | `state_counts` v odpovědi `/api/backlog` |
| `aifactory/src/aifactory/web/static/` | nový build |

## Jak ověřit

```sh
just web-test
just test && just typecheck && just lint && just e2e
```
