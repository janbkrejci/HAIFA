---
id: HAIFA-S09-T02
title: "E2E: Azure repo s povinným schválením, auto approve, auto-continue a úklid"
status: done
archived: true
depends_on: [HAIFA-S90-T04]
---

## Zadání
End-to-end ověření na skutečném Azure DevOps. Repo, kde do base vede cesta jen přes pull request a PR vyžaduje aspoň jednoho schvalovatele, musí s HAIFA projít bez člověka: vlastní schválení, merge, změny base i auto-continue řetězu tasků. Na konci se dočasné repo na Azure smaže.

Prostředí: organizace https://asolcz.visualstudio.com, projekt NEO_HEF, přihlášené `az` s rozšířením azure-devops (viz HAIFA-S09-T01). Produkční repo NEO_HEF ani HAIFA-Azure-Sandbox se nemění.

Scénář:
1. Založit dočasné repo s jedinečným názvem (např. `HAIFA-E2E-<datum>-<n>`), s base `main` a počátečním commitem.
2. Na `main` nastavit politiku: minimálně 1 schvalovatel, autor smí schválit vlastní změny (`creatorVoteCounts`). Ověřit, že přímý push do `main` je odmítnutý.
3. Naklonovat repo do dočasného adresáře a přidat ho do HAIFA s `base_changes: pr` a `base_pr_merge: auto` (`factory init --commit --base-changes pr --base-pr-merge auto` nebo `POST /api/repos`). Ověřit, že instalace prošla PR `factory-init/<n>`, factory ho sama schválila a mergnula a lokální `main` ho obsahuje.
4. Založit backlog se dvěma závislými tasky s `auto_continue` a `auto_merge` a commitnout ho (`factory backlog commit`). Ověřit, že šel PR `factory-backlog/<n>` a byl automaticky mergnut.
5. Spustit řetěz s `--auto` přes jednoduchý levný workflow nebo falešný harness, pokud stačí. Ověřit, že každý task má PR, factory ho schválila vlastním hlasem (`reviewed: true`), PR se mergnul přes politiku bez bypassu a druhý task se spustil sám.
6. Ověřit, že stav backlogu (`status: done`, běhy) a lokální `main` odpovídají remote.
7. Úklid ve `finally`, i když scénář selže: smazat dočasné repo na Azure (`az repos delete`), jeho politiky a lokální klon a odregistrovat ho z dashboardu. Výsledek úklidu zapsat do výstupu.

Hotovo, když:
- scénář je spustitelný jedním příkazem pro operátora (např. jako scénář v `aifactory/validation/` nebo `just` recept), neběží v CI a bez přihlášeného `az` skončí srozumitelnou chybou bez zásahu do Azure,
- výsledek uloží přehled kroků s URL PR, hlasy a SHA a jasné ok/selhání,
- po běhu (úspěšném i neúspěšném) na Azure nezůstane dočasné repo ani politika,
- nalezené chyby HAIFA jsou opravené nebo zapsané jako další tasky.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/113 · náklady $5.75
