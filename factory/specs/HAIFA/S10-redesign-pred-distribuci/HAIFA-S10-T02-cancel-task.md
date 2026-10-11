# HAIFA-S10-T02 — Cancel task

## Cíl
Task, který ještě neproběhl, jde v dashboardu zrušit jedním tlačítkem. Dostane status
`cancelled` a kanban ho ukáže ve sloupci Zrušeno.

## Řešení
- Backend se nemění: `edit_task(status="cancelled")` (`POST …/tasks/<id>/edit`) už status
  `cancelled` umí a stav na boardu je pak `cancelled`.
- `aifactory/web/src/components/backlog/TaskDetail.vue`: tlačítko „Zrušit“
  (`data-test="cancel-task"`) v hlavičce detailu, jen pro tasky, které ještě nezačaly
  (`DEFERRABLE_STATES`: todo, ready, blocked). Po potvrzení v `ConfirmDialog` emituje
  `cancel-task`.
- `aifactory/web/src/views/BacklogView.vue`: `onCancelTask` zapíše `{status: "cancelled"}`
  přes `editTask` (akce `cancel`, spinner na tlačítku) a znovu načte detail i seznam.
- Testy: `TaskDetail.test.ts` (potvrzení, zrušení dialogu, žádné tlačítko pro done,
  cancelled, running, in review), `BacklogView.test.ts` (zápis a obnovení detailu).
- `web/static` přestavěno (`just web-build`).
