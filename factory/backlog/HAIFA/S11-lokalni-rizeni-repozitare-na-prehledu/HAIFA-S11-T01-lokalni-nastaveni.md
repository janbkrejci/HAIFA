---
id: HAIFA-S11-T01
title: Místní nastavení repozitáře a kompatibilní kontrakt
status: done
depends_on: []
writes: [aifactory/, docs/decisions.md]
test_timeout: 1200
---

## Zadání

Zavést sdílenou službu pro lokální auto_merge, auto_continue a harness podle rozhodnutí v indexu tohoto stepu. Vyjít z home.py, harness/settings.py, web/registry.py a run/gitops.py; runtime nesmí záviset na web registry. Uložit verzovaný záznam mimo repo v HAIFA_HOME, identita podle kanonické hlavní repo/common Git dir (Windows case a worktrees), nikoli remote URL nebo ID dashboardu. Popsat chování při přesunu/odstranění klonu. Read nesmí samovolně migrovat či zapisovat.

Implementovat validovaný read/update a CLI show/set v jednotném JSON envelope, atomický zápis a zámek mezi procesy, ochranu proti ztracené změně různých polí. Navrhnout společnou bariéru pro změnu auto_continue a přijetí automatického startu pro T02. Chybějící nastavení znamená false/false a místní výchozí harness; poškozený záznam neobnoví legacy true ani starou cache umožňující start. Explicitní false nikdy není fallback. Neznámou verzi nepřepsat, chybu zpřístupnit.

Zapsat kontrakt a precedence do docs/decisions.md. Hotovo znamená stejná data pro CLI/dashboard/worker, oddělené klony a HAIFA_HOME, sdílení worktrees, žádný Git diff při set a persistence po restartu. Testovat chybějící i vadný soubor, neplatný typ/verzi/harness, souběžný zápis a selhání uložení. Kandidáti: nové testy lokální služby a CLI, relevantní testy harness/test_harness_settings.py a web/test_web_registry.py jen při změně jejich chování. Společný testovací postup je v indexu.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-09 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/205 · náklady $0.00

