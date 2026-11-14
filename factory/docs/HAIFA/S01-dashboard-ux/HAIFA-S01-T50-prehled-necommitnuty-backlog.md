# Necommitnutý backlog na Přehledu

Přehled zobrazuje u každého repozitáře samostatný odkaz „Necommitnutý backlog“ s počtem změněných souborů. Odkaz vede do Backlogu daného repozitáře se stávající možností commitu. Indikace se zobrazuje jednou u repozitáře v aktivní kartě i klidném řádku a v obou režimech seskupení, nezávisle na projektech.

API `/api/overview` vrací `backlog` se stavem `clean`, `dirty`, `loading` nebo `error`, počtem `count` a případným detailem `error`. Čistý stav nemá indikaci. Chyba nebo chybějící údaj zobrazí neznámý stav; timeout zachovává stávající načítací kartu repozitáře.

Čtení používá `web.backlog.status`, tedy stejné změny vůči base jako obrazovka Backlog: staged, unstaged, nové i smazané soubory v nakonfigurovaných kořenech backlogu. Změny mimo backlog indikaci neovlivní. Samostatná dvousekundová cache se obnovuje při existujícím pollingu Přehledu; cache konfigurace a tasků zůstávají zachovány. Čtení nemění soubory ani Git index, nespouští fetch/pull ani commit. Pomalé čtení podléhá stávajícímu timeoutu a izolaci repozitářů.

Regresní pokrytí je v `test_web_overview.py`, `OverviewView.test.ts`, `RepoCard.test.ts`, `lib/overview.test.ts` a browser testu `test_overview_loading_browser.py`. Ověření a vytvoření distribuovaného frontendu provádí samostatný testovací krok workflow.
