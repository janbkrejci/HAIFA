# HAIFA-S01-T32: Skrytí hotových běhů (archiv běhů)

## Co se změnilo

Přepínač **Skrýt dokončené** z T25 nahradil archiv běhů podle sssf.

- Nad seznamem běhů je přepínač **Aktivní / Archivované**. Aktivní zobrazení ukazuje jen
  nearchivované běhy, archivované zobrazení jen archivované. Filtry Stav a Task platí v obou.
- V aktivním zobrazení je tlačítko **Archivovat dokončené**. Po potvrzení v modálním
  dialogu dostanou všechny dokončené běhy (úspěch, chyba, přerušeno, zastaveno) flag
  `archived`. Běžící běh se nearchivuje.
- V archivovaném zobrazení je tlačítko **Vymazat všechny**. Po potvrzení smaže všechny
  archivované běhy z databáze, nevratně.
- Řádek aktivního dokončeného běhu má na konci ikonu archivace. Řádek archivovaného běhu
  má ikonu vrácení z archivu a úplně vpravo ikonu smazání z databáze (s potvrzením).
- Klik kamkoli na řádek (mimo odkazy a ikony) otevře detail běhu, i archivovaného.
- Součty nákladů (`CostTotals`) dál zahrnují všechny běhy v databázi, archivované také.
  Smazaný běh v nich už není.

## Data a API

- Sloupec `task_runs.archived` (`INTEGER NOT NULL DEFAULT 0`). Starší trace DB ho dostane
  při otevření `TaskRunStore`.
- Smazání běhu odstraní řádek `task_runs` a řádky běhu (`adw_id`) v tabulkách `events`,
  `envelopes`, `gate_results`, `processes`, `agent_sessions`, `phases` a `sessions`
  v jedné transakci. Adresář session na disku zůstává. Záznam PR (`task_prs`) také zůstává.
- `GET /api/runs?archived=1` vrací archivované běhy, bez parametru aktivní. Každý běh
  má pole `archived`.
- `POST /api/runs/archive-finished` → `{archived: [run_id…]}`
- `POST /api/runs/delete-archived` → `{deleted: [run_id…]}`
- `POST /api/runs/{run_id}/archive` a `/unarchive` → `{run}`. Archivace běžícího běhu
  vrací HTTP 409 `run_running`.
- `POST /api/runs/{run_id}/delete` → `{deleted: [run_id]}`. Smazání nearchivovaného běhu
  vrací HTTP 409 `run_not_archived`.
- Live: změna `archived` nebo smazání běhu vyvolá `trace` událost s `runs_changed`.

## Soubory

- `aifactory/src/aifactory/run/store.py`: sloupec, `archive`, `archive_finished`,
  `unarchive`, `delete_run`, `delete_archived`
- `aifactory/src/aifactory/web/runs.py`, `web/app.py`, `web/live.py`, `skill/codes.py`
- `aifactory/web/src/lib/runs.ts`: `fetchRuns(filters, archived)`, `isFinished`,
  `archiveRun`, `unarchiveRun`, `deleteRun`, `archiveFinishedRuns`, `deleteArchivedRuns`.
  `HIDE_DONE_KEY`, `loadHideDone`, `saveHideDone` a `visibleRuns` byly odstraněny.
- `aifactory/web/src/components/runs/RunsList.vue`, `aifactory/web/src/views/RunsView.vue`
- testy: `tests/web/test_web_runs.py`, `lib/runs.test.ts`, `RunsList.test.ts`, `RunsView.test.ts`
- přebuildovaný frontend v `aifactory/src/aifactory/web/static/`
