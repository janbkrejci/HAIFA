---
id: HAIFA-S11-T06
title: Převzetí legacy voleb a kompatibilita sdíleného backlogu
status: done
depends_on: [HAIFA-S11-T05]
writes: [aifactory/, docs/, README.md]
test_timeout: 1200
---

## Zadání

Dokončit přechod popsaný v indexu. CLI/API a Přehled nabídnou explicitní náhled legacy effective hodnot přes task/step/project a lokální import. Jednotné hodnoty lze nabídnout k převzetí, u rozdílných voleb vyžadovat konkrétní rozhodnutí pro repo; žádné any(true), nearest project ani tichý import při read/upgrade. Existující lokální volby bez výslovného přepsání zachovat. Import je idempotentní, atomický a píše pouze do HAIFA_HOME.

Parser/serializace a task edit/add, follow-up, approve/sync, demo a generování návrhu backlogu musí fungovat bez těchto klíčů a zachovat existující legacy klíče. Nové generátory je nevkládají jako požadavek; neprovádět hromadný cleanup současného backlogu. Staré CLI příkazy backlog auto-continue/auto-merge a task edit --auto-merge nesmějí v nové verzi předstírat účinnou provozní změnu: vrátit deprekační chybu s konkrétní lokální alternativou; legacy čtení zachovat. Zkontrolovat všechna zbývající čtení effective(auto_*) a harness_values, rozlišit metadata od runtime.

Otestovat matici: starý backlog + nový runtime bez lokálního záznamu, s on/off, po importu a po git pull se změněnými legacy hodnotami; nový backlog bez klíčů; dvě HAIFA_HOME nad stejným repem; persistence po restartu nové verze. Historický parser/fixture poslední předchozí verze musí stále načíst zachovaný backlog pro počítače, které ještě neupgradovaly; nové editace nesmějí měnit jeho existující provozní hodnoty. Test bez instalace živých služeb nebo modelů. Návrat ke staré verzi a souběh či ovládání starých procesů na upgradovaném počítači jsou mimo scope; neimplementovat ani netestovat.

Aktualizovat docs/decisions.md, uživatelskou příručku, CLI help a zdroj generovaného factory skillu. Popsat vypnuté výchozí hodnoty, ruční převzetí a běžný restart již spuštěného dashboardu po instalaci nové verze. Vysvětlit jen potřebné rozlišení: neupgradovaný počítač používá frontmattery, upgradovaný místní nastavení. Bez povinného commitu a bez min-version bariéry během přechodu; budoucí odstranění legacy polí zůstává mimo scope.

Kandidáti testů: backlog/test_backlog_auto_continue.py, test_backlog_auto_merge.py, test_backlog_container_edit.py, test_task_follow_up.py, workflow/test_workflow_cli.py podle změn seed/generátorů, test_skill.py, demo/test_demo_try.py a nové kompatibilitní fixture testy. Dotčené UI ověřit just web-test/web-build a relevantním browser testem Přehledu. Zopakovat vybrané integrační scénáře off a kompatibility z T02–T05, nikoli celou sadu. Hotovo znamená úplnou funkci připravenou k jednomu vydání, žádné runtime rozhodnutí založené na legacy automatizacích.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-09 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/210 · náklady $0.00

