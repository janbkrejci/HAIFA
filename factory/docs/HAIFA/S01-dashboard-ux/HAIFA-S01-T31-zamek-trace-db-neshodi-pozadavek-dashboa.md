# Zámek trace.db neshodí požadavek dashboardu (HAIFA-S01-T31)

## Co se změnilo

- **Git neběží pod zámkem DB.** `TaskRunStore.serialized()` už neotevírá zápisovou transakci `trace.db`. Je to zámek souboru `trace.db.lock` vedle databáze (`flock`, re-entrantní v procesu, čekání nejvýš 60 s). Kryje `git worktree add` při startu běhu, `config commit` a `config pull`. `claim()` a `live_runs()` ho berou také, takže se uprostřed bloku nespustí žádný běh.
- **Čekání místo pádu.** Každé spojení do `trace.db` čeká na uvolnění zámku až `BUSY_TIMEOUT` = 30 s (`aifactory.engine.tracer`), dřív 5 s. Platí to pro Tracer běhu, `TaskRunStore` (dashboard i CLI) a read-only čtení review.
- **Srozumitelná chyba.** Když zámek nepovolí ani po čekání, API vrátí HTTP 503 s kódem `trace_db_locked` a čitelnou zprávou, ne „database is locked“. Dashboard ukáže: „Databáze běhů je právě obsazená souběžnými běhy a ani po čekání se ji nepodařilo použít. Zkus to znovu za chvíli.“ a tlačítko **Zkusit znovu**. V Review tlačítko zopakuje akci, která selhala (schválit, vrátit, vyřešit konflikt), v Běhy a Backlog stránku znovu načte.

## Jak ověřit

```bash
cd aifactory
uv run pytest -n0 tests/run/test_trace_db_lock.py tests/web/test_web_db_busy.py
cd web && bunx vitest run src/lib/api.test.ts src/views/ReviewView.test.ts
```

Testy pustí proces, který drží zápisový zámek 6,5 s. Zápis běhu i `GET /api/runs` doběhnou po jeho uvolnění.
