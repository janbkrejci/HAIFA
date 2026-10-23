---
id: HAIFA-REFINEMENT-T70
title: "Nový záměr: proposer běží s harnessem, modelem a thinking cílového projektu nebo stepu"
status: todo
workflow: plan-build-test
depends_on: [HAIFA-REFINEMENT-T69]
writes: [aifactory/src/aifactory/workflow/propose.py, aifactory/src/aifactory/web/intent.py, aifactory/tests/workflow/test_backlog_propose.py, aifactory/tests/web/test_web_intent.py, aifactory/tests/intent_fixture.py]
---

## Zadání
Cíl: když člověk zadá Nový záměr do konkrétního projektu nebo stepu, agent `proposer` poběží se stejným harnessem, modelem a thinking jako tasky v tomto projektu nebo stepu. Při automatickém umístění (`target.kind: auto`) poběží s výchozím nastavením počítače (topbar), stejně jako kterýkoli objekt na úrovni repa.

Dnes `run_proposer` v `aifactory/src/aifactory/workflow/propose.py` bere agenta jen z rosteru (`agents.resolve(cfg, PROPOSER_AGENT)`) a kontext nebere v úvahu vůbec.

Co udělat:
- V `run_proposer` (i v jeho refinement kole, které má zůstat ve stejné session a se stejným harnessem) spočítat binding funkcí z HAIFA-REFINEMENT-T69 pro cílový kontejner, případně pro repo. Aplikovat ho na roster přes `apply_agents_override` z `run/task.py` před `agents.resolve`. Kontrola `ensure_enabled` a `check_harness` dál běží, ale na výsledném harnessu.
- Zvolený harness, model a thinking zapsat do stavu jobu v `aifactory/src/aifactory/web/intent.py` (např. pole `agent` v `IntentJob.json()`), aby je dashboard mohl ukázat.
- CLI `factory backlog propose` se chová stejně jako dashboard.

Mimo rozsah: frontend dialogu Nový záměr, ostatní agenti.

Hotovo znamená:
- `aifactory/tests/workflow/test_backlog_propose.py` ověřuje: s cílem projekt nebo step, který má `harness: codex` (a model, thinking), proposer běží na codexu s těmito hodnotami. S automatickým umístěním běží s výchozím harnessem počítače. Refinement zůstává na stejném harnessu.
- `aifactory/tests/web/test_web_intent.py` ověřuje, že stav jobu obsahuje použitý harness, model a thinking.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
