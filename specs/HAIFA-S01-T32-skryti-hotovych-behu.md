# HAIFA-S01-T32: Skrytí hotových běhů

## Zadání

Jako v sssf: dokončené běhy (úspěch, chyba, přerušeno, zastaveno) jde archivovat.
Checkbox „Skrýt dokončené“ (T25) nahrazuje tlačítko „Archivovat dokončené“ s potvrzením.
Nad seznamem se přepíná zobrazení aktivních a archivovaných běhů. V archivu je
tlačítko „Vymazat všechny“ s potvrzením. Řádek aktivního běhu má na konci ikonu
archivace, řádek archivovaného ikonu vrácení z archivu a vpravo od ní ikonu smazání
z databáze. Klik na řádek (i archivovaný) otevře detail běhu.

## Řešení

- `task_runs.archived` (INTEGER, 0/1), starší trace DB dostane sloupec při otevření store.
- `TaskRunStore`: `archive` (běžící běh → `run_running`), `archive_finished`, `unarchive`,
  `delete_run` (jen archivovaný, jinak `run_not_archived`), `delete_archived`. Mazání
  odstraní řádek `task_runs` a řádky běhu v tabulkách trace v jedné transakci.
- API: `GET /api/runs?archived=1`, `POST /api/runs/archive-finished`,
  `POST /api/runs/delete-archived`, `POST /api/runs/{id}/archive|unarchive|delete`.
- Frontend: přepínač Aktivní/Archivované, hromadné akce, ikony v řádcích, ConfirmDialog
  pro hromadné akce a smazání jednoho běhu, klik na řádek otevře detail.
