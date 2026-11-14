---
id: HAIFA-S12-T03
title: GIRO — dashboard, dokumentace, demo a skilly
status: todo
depends_on: [HAIFA-S12-T02]
writes: [aifactory/, giro/, README.md, AGENTS.md, CLAUDE.md, docs/, justfile]
---

## Zadání

Sjednoť uživatelskou identitu na GIRO podle T01. Zahrň Vue dashboard,
HTML title a metadata, existující ikony/slovní značku, onboarding, průvodce,
diagnostické texty, ukázkové repo, README, příručku, agentní instrukce,
generovaný `--skill`, seedy a frontendová package metadata.

Hotovo znamená:
- Nový uživatel vidí GIRO a tam, kde dává smysl, `Goal in. Release out.`.
  Aktivní texty neprezentují produkt jako Helios AI Factory ani jako produkt
  zaměstnavatele. Nejde o plošný redesign obrazovek nebo změnu workflow.
- Příklady používají `giro`; staré `factory`, HAIFA proměnné a cesty jsou jasně
  označené jako kompatibilita. Návody pro instalaci/upgrade/uninstall odpovídají
  GIRO bundlu z T02 a přechodu přes poslední HAIFA s alertem z T04.
- Alert „HAIFA se přejmenovává na GIRO“ je pouze v poslední HAIFA; po úspěšném
  přechodu se v GIRO nezobrazuje. Běžné GIRO aktualizace používají nové repo.
- Seed a generovaný skill obsahují stejné názvy; uživatelské úpravy knihovny
  se při refreshi nesmějí ztratit. Při změně storage klíčů se zachovají preference.
- Dokumentace rozlišuje cílové GIRO URL od zatím aktivních HAIFA URL; před T06
  nevydávej neexistující cílovou adresu jako funkční instalační zdroj.
- Historické backlogy, zápisy běhů, odkazy na stará PR, copyrighty,
  `THIRD_PARTY_NOTICES` a převzatý vendor kód zůstanou věcně správné.
- Zbývající aktivní HAIFA/Helios výskyty jsou vysvětleny v mapě T01; přibalený
  statický frontend se regeneruje pomocí `just web-build`.

Ověření: společné kontroly stepu, `just web-test`, cílené guide/skill/demo testy
a browserové kontroly skutečně změněných obrazovek. Vizuálně ověř titulek,
hlavní značku a onboarding. Nezaváděj test zakazující historická slova všude.

## Běhy
<!-- doplňuje factory při schválení PR -->
