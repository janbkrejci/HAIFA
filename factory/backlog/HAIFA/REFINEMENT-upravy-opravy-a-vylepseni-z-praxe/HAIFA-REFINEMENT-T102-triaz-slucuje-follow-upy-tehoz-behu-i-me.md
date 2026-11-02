---
id: HAIFA-REFINEMENT-T102
title: Triáž slučuje follow-upy téhož běhu i mezi sebou
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T101]
writes: [aifactory/src/aifactory/run/triage.py, aifactory/src/aifactory/run/followups.py, aifactory/src/aifactory/seed/agents/triager/, aifactory/tests/run/test_triage.py, aifactory/tests/run/test_followups_triage.py, aifactory/tests/run/test_followups.py]
---

## Zadání
`followups.collect` (aifactory/src/aifactory/run/followups.py) slučuje follow-upy jednoho běhu jen podle normalizovaného titulku. Triáž (run/triage.py, seed agent `triager`) porovnává každý follow-up jen s todo tasky backlogu a `covered`, `extend` i `decide` vyžadují `task_id` existujícího tasku. Dva follow-upy téhož běhu s různým titulkem a stejnou prací proto založí dva tasky.

Doložené případy z NEO_HEF (factory 0.1.545 až 0.1.563):
- UIRTODO-TODO-T39 (builder: rámečky PictureBox jako zastávky Tabu ve všech formulářích UIR) a T40 (documenter: totéž pro jeden rámeček v detailu obce). T40 je celá obsažená v T39, a přesto dostala vlastní běh.
- MAT-TODO-T52, T54 a T57: tři lidské tasky ze stejného běhu MAT-S55-T001 se stejnou otázkou Q-S55-1, ohlášené builderem, dalším agentem a documenterem.

Co udělat:
- Triáž dostane follow-upy téhož běhu jako možné cíle. Rozhodnutí `covered` (případně nová akce, např. `duplicate`) smí odkazovat na jiný follow-up téhož běhu (`follow_up_id` cíle) místo `task_id`. Cílem je vždy follow-up, který práci pokrývá celou. Kryté follow-upy se nezaloží a jejich `origins` a `blocks_task` přejdou na cíl, stejně jako dnes při shodě titulku v `collect`.
- Stejně se slučují i follow-upy `for_human`. Lidský follow-up nesmí skončit pokrytý agentním a naopak.
- Řetězy odkazů (f3 → f2 → f1) a cykly ošetří deterministická kontrola v run/triage.py: cyklus nebo odkaz na neexistující id je neplatné rozhodnutí a jde do jedné opravy jako ostatní.
- Upravit instrukce `triager` (seed/agents/triager/system.md).

Mimo rozsah: slučování napříč různými běhy (to už dělá porovnání s backlogem), změny promptů ostatních agentů.

Hotovo znamená:
- Test v aifactory/tests/run/test_followups_triage.py: běh s dvěma follow-upy (široký a jeho podmnožina s jiným titulkem), triáž označí podmnožinu jako krytou širším, vznikne jeden task, ve kterém je původ z obou agentů.
- Test: tři lidské follow-upy se stejnou otázkou vytvoří jeden lidský task.
- Test v aifactory/tests/run/test_triage.py: cyklus a odkaz na neexistující follow-up jsou odmítnuté.
- Stávající testy triáže a follow-upů procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
