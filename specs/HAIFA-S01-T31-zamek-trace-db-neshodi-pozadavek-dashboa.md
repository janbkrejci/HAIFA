# HAIFA-S01-T31: Zámek trace.db neshodí požadavek dashboardu

## Problém

Do `trace.db` zapisují všechny běhy i dashboard. SQLite pouští jen jednoho zapisovatele a ostatní čekaly nejvýš 5 s (`busy_timeout`). Když zámek někdo držel déle, požadavek dashboardu skončil surovou chybou „database is locked“.

## Kde se zámek držel přes dlouhou práci

`TaskRunStore.serialized()` otevíral `BEGIN IMMEDIATE`, tedy zápisový zámek DB, a uvnitř běžel git:

- `run/task.py` `_execute`: `git worktree add` (a `ensure_excluded`) při startu každého běhu,
- `providers/publish.py` `_advance` (`config commit`): `git add`, `update-ref`, `basemoves.record`,
- `providers/publish.py` `pull_base` (`config pull`): `git.advance_branch`.

Ostatní zápisy (`Tracer`, `finish`, `save_pr`, `update_pr`, `mark_stopped`, `_reap`) jsou krátké příkazy v autocommitu nebo krátké transakce bez externích volání. Volání hostingu (`gh`) v `review/` a `web/` běží mimo transakci.

## Řešení

1. `serialized()` je zámek souboru `trace.db.lock` (`fcntl.flock`), re-entrantní v rámci procesu (RLock + čítač hloubky). Nedrží žádnou DB transakci, takže git pod ním neblokuje zápisy ostatních. `claim()` a `live_runs()` ho berou také, aby žádný běh nezačal uprostřed bloku (stejná záruka jako dřív). Čekání na zámek je omezené (`SERIAL_TIMEOUT` = 60 s), pak `TaskRunError("trace_db_locked")`.
2. `BUSY_TIMEOUT` = 30 s (`engine/tracer.py`) pro všechna spojení: `Tracer`, `TaskRunStore`, read-only spojení v `web/review.py` a `review/prbody.py`. Busy handler SQLite opakuje pokus, dokud zámek nepovolí nebo doba nevyprší. `Tracer` nastaví `busy_timeout` ještě před `journal_mode=WAL`.
3. Web: `is_db_busy(exc)` rozpozná „locked/busy“ i `trace_db_locked`. `_run_error` a handler pro `sqlite3.OperationalError` vrátí HTTP 503 s kódem `trace_db_locked` a srozumitelnou zprávou. Varování „runs are not shown“ v backlogu řekne, že je DB obsazená.
4. Dashboard: `api.ts` nahradí zprávu kódu `trace_db_locked` českou hláškou (`DB_BUSY_MESSAGE`). Chybový pruh v Běhy, Backlog a Review má tlačítko „Zkusit znovu“. V Review zopakuje neúspěšnou akci (např. resolve), jinde načte stránku znovu.

## Testy

- `tests/run/test_trace_db_lock.py`: jiný proces drží zápisový zámek 6,5 s, `claim`, `Tracer.session_start`, `Tracer.event` a `finish` počkají a uspějí. `serialized()` nedrží DB zámek. Zámek je výlučný mezi vlákny a re-entrantní. Po vypršení čekání vznikne chyba rozpoznaná přes `is_db_busy`.
- `tests/web/test_web_db_busy.py`: `GET /api/runs` (zapisuje přes `_reap`) při zámku drženém 6,5 s vrátí 200. Po vypršení čekání vrátí 503 `trace_db_locked` bez textu „database is locked“.
- Frontend: `api.test.ts` a `ReviewView.test.ts` ověří hlášku, tlačítko „Zkusit znovu“ a zopakování akce.
