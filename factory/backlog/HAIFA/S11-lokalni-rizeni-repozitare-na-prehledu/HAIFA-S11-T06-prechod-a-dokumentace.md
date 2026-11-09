---
id: HAIFA-S11-T06
title: Převzetí legacy voleb a ověření soužití verzí
status: todo
depends_on: [HAIFA-S11-T05]
writes: [aifactory/, docs/, README.md]
test_timeout: 1200
---

## Zadání

Dokončit přechod popsaný v indexu. CLI/API a Přehled nabídnou explicitní náhled legacy effective hodnot přes task/step/project a lokální import. Jednotné hodnoty lze nabídnout k převzetí, u rozdílných voleb vyžadovat konkrétní rozhodnutí pro repo; žádné any(true), nearest project ani tichý import při read/upgrade. Existující lokální volby bez výslovného přepsání zachovat. Import je idempotentní, atomický a píše pouze do HAIFA_HOME.

Parser/serializace a task edit/add, follow-up, approve/sync, demo a generování návrhu backlogu musí fungovat bez těchto klíčů a zachovat existující legacy klíče. Nové generátory je nevkládají jako požadavek; neprovádět hromadný cleanup současného backlogu. Staré CLI příkazy backlog auto-continue/auto-merge a task edit --auto-merge nesmějí v nové verzi předstírat účinnou provozní změnu: vrátit deprekační chybu s konkrétní lokální alternativou; legacy čtení zachovat. Zkontrolovat všechna zbývající čtení effective(auto_*) a harness_values, rozlišit metadata od runtime.

Otestovat matici: starý backlog + nový runtime bez lokálního záznamu, s on/off, po importu a po git pull se změněnými legacy hodnotami; nový backlog bez klíčů; dvě HAIFA_HOME nad stejným repem; restart a návrat ke staré verzi. Historický parser/fixture poslední předchozí verze musí stále načíst zachovaný backlog; nové editace nesmějí měnit jeho existující provozní hodnoty. Test bez instalace živých služeb nebo modelů. Ověřit, že downgrade místní záznam nepoškodí a má opět starou sémantiku.

Aktualizovat docs/decisions.md, uživatelskou příručku, CLI help a zdroj generovaného factory skillu. Popsat vypnuté výchozí hodnoty, ruční převzetí, zastavení/doběhnutí starých řetězů před upgrade a restart dashboardu/workerů. Výslovně uvést, že nové off neovládá starý proces, jinou instalaci ani starou verzi po rollbacku. Bez povinného commitu a bez min-version bariéry během soužití; budoucí odstranění legacy polí zůstává mimo scope.

Kandidáti testů: backlog/test_backlog_auto_continue.py, test_backlog_auto_merge.py, test_backlog_container_edit.py, test_task_follow_up.py, workflow/test_workflow_cli.py podle změn seed/generátorů, test_skill.py, demo/test_demo_try.py a nové kompatibilitní fixture testy. Dotčené UI ověřit just web-test/web-build a relevantním browser testem Přehledu. Zopakovat vybrané integrační scénáře off a kompatibility z T02–T05, nikoli celou sadu. Hotovo znamená úplnou funkci připravenou k jednomu vydání, žádné runtime rozhodnutí založené na legacy automatizacích.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->

