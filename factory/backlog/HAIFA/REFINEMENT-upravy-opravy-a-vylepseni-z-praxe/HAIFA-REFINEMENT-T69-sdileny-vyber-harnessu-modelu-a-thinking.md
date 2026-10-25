---
id: HAIFA-REFINEMENT-T69
title: "Sdílený výběr harnessu, modelu a thinking pro AI pomocníky podle objektu (repo, projekt, step, task)"
status: done
archived: true
workflow: plan-build-test
depends_on: []
writes: [aifactory/src/aifactory/backlog/derived.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/harness/settings.py, aifactory/src/aifactory/workflow/adaptive.py, aifactory/src/aifactory/web/workflow_advice.py, aifactory/tests/backlog/, aifactory/tests/harness/test_harness_settings.py, aifactory/tests/web/test_web_workflow_advice.py, aifactory/tests/web/test_web_task_advice.py, aifactory/tests/workflow/test_workflow_advice.py]
---

## Zadání
Cíl: jedno místo, které pro objekt backlogu (task, step, projekt) nebo pro repo vrátí harness, model a thinking stejně, jako by s nimi běžel task v tomto objektu. Na tomto místě se potom postaví všichni pomocní AI agenti.

Dnešní stav:
- Běh tasku bere hodnoty přes `task_harness_values(task)` v `aifactory/src/aifactory/run/task.py` (když nižší úroveň přepne harness, zahodí model vyšší úrovně) a potom `harness_settings.effective_override(...)` a `apply_agents_override(...)`.
- Návrh workflow a parametrů tasku (`aifactory/src/aifactory/workflow/adaptive.py`, funkce `context` a `recommend`, a `aifactory/src/aifactory/web/workflow_advice.py`, `AdviceManager.start` a `_resolve`) skládá `ctx["effective"]` vlastním slučováním (`rc.config.settings`, defaults předků, draft). Model se při přepnutí harnessu nezahazuje, takže výsledek se od běhu tasku může lišit. U draftu nového tasku ve stepu se musí použít hodnoty stepu a jeho předků.

Co udělat:
1. Do `aifactory/src/aifactory/backlog/derived.py` přidat funkci (např. `harness_values(node)`), která pro Task i Container vrátí `harness`/`model`/`thinking` se stejnou sémantikou jako dnešní `task_harness_values` (od nejvyššího předka k uzlu, přepnutí harnessu zahodí zděděný model). Funkce `task_harness_values` v `run/task.py` zůstane jako tenký wrapper nad ní, chování běhu se nemění.
2. Přidat funkci (např. v `aifactory/src/aifactory/harness/settings.py`, třeba `context_binding(values)`), která vrátí výsledek `effective_override(values, None)`. Pro repo nebo stránku bez objektu to jsou výchozí hodnoty počítače (topbar, harnesses.json). Když počítač harness nastavený nemá, vrátí `{}` a volající použije svůj roster agent.
3. V `workflow/adaptive.py` a `web/workflow_advice.py` brát hodnoty `harness`/`model`/`thinking` v `ctx["effective"]` a v advisoru z nové funkce: pro existující task z tasku, pro draft nového tasku ze zvoleného stepu. Ruční volba harnessu nebo modelu v dialogu „Vylepšit task“ dál vyhrává. Pole `advisor` v odpovědi jobu musí ukazovat i `thinking`.

Mimo rozsah: Nový záměr, triáž follow-upů, lekce a AI průvodce (řeší je navazující tasky) a frontend. Chování běhu tasku se nemění.

Hotovo znamená:
- Nové testy v `aifactory/tests/backlog/` (nebo `tests/harness/test_harness_settings.py`) ukazují stejné hodnoty pro task, step a projekt, i když nižší úroveň přepíná harness.
- `aifactory/tests/web/test_web_workflow_advice.py`, `test_web_task_advice.py` a `aifactory/tests/workflow/test_workflow_advice.py` ověřují, že návrh workflow a „Vylepšit task“ u tasku v projektu s harness: codex a u draftu nového tasku v takovém stepu běží na codexu s modelem a thinking projektu. Ruční volba pořád vyhrává.
- Stávající testy běhu a retry tasku v adresáři testů `run` projdou beze změny.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-23 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/147 · náklady $0.00
