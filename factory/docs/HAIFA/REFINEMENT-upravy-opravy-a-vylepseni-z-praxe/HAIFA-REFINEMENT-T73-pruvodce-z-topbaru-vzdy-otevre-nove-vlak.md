# T73 — Otevírání AI průvodce

Tlačítko v topbaru při otevření zavřeného panelu vždy ukáže nové prázdné vlákno. Stejně funguje explicitní `setOpen(true)`. Vlákno se uloží až při první zprávě; otevření panelu samo nic nezakládá. Starší konverzace jsou dostupné přes seznam vláken.

Reload stránky s otevřeným panelem jednorázově obnoví vybrané vlákno ze sessionStorage, včetně streamování probíhající odpovědi. Reload se zavřeným panelem konverzaci nenačítá. Navigace mezi obrazovkami zachová otevřenou konverzaci. Opožděné načtení staršího vlákna nepřepíše nově otevřený prázdný panel ani jej nenechá ve stavu načítání.

První zpráva předává do vytvoření vlákna i odeslání zprávy stejný efektivní `screen`, který panel zobrazuje jako chip. Na Přehledu a po odebrání chipu se `screen` vynechá; backend tak použije výchozí nastavení počítače. Další zprávy znovu vlákno nezakládají. Harness, model a thinking vybírá backend; klient zobrazuje uložené hodnoty vlákna v hlavičce i historii. Chybějící nebo null thinking nepřidává prázdný oddělovač.

Aktuální backend ukládá thinking do vlákna, ale `Thread.summary()` ani odvozený `detail()` jej nevracejí klientovi. Popisek proto v tomto checkoutu zůstává bez thinking; frontend je připravený na jeho přítomnost v API a Vitest ověřuje obě varianty. Browser test porovnává popisek se skutečným bindingem odpovědi API. Backend se v T73 nemění.

## Ověření

- Cílené běhy Vitest pro `assistant.test.ts`, `AssistantPanel.test.ts` a `App.test.ts` ověřily 28 testů knihovny, 18 testů panelu a 35 integračních scénářů App; upravený scénář topbaru prošel po opravě simulace submitu samostatně.
- `just web-build`: úspěšný návratový kód, včetně `vue-tsc --noEmit`; statický frontend přegenerován.
- Browser: původní běh souboru ověřil oba scénáře akcí; upravený `test_assistant_conversation_browser` následně prošel samostatně (1 passed). Pokrývá reload, nové otevření z topbaru, historii a POST threads s repo i task kontextem.
- Ruff check a format check pouze pro změněný browser soubor: úspěšné.
- Cílené mypy: `MYPYPATH=tests:tests/run:tests/e2e:tests/workflow uv run mypy --follow-imports=silent tests/e2e/test_assistant_browser.py` úspěšné. Cesty odpovídají helperům, které test importuje.
- Očekávání selektorů, sessionStorage a obnovy byla vyhledána pomocí `rg` a upravena.

V builder fázi byly dle omezení role spuštěny cílené testy; kompletní `just web-test`, `just lint` a `just typecheck` náleží testovací fázi workflow.
