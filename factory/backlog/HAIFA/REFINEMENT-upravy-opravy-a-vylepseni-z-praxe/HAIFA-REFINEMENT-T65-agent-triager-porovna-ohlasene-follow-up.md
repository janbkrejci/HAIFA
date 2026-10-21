---
id: HAIFA-REFINEMENT-T65
title: "Agent triager: porovná ohlášené follow-upy s neudělaným backlogem"
status: done
workflow: plan-build-test
depends_on: []
writes: [aifactory/src/aifactory/seed/agents/triager/, aifactory/src/aifactory/library/seed.py, aifactory/src/aifactory/run/triage.py, aifactory/tests/run/test_triage.py, aifactory/tests/library/test_library_seed.py, aifactory/tests/config/test_config_loader.py, aifactory/tests/validation/test_validation_template.py]
---

## Zadání
Přidat read-only agenta `triager` a modul `aifactory/src/aifactory/run/triage.py`, který pro follow-upy ohlášené v běhu vyhodnotí zbytek neudělaného backlogu. Tento task jen připraví agenta a čistou funkci s rozhodnutími. Zapojení do zakládání follow-upů dělá HAIFA-REFINEMENT-T66.

## Vzor

Seed agent `learner` (soubory `agent.yaml`, `system.md`, `user.md`) a jeho volání `_ask_learner` ve `factory learn scan`: izolovaný checkout, `prepare_cfg`, `agents.resolve`, kontrola harnessu, `writes = []`, fáze s `AgentCall(output_type=..., gates=[...])` a jednou opravou. Oba soubory slouží jen jako vzor a nemění se. Seznam seed agentů je `SEED_AGENTS` v `aifactory/src/aifactory/library/seed.py`.

## Co udělat

1. Nový seed agent `aifactory/src/aifactory/seed/agents/triager/` (`agent.yaml` s `writes: []`, `system.md`, `user.md`). Instrukce: agent dostane follow-upy (title, reason, details, blocks_task, writes, for_human) a neudělané tasky backlogu (`status: todo`: id, titulek, step, tělo, writes, assignee). U každého follow-upu vrátí jedno rozhodnutí:
   - `covered`: práci už plně kryje existující task (`task_id`). Nic se nezakládá.
   - `extend`: práce do existujícího tasku patří a jde ho jen doplnit (`task_id`, `addition`: text doplnění). Doplnění smí zadání jen rozšířit o související práci. Nesmí zúžit, vypustit ani zásadně změnit původní zadání a musí se vejít do `writes` cílového tasku.
   - `decide`: práci by šlo pokrýt jen zúžením nebo zásadní změnou existujícího tasku (`task_id`, `proposal`: navrhovaná změna a proč). To rozhodne člověk.
   - `new`: nic v backlogu ji nekryje. Založí se nový TODO task.
   Každé rozhodnutí má `reason` (jedna věta).
2. `SEED_AGENTS` doplnit o `triager`.
3. `run/triage.py`: typy výstupu (pydantic, po vzoru `LessonsOutput`), funkce `context(reported, backlog)`, která sestaví vstup (jen `todo` tasky, ne `done` a `cancelled`, těla rozumně zkrácená), a `ask_triager(repo, reported, backlog) -> list[Decision]`. Brána (gate) zamítne: neznámé `task_id`, `task_id`, který není `todo`, `extend` na task člověka nebo na task, jehož `writes` doplnění nepokrývají, chybějící rozhodnutí u některého follow-upu. Po jedné neúspěšné opravě nebo při nedostupném agentovi či harnessu funkce vyhodí jasnou chybu, kterou volající umí zachytit (např. `TriageUnavailable`).
4. Bez follow-upů nebo bez jediného `todo` tasku se agent nevolá a všechna rozhodnutí jsou `new`.

## Mimo rozsah

- Zápis do backlogu, zapojení do zakládání follow-upů a dokumentace rozhodnutí (T66).
- `.factory/` a backlog.

Hotovo znamená:
- `aifactory/tests/run/test_triage.py` s namockovaným voláním agenta ověří sestavení kontextu (jen `todo` tasky), všechna čtyři rozhodnutí, odmítnutí neznámého nebo hotového `task_id` a `extend` mimo writes branou a zkratku bez volání agenta, když backlog nemá `todo` tasky.
- Testy seznamu seed agentů (`aifactory/tests/library/test_library_seed.py`, `aifactory/tests/config/test_config_loader.py`, `aifactory/tests/validation/test_validation_template.py`) počítají s agentem `triager` a jsou zelené.
- `factory library seed` nabídne agenta `triager`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/141 · náklady $0.00
