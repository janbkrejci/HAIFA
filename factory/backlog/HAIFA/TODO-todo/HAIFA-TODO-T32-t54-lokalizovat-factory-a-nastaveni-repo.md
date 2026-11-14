---
id: HAIFA-TODO-T32
title: "T54: Lokalizovat Factory a nastavení repozitáře"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést instalaci, kontrolu a konfiguraci repozitáře, commit preview, roster, dědičnost, nastavení a lekce do EN/CS. Zachovat API enumy a konfiguraci. Backendové popisky řešit explicitními kódy/parametry nebo locale požadavku bez globálního přepínání serveru. Ověřit zachování rozepsaných nastavení a aktualizovat testy.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: FactoryView, SettingsForm, správa agentů a lekce dosud nejsou migrovány.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
