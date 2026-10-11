# HAIFA-S03-T19: Pauza a pokračování běžícího běhu

## Cíl

Běžící běh jde pozastavit na hranici fáze a později pustit dál ve stejném worktree a větvi.

## Návrh

- `task_runs.pause` (nový sloupec, starší DB ho dostanou při otevření): `NULL`, `pausing`
  (pauza požádaná, fáze ještě běží), `paused` (proces čeká před další fází).
- Stav `task_runs.state` zůstává `running`. Pozastavený běh tak beze změny drží zámek tasku,
  místo v `max_parallel_runs` a čekání auto-continue řetězu, a `factory task stop` na něj
  funguje. Zobrazený stav je `paused` (`TaskRunRow.shown_state`, `shownState` v dashboardu).
- `run/pause.py`: `pause_run`, `resume_run` (CLI i dashboard) a `PauseGate`, kterou
  `_execute` předá do `run_workflow(phase_gate=...)`. Interpreter ji volá před každou role
  a code fází. Brána změní `pausing` na `paused` a dotazuje se DB (1 s), dokud pauza
  nezmizí. Když běh mezitím přestane být `running` (stop), vyhodí výjimku.
- Pauza požádaná v poslední fázi nemá na co čekat: běh doběhne, `finish` pauzu smaže.
  Stejně ji smaže `mark_stopped` a označení mrtvého běhu jako `aborted`.
- Chybové kódy (exit 2, nic se nezmění): `run_not_running`, `run_already_paused`,
  `run_not_paused`. `resume` zruší i čekající `pausing`.
- CLI: `factory task pause|resume ID [--run RUN_ID] [--json]`.
- Web: `POST /api/runs/{id}/pause`, `POST /api/runs/{id}/resume` (409 při chybě stavu),
  pole `pause` v souhrnu běhu a v běhu řetězu, filtr `?state=paused`. Živé události
  hlídají i sloupec `pause`.
- Dashboard: StatusChip `paused` (pozastaveno) a `pausing` (pozastavuje se). V detailu běhu
  jsou tlačítka Pauza a Pokračovat a Zastavit zůstává.
- `factory --skill`: postup „Pause, resume and stop“ a nové kódy.

## Testy

`tests/run/test_task_pause.py`, `tests/web/test_web_runs.py`, vitest `RunDetail`,
`RunsView` a `lib/runs`.
