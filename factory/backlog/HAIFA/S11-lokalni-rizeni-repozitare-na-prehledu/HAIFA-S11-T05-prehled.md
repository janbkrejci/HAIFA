---
id: HAIFA-S11-T05
title: Ovládání automatizací a harnessu na Přehledu
status: todo
depends_on: [HAIFA-S11-T04]
writes: [aifactory/]
test_timeout: 1200
---

## Zadání

Přidat repo API pro čtení a patch místních voleb přes službu T01 a propojit s web/overview.py, app.py a Vue OverviewView/RepoCard/RepoControls. Každá karta repo nabízí auto merge, auto continue a výchozí harness z místního katalogu. Označení „Na tomto počítači“ a při off „Aktuální běhy doběhnou, další se nespustí“. Uložit ihned bez commit/apply workflow; UI zobrazí potvrzený stav, ukládání a chybu, při neúspěchu neprezentuje off jako účinné. Souběžné změny záložek nesmějí ztratit jiná pole.

Odstranit aktivní editaci těchto provozních voleb z backlogových formulářů/detailů a stromu; legacy hodnoty mohou být read-only v přechodovém vysvětlení. Neodstranit kanbanové vyloučení tasků, samostatné nastavení modelů stroje ani jednorázový RunDialog override. Nabídnout převzetí starých voleb s náhledem přes T06; pokud API importu ještě není hotové, nedodat nefunkční tlačítko. Ukázat, že ovladače platí pouze pro novou Factory na tomto počítači.

Hotovo: změna z Přehledu se okamžitě projeví v běžícím novém workeru, vydrží reload/restart, nezmění Git ani druhou repo; nedostupná repo/harness a chyba zápisu jsou čitelné. Přístupné popisky a ovládání klávesnicí. Testy backendu web/test_web_overview.py, test_web_runs.py a dotčených backlog endpointů; Vue testy změněných komponent. just web-test, just web-build a browser scénář Přehledu v tests/e2e/test_multi_repo_browser.py; při změně Backlogu relevantní test_f3_browser.py. Každý upravený browser soubor spustit -n0. Ověřit off během aktivního běhu s falešným workerem.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->

