---
id: HAIFA-S01-T09
title: Běhy z dashboardu jako samostatné procesy factory task
status: done
depends_on: []
---

## Zadání
Spouštěj běhy z dashboardu (Spustit, Vrátit, Vyřešit konflikt) jako samostatné procesy `factory task run|return|resolve ID --repo KOŘEN --json` místo vlákna serveru. Dnes `run_task` mění pracovní adresář celého procesu a drží procesní zámek signálů (`run/task.py`), takže server pustí jen jeden běh najednou, Zastavit odmítne běh spuštěný z dashboardu („cannot stop itself“), `factory task stop` z terminálu pošle SIGTERM serveru a běhy skončí se serverem.

Where: `aifactory/src/aifactory/web/launcher.py`, `aifactory/src/aifactory/web/backlog.py`, `aifactory/src/aifactory/web/review.py`, `aifactory/src/aifactory/web/app.py`, `aifactory/src/aifactory/cli.py` (`factory obs`), `aifactory/validation/worker.py`, `aifactory/validation/fake.py`, `aifactory/tests/conftest.py`, testy v `aifactory/tests/web/` a `aifactory/tests/e2e/`. Nový modul s domovským adresářem HAIFA v `aifactory/src/aifactory/`.

Done means:
- Domovský adresář HAIFA je `$HAIFA_HOME`, jinak `$XDG_CONFIG_HOME/haifa`, jinak `~/.config/haifa`.
- Proces běhu startuje s `start_new_session`, zavřeným stdin, `cwd` v kořeni repa a prostředím serveru. Jeho JSON obálka a výpis jdou do souborů s právy 0600 v `logs/` domovského adresáře, nikdy do repa.
- Server čeká na nový řádek v `task_runs` jako dnes (po 30 s `pending`). Když proces skončí dřív, kód chyby z jeho obálky vrátí stejný HTTP stav jako dnes (`already_running` a `unmet_dependencies` 409, `no_pr` 404, ...). Nečitelná obálka vrátí `internal_error` s koncem výpisu.
- Běhy dvou tasků jednoho repa i dvou rep (dvě instance aplikace) běží souběžně. `run-check` vrací `launcher_busy: false`.
- Zastavit v dashboardu zastaví běh spuštěný z dashboardu. `factory task stop` zastaví proces běhu a server běží dál.
- Běh přežije ukončení serveru a nová instance aplikace ho vidí jako běžící. Skončený proces server vždy uklidí, takže zabitý proces nezůstane zombie a jeho řádek přejde na `aborted`.
- Prefix příkazu procesu jde nastavit. `python -m validation.worker` ho při `HAIFA_VALIDATE_FAKE` nastaví na sebe, takže procesy serveru z testu F3 běží nad falešným harnessem. Falešný harness bere pozici ve skriptu z `<script>.calls.jsonl`, takže druhý běh dostane druhou položku i v novém procesu.
- `tests/conftest.py` nastaví `HAIFA_HOME` na dočasný adresář pro každý test a ověří, že skutečný domov zůstal beze změny. Server v e2e testech ho dostane taky.
- `factory obs` při ukončení vypíše, kolik běhů spuštěných z dashboardu pokračuje.
- Testy (pytest): stub proces, který zabere řádek a čeká nebo skončí s obálkou, mapování chyb před zabráním, souběh, Zastavit přes API, nová instance aplikace, úklid procesu a jeden skutečný `task run` přes `validation.worker` se skriptem JSON. Testy v `tests/web/test_web_task_run.py` jsou upravené na nový spouštěč a projdou. Dnešní vláknový spouštěč smí zůstat jen jako testovací náhrada.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: více repozitářů v jednom serveru, limit souběžných běhů, `.env` pro jednotlivá repa, změna `factory task stop`, odstranění `launcher_busy` z frontendu.

Pevná omezení:
- `aifactory/src/aifactory/engine/` se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/7 · náklady $5.55
