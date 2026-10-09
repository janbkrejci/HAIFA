---
id: HAIFA-S02-T01
title: Sestavené prompty každé fáze běhu v API
status: done
depends_on: []
---

## Zadání
Ukládej sestavené prompty každé fáze běhu zvlášť a vydej je přes API dashboardu. Dnes se prompty ukládají po agentech a další fáze téhož agenta je přepíše, takže u fáze build je vidět prompt z revise_1 a u review_1 prompt z review_2.

Where: `aifactory/src/aifactory/engine/agents.py`, `aifactory/src/aifactory/engine/prompts.py`, `aifactory/src/aifactory/run/task.py`, `aifactory/src/aifactory/web/runs.py`, `aifactory/src/aifactory/web/app.py`, testy v `aifactory/tests/engine/` a `aifactory/tests/web/`. Vzor: route `/api/sessions/:adw_id/agents/:agent/prompts` ve `vendor/sssf/apps/visualizer/server/index.ts`.

Done means:
- Každá fáze agenta nechá v session adresáři běhu svůj system a user prompt pod jménem fáze. Dnešní `<agent>/prompts/{system,user}.md` zůstávají.
- `GET /api/runs/{run_id}/phases/{phase_id}/prompts` vrací system a user prompt té fáze. Pro starší běh bez promptů po fázích vrátí poslední prompty agenta a v odpovědi to označí. Chybějící soubor je `null` s HTTP 200, neznámý běh nebo fáze 404, neplatné id 400.
- Session adresář se hledá podle konfigurace běhu (`data_dir`, výchozí `.factory/data`), ne vedle trace DB. Cesta nikdy nevede ven ze session adresáře a příliš velký soubor se zkrátí.
- Testy (pytest, falešný harness): build a revise téhož agenta mají v API různé prompty, starší běh dostane prompty agenta, chybějící soubory, neznámý běh, neznámá fáze a pokus o cestu ven ze session adresáře.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: zobrazení v UI (samostatný úkol), soubory z `context_handoff/` a `raw_output.jsonl`.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory` jako dnešní úpravy (`# aifactory 2.9:`).
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/20 · náklady $2.34
