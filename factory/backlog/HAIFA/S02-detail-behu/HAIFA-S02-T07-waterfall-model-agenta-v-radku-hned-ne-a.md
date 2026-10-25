---
id: HAIFA-S02-T07
title: "Waterfall: model agenta v řádku hned, ne až po refreshi"
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-S02-T03]
writes: [aifactory/web/src/lib/waterfall.ts, aifactory/web/src/lib/waterfall.test.ts, aifactory/web/src/lib/runs.ts, aifactory/web/src/lib/runs.test.ts, aifactory/web/src/views/RunsView.vue, aifactory/web/src/views/RunsView.test.ts, aifactory/web/src/components/runs/RunWaterfall.test.ts, aifactory/src/aifactory/web/runs.py, aifactory/tests/web/test_web_runs.py, aifactory/src/aifactory/web/static/]
---

## Zadání
## Problém
V detailu běhu (waterfall/gantt, komponenta RunWaterfall) se u řádku agenta zobrazuje použitý LLM model (`lane-model`, ikona poskytovatele + název) až po ručním refreshi stránky. Model je přitom známý od chvíle, kdy agent startuje. Engine zapisuje událost `agent_start` s `payload.model` ještě před spuštěním harnessu. Řádek agenta má model ukázat hned, jak vznikne.

## Kde to je
- `aifactory/web/src/lib/waterfall.ts` – `buildLanes()` bere model řádku jako `info?.model ?? start?.model`. `info` je `detail.agents` (tabulka `agent_sessions`, zapisovaná až s hotovou session agenta), `start` je první `agent_start` vlastníka z `events` (`ownerStarts`).
- `aifactory/web/src/lib/runs.ts` – `applyTail()` slučuje do načteného běhu přírůstek z `GET /api/runs/{id}/tail` (phases, events, agents).
- `aifactory/web/src/views/RunsView.vue` – `tail()` volá živé doplňování.
- `aifactory/src/aifactory/web/runs.py` – `run_tail()`, `_phases()` (PhaseRow.model z `agent_start`, záloha z `agent_sessions`) a `_agent_sessions()`.

## Co udělat
1. Nejdřív testem reprodukovat chybu: běh načtený bez modelu, potom tail s fází agenta a jeho `agent_start`, případně se změněnou fází a bez řádku v `agent_sessions`. Zjistit, kde se model při živém doplňování ztrácí (frontend, nebo data z tailu).
2. Opravit příčinu tak, aby se model řádku agenta zobrazil v prvním tailu, ve kterém je o něm cokoli známo. Zdrojem může být `agent_start`, `PhaseRow.model` libovolné fáze řádku nebo `detail.agents`. Robustní varianta: v `buildLanes` brát jako další zálohu model z fází řádku (`phases` daného ownera).
3. Pokud je příčina v backendu (tail nevrací potřebná data), opravit ji v `aifactory/src/aifactory/web/runs.py` a pokrýt testem v `aifactory/tests/web/test_web_runs.py`.
4. Po změně frontendu přegenerovat commitnutý statický build `just web-build` (`aifactory/src/aifactory/web/static/`).

## Omezení
- Neměnit vzhled řádku ani tooltipu, jen to, kdy se model objeví. Komponenta waterfallu se nemění.
- Neměnit schéma trace DB ani engine.
- Mimo rozsah: kontext (context bar), barvy řádků a další údaje řádku.

Hotovo znamená:
- Nový unit test ve `waterfall.test.ts` nebo `runs.test.ts`: po `applyTail` s fází agenta a jeho `agent_start` (bez `agent_sessions`) má řádek agenta v `buildLanes` vyplněný `model`. Bez opravy test selže, s ní projde.
- Test řádku: když jedinou informací o modelu je `PhaseRow.model` fáze řádku, `buildLanes` vrátí tento model.
- V prohlížeči se u běžícího běhu objeví model v řádku agenta zároveň se vznikem řádku, bez refreshe.
- Projdou stávající testy waterfallu, RunDetail, RunsView a `aifactory/tests/web/test_web_runs.py`.
- `aifactory/src/aifactory/web/static/` je přegenerovaný přes `just web-build`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-23 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/146 · náklady $0.00
