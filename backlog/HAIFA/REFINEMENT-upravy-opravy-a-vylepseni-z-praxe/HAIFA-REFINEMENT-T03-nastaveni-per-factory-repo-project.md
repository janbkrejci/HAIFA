---
id: HAIFA-REFINEMENT-T03
title: Nastavení per factory/repo/project
status: done
depends_on: []
related: [HAIFA-S03-T03, HAIFA-S03-T04, HAIFA-S03-T05, HAIFA-S03-T07]
writes: [aifactory/src/aifactory/config/, aifactory/src/aifactory/backlog/, aifactory/src/aifactory/run/, aifactory/src/aifactory/web/settings.py, aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/static/, "aifactory/web/src/views/SettingsView*", aifactory/web/src/components/settings/, "aifactory/web/src/lib/settings*", "aifactory/web/src/lib/backlog*", aifactory/web/src/test/settingsFixtures.ts, aifactory/tests/config/, aifactory/tests/backlog/, aifactory/tests/run/, aifactory/tests/web/test_web_settings.py, aifactory/tests/web/test_web_backlog_containers.py, aifactory/tests/onboard/]
---

## Zadání
Cesty k výstupům a pracovní adresář mají mít výchozí nastavení per repository, které jednotlivé projekty v repozitáři mohou doplnit nebo přetížit. Každý repozitář může obsahovat N projektů a jejich nastavení se má commitovat a sdílet v rámci repozitáře.

Stránka Nastavení má rozlišovat tři úrovně:
1. Lokální necommitované nastavení.
2. Sdílené nastavení repozitáře.
3. Sdílené nastavení jednotlivých projektů v repozitáři.

Navázat na existující uložení: lokální nastavení v `.factory/local.yaml`, nastavení repozitáře v `.factory/config.yaml` a projektové hodnoty v projektovém `index.md`. Projekt zde znamená nejvyšší úroveň backlogu. Pro `specs_dir` a `docs_dir` již existuje projektové dědění; využít je a doplnit projektový `workdir` včetně jeho skutečného použití při běhu.

Akceptační kritéria:
- Stránka Nastavení jasně odděluje lokální nastavení, nastavení aktuálního repozitáře a nastavení vybraného projektu. Umožňuje vybírat mezi projekty daného repozitáře.
- U projektových `specs_dir`, `docs_dir` a `workdir` je vidět vlastní hodnota nebo zděděná hodnota včetně původu. Odstranění projektového přetížení obnoví dědění z repozitáře.
- Dva projekty ve stejném repozitáři mohou používat různé adresáře výstupů a pracovní adresáře. Úprava jednoho projektu nezmění nastavení druhého.
- Běh používá účinné adresáře výstupů a účinný pracovní adresář svého projektu uvnitř izolovaného worktree. Cesty zůstávají relativní vůči kořeni repozitáře; změna pracovního adresáře neposune význam `specs_dir`, `docs_dir` ani `writes`.
- Zachovat existující přetížení `specs_dir` a `docs_dir` na úrovni stepu a tasku a stávající ochranu zápisových cest.
- Lokální hodnoty zůstávají necommitované. Nastavení repozitáře a projektů je verzovatelné a po commitu dostupné ostatním uživatelům. UI vysvětluje, že běhy čtou sdílené změny až z base commitu.
- Existující repozitáře bez projektového přetížení zachovají dosavadní nastavení. Neplatné cesty se odmítnou před zápisem nebo spuštěním běhu.
- Regresní testy pokryjí dědění, odstranění přetížení, izolaci dvou projektů, použití pracovního adresáře při běhu a rozlišení tří úrovní v UI. Aktualizovat generované frontendové assets a ověřit `just check-scoped`.

Rozsah této změny tvoří tři uvedené úrovně a nastavení cest. Další projektové parametry nerozšiřovat bez konkrétní potřeby.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/101 · náklady $0.00
