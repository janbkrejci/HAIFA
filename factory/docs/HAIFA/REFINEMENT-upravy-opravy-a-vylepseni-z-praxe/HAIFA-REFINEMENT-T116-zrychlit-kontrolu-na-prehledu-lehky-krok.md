# Rychlejší kontrola na Přehledu

Readiness používá `GET /api/repos/{id}/factory/roster?summary=1`. Odpověď
`{"agents": počet}` načítá efektivní konfiguraci agentů, ale nevolá `_base_tasks`,
nečte úlohy z base a nesestavuje metadata editoru. Plný roster pro editor nadále
vrací původní strukturu včetně počtů použití workflow.

Dokončená kontrola počítače se uchovává ihned po přijetí odpovědi. Timeout nebo
chyba knihovny, seznamu repozitářů, rosteru či backlogu zobrazí upozornění
„Údaj není k dispozici“ spolu se zjištěními kontroly a časem posledního známého
výsledku. Pozdní odpověď po timeoutu ani starší souběžná kontrola stav nepřepíše.
Timeout samotné kontroly počítače si zachovává původní označení.

Společný `procrun.limit` i čtení gitu v `web/repos.py` odmítnou zbývající rozpočet pod jednu sekundu pomocí
`BudgetExceeded`; takové odmítnutí se nezamění za repozitář bez commitů.
Limit platí pro každý git příkaz uvnitř kontextu, čtení base, commitu a rosteru.
Ostatní sondy si zachovávají původní limity a git bez rozpočtu se nemění.
Registry kontrolují rozpočet také po načtení kontextu a konfigurace: odmítnutí,
které konfigurace převede na chybějící údaj nebo ConfigError, nepřepíše známý stav.
Při timeoutu použijí známé počty pro stále registrované repozitáře. Timeouty
registru a knihovny jsou zachyceny před cestou do `monitoring.once` nebo
`monitoring.periodic`, kde obecná výjimka jinak vytváří stack trace přes
`log.exception`. V tomto checkoutu je původní `run.gitops.read_git` bez limitu;
rozpočet do git příkazů kontextu kontroly přenášejí `config.source` a
`providers.git`. Webový obal nyní respektuje rozpočet i pro ověření HEAD.

Rozpočty zůstávají 60 s pro kontrolu, 10 s pro registr a 10 s pro samostatné
obnovení knihovny z cache. Čerstvá kontrola s registrem a dvousekundovou rezervou
pro předání výsledku má 72 s proti klientským 75 s. Obnovení knihovny při čtení
cache neběží navíc za čerstvou kontrolou. Windows pod skutečnou souběžnou zátěží
nebyl měřen; místo nepodloženého zvýšení limitů je vyčerpání rozpočtu ošetřeno
degradací na známý stav. Regrese používají falešné funkce a virtuální čas.

Přímé volající byly hledány v celém `aifactory/tests/` a webových testech.
Změněné chování pokrývají `test_procrun.py`, `test_web_machine.py`, `test_web_repos.py`,
`test_web_factory_roster.py`, `OverviewReadiness.test.ts`, `App.test.ts` a
`test_machine_check_browser.py`. Plný roster dále používají testy editoru
`RosterEditor.test.ts`, `FactoryView.test.ts` a test vlastního agenta
v `test_web_factory.py`. CLI `factory check` ani obsah kontrol se nemění.

Diagnostický běh `bun run test src/components/OverviewReadiness.test.ts` prošel
se 33 testy. Kompletní ověření změny patří samostatné testovací fázi workflow:
lint, typecheck, webové testy, všechny editované backendové testovací soubory
a celý editovaný browser soubor s `-n0`.
