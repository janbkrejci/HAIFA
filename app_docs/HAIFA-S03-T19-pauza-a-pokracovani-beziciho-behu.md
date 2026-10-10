# Pauza a pokračování běžícího běhu

```bash
factory task pause <task-id> [--run RUN_ID] [--json]   # běh doběhne fázi a počká
factory task resume <task-id> [--run RUN_ID] [--json]  # běh pokračuje další fází
factory task stop <task-id>                            # funguje i na pozastavený běh
```

- Pauza platí na hranici fáze. Rozběhnutá fáze (agent, test) doběhne. Do té doby je běh
  `pausing` (pozastavuje se), potom `paused` (pozastaveno). Proces běhu zůstane živý,
  nic se nezmrazuje.
- Pozastavený běh má v DB stále stav `running` a `pause = paused`. Drží místo
  v `max_parallel_runs`, blokuje další běh téhož tasku a auto-continue řetěz na něj čeká.
- Pauza požádaná v poslední fázi se zahodí, běh normálně doběhne.
- `resume` zruší i pauzu, která ještě nezačala (`pausing`).
- Chyby (exit 2, nic se nezmění): `run_not_running` (task nemá běžící běh),
  `run_already_paused`, `run_not_paused`.
- Pauza nepřežije restart počítače: proces zmizí a běh se označí `aborted`.
- Dashboard: v detailu běhu jsou tlačítka Pauza a Pokračovat a stav `paused` je vidět
  v seznamu běhů, v detailu, v panelu řetězu a v detailu tasku. API:
  `POST /api/runs/{id}/pause` a `POST /api/runs/{id}/resume`.
