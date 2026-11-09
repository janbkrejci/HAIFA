---
id: HAIFA-S11-T04
title: Místní výchozí harness pro všechny nové běhy repozitáře
status: done
depends_on: [HAIFA-S11-T03]
writes: [aifactory/]
test_timeout: 1200
---

## Zadání

Napojit místní repo harness na existující katalog/model/thinking v harness/settings.py a sestavení rosteru v run/task.py, retry.py, quota_chain.py a dalších spouštěcích cestách. Výběr na repo platí pro následující běhy včetně automatických členů; nemění rozehraný běh ani existující session při retry. U retry zachovat identitu session a případnou změnu harnessu provést jen explicitní existující cestou.

Stanovit a implementovat precedence: explicitní jednorázový override > lokální repo volba > místní default stroje > roster jako poslední fallback, pokud default není určen. Explicitní workflow step override zůstává zachován a je ve výsledku viditelný. Backlog harness/model/thinking jsou pouze legacy metadata/import; nesmějí potichu přebít lokální volbu. Při přepnutí harnessu nepřenášet model nekompatibilní s novým harness; používat jeho místní model/thinking. Existující quota fallback může dočasně přepnout harness, ale nepřepisuje uloženou volbu; switch-back vychází z lokálního primárního harnessu a ne starého frontmatteru.

Hotovo: změna bez commitu ovlivní další ruční i automatický run, jiné repo se nemění, run zaznamená efektivní harness a původ override. Neplatný/nedostupný/zakázaný harness vrátí srozumitelnou chybu bez tichého běhu na jiném. Kandidáti: harness/test_harness_settings.py, test_harness_override.py, run/test_task_run.py, test_task_run_cli.py, test_quota_chain.py, backlog/test_backlog_harness_values.py. Testovat precedence, explicitní workflow override, další člen řetězu, retry a kvóty bez živých modelů.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-09 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/208 · náklady $0.00

