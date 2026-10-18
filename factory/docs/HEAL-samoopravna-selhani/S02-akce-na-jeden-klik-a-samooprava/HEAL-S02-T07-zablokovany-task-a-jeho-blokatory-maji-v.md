# HEAL-S02-T07: Zablokovaný task a jeho blokátory mají ve frontě přednost

## Co se změnilo

Blokovaný běh (druh `blocked`) zapíše do trace DB přednostní záznam: task a jeho
blokátory, včetně existujících tasků z `blocked_by`. Záznam čte každý výběr dalšího tasku,
nejen běžící řetěz.

| Kde | Dřív | Teď |
| --- | --- | --- |
| Přednost | jen nově založené follow-upy (`blockers_of`), jen pro jeden výběr v běžícím řetězu | záznam `task_priority` pro všechny výběry, dokud nezmizí |
| Existující blokátor z `blocked_by` | běžné pořadí | před frontou kanbanu |
| Blokovaný task po dokončení blokátorů | běžné pořadí, v řetězu se už nespustil | hned na řadě, i ve stejném řetězu |
| Kanban | — | tasky s předností nahoře sloupce se štítkem „přednostně“ a tlačítkem Zrušit přednost |
| `factory task list` | — | `[přednostně #N]` (pořadí v přednosti); JSON `priority` |

## Pořadí výběru

`queue.priority_order` (a `priority_map` s tím, čí záznam přednost dává):

1. blokované tasky (`todo`) s přednostním záznamem, jejichž blokátory jsou hotové (žádný
   blokátor není `todo`), od nejstaršího záznamu;
2. nehotové blokátory ostatních záznamů, každý až po svých nehotových blokátorech (jeho
   vlastní záznam a jeho nesplněné závislosti), a hned za nimi blokovaný task (kontroly
   výběru ho nechají čekat, dokud blokátory nejsou hotové nebo na jejich PR nejde
   navázat se `stacked_prs`);
3. fronta kanbanu a běžné pořadí.

`select_next`, `select_ready` i souběžné řetězy to dostanou přes `QueuePrefs.priority`.
Kontroly kandidáta (projekt řetězu, sloty, kolize `writes`, `auto_continue`, vyloučené
tasky) se nemění. Blokovaný task, jehož blokátory jsou úkoly backlogu, smí řetěz spustit
znovu (jednou za řetěz), až na něj podle závislostí dojde řada.

## Kdy záznam zmizí

- úspěšný běh tasku (`TaskRunStore.finish`),
- task už není `todo`: výběr ho nebere v úvahu, zápis tasku se stavem `cancelled` přes
  dashboard záznam smaže,
- člověk zruší přednost: `DELETE /api/backlog/tasks/{id}/priority`. U blokátoru se smažou
  záznamy, které mu přednost dávají.

Nový blok téhož tasku záznam přepíše (blokátory, běh), čas založení zůstane. Záznam
vznikne z druhu `blocked`, nebo z chyby začínající `blocked: `.

## API

`GET /api/backlog` vrací u tasku `priority_rank`, `priority_of` a `priority_blockers` a
celkově `priority` (záznamy tasků `todo`) a `priority_order`. Seznam `tasks` začíná tasky
s předností.

## Ověření

- `tests/run/test_auto_continue.py`: `test_existing_blocker_goes_before_the_kanban_queue`,
  `test_blocked_task_goes_right_after_its_last_blocker`, `test_blockers_of_blockers_go_first`,
  `test_store_keeps_the_priority_of_a_blocked_run`,
  `test_blocked_task_runs_again_in_its_chain_after_its_blocker`.
- `tests/run/test_parallel_chain.py`: `test_blocked_member_runs_again_after_its_blocker`.
- `tests/web/test_web_backlog_queue.py`: `test_priority_goes_first_and_can_be_cleared`,
  `test_task_list_prints_the_priority`, `test_cancelling_a_task_drops_its_priority`.
- Vitest `KanbanBoard.test.ts`: štítek a zrušení přednosti.
