---
id: HAIFA-REFINEMENT-T68
title: "Build success bez změn a bez already_done: běh nesmí tiše otevřít PR jen se specem"
status: todo
depends_on: []
writes: [aifactory/src/aifactory/workflow/interpreter.py, aifactory/src/aifactory/engine/data_types.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/run/unchanged.py, aifactory/src/aifactory/review/automerge.py, aifactory/tests/, docs/decisions.md]
---

## Zadání
Builder, který nic nezmění a nevyplní `already_done`, nechá běh projít bez testů a review. Běh pak otevře PR jen se specem plánovače a automerge ho odmítne („no review ran in this run“). V řetězci auto-continue to znamená zastavení, dokud ho člověk neodblokuje. Továrna by tento případ měla poznat sama.

## Současný stav (naměřeno v NEO_HEF 2026-10-21, factory 0.1.472)

- Úloha `ROB-TODO-T43`, běh `92b67c66`, workflow `haifa-implement-task` (plan → commit_plan → build → test_plan/test/fix → review/revise → commit_build → changes → document → commit_docs, `accept: test.passed and review.approved`).
- Plánovač zjistil, že práci už udělala jiná úloha (`ROB-TODO-T42`, commit `03cc8f190`), a commitnul spec. Builder vrátil `BuildOutput` se `status: success`, `changed_files: []` a bez `already_done` („Nothing to change. Commit 03cc8f190 … already updated both SAU comments“).
- Běh skončil `succeeded`. Testy ani review neběžely (souhrn PR: „review neběželo“). PR #30601 obsahoval jen spec (`factory/specs/…/ROB-TODO-T43-*.md`, 21 řádků).
- `review/automerge.py:167` vrátil `no_review` → PR zůstal otevřený a řetězec se zastavil. Uživatel to musel odblokovat přes `factory task approve`.
- Cesta `already_done` (`engine/data_types.py` `BuildOutput.already_done`, `workflow/interpreter.py:563` `stop_if_first_build`, `run/unchanged.py`) by běh správně ukončila bez PR a úlohu označila jako hotovou bez změn. Jenže závisí na tom, že builder pole vyplní.

## Co udělat

1. Když první build běhu vrátí `success` bez změn kódu (prázdné `changed_files` a žádný commit mimo spec plánovače) a bez `already_done`, nesmí běh tiše projít. Možnosti (vybrat a zdůvodnit v `docs/decisions.md`):
   - a) Továrna vyžádá od builderu doplnění `already_done` (evidence), nebo běh ukončí s `failure_kind` (např. `invalid_output` s jasným textem) místo úspěchu.
   - b) Továrna případ převede na cestu `already_done`, když builder v `summary` uvede důkaz. Vyžaduje bezpečné rozpoznání, takže spíš ne.
   - c) Spec-only běh (jediný commit je `commit_plan`) se nepublikuje jako PR a úloha zůstane k rozhodnutí operátora (dashboard), ne jako otevřený neslučitelný PR.
2. Prompt/role builderu: výslovně uvést, že hotová práce se hlásí přes `already_done` s evidencí, nikdy prázdným `success`. (V NEO_HEF je to doplněné ve skillu `haifa-implementation-step`, PR #30606. Továrna by to ale neměla nechat jen na repo skillu.)
3. Automerge: když PR nemá žádnou změnu mimo spec, hlášení „no review ran“ doplnit o důvod („build nezměnil kód, chybí already_done“), aby operátor věděl, co udělat.

## Hotovo znamená

- Build `success` bez změn a bez `already_done` už neskončí otevřeným PR jen se specem, který automerge odmítne. Běh buď skončí jasnou chybou, nebo cestou bez PR.
- Testy pokrývají případ „builder success, prázdný diff, bez already_done“ a případ s `already_done`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
