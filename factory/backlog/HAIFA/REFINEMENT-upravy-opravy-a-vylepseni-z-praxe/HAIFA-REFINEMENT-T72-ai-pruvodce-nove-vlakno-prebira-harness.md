---
id: HAIFA-REFINEMENT-T72
title: "AI průvodce: nové vlákno přebírá harness, model a thinking z kontextu obrazovky"
status: todo
workflow: plan-build-test
depends_on: [HAIFA-REFINEMENT-T69]
writes: [aifactory/src/aifactory/web/assistant.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_assistant.py]
---

## Zadání
Cíl: vlákno AI průvodce založené v kontextu repa nebo tasku poběží se stejným harnessem, modelem a thinking jako task, případně repo. Bez kontextu (stránka Přehled) poběží s výchozím nastavením počítače z topbaru (harnesses.json).

Dnes `AssistantManager.create` v `aifactory/src/aifactory/web/assistant.py` bere vždy `harness_settings.effective_override({}, None)` a přijímá jen `{title}`.

Co udělat:
- `POST /api/assistant/threads` (`assistant_create` v `aifactory/src/aifactory/web/app.py`) přijme volitelné `screen: {repo?, task?, run?}` ve stejném tvaru jako u zprávy (`ScreenContext`). Neznámé klíče a neznámé repo vrátí `usage_error`.
- U `task` (a u `run`, přes jeho task) se binding spočítá funkcí z HAIFA-REFINEMENT-T69 nad backlogem repa z registru. U samotného `repo` a bez kontextu se použijí výchozí hodnoty počítače. Bez nastavení počítače platí dnešní `guide_defaults()`.
- Omezení průvodce zůstává: harness mimo `GUIDE_HARNESSES` dál přechází na `claude_fallback`. Vlákno si harness, model a thinking uloží jako dnes a další zprávy pokračují ve stejné session.
- Aktualizovat docstringy modulu `assistant.py` a route.

Mimo rozsah: frontend (HAIFA-REFINEMENT-T73).

Hotovo znamená:
- `aifactory/tests/web/test_web_assistant.py` ověřuje: vlákno s `screen.task` tasku v projektu s `harness: codex` (model, thinking) má tento harness, model a thinking. Bez `screen` má výchozí harness počítače. Harness, který průvodce nesmí, přejde na claude jako dnes. Neplatný `screen` vrátí `usage_error`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
