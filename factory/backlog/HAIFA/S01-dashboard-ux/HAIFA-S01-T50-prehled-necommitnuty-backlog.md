---
id: HAIFA-S01-T50
title: "Přehled: indikovat necommitnutý backlog každého repozitáře"
status: todo
depends_on: []
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Na Přehledu chybí informace o necommitnutém backlogu. Existující čip v App.vue je dostupný jen uvnitř repozitáře; overview.py a lib/overview.ts nyní hlásí necommitnutou konfiguraci. Doplnit samostatnou indikaci backlogu přímo u příslušného repozitáře.

Akceptace:
- U změněného backlogu zobrazit srozumitelnou indikaci s počtem změněných souborů a odkazem do backlogu daného repozitáře, kde je stávající možnost commitu. Rozlišit ji od necommitnuté konfigurace. Žádný automatický commit ani nová implementace commitování.
- Indikace je viditelná v obou režimech Přehledu, i u repozitáře bez běžících tasků a při skrytí dokončených projektů; patří repozitáři a neopakuje se pro každý projekt.
- Použít stejnou definici změny jako web.backlog.status / backlog_changes vůči base: staged, unstaged, nové i smazané soubory backlogu. Změna mimo backlog indikaci nezpůsobí. Nepoužít souhrnný git dirty jako náhradu.
- Indikace se aktualizuje po změně a commitu bez reloadu stránky v rámci existujícího obnovování. Rozlišit čistý stav, načítání a chybu čtení; neznámý stav nesmí vypadat jako potvrzeně čistý. Pomalý repozitář neblokuje ostatní.
- Čtení Přehledu zůstává bez zápisů, fetch/pull a síťových Git operací; nepřidávat dotaz na každý projekt ani nezávislou polling smyčku. Zachovat současné loading/timeout chování a cache.

Testy: clean/dirty a přechod po commitu, různé typy změn, změna mimo backlog, chyba čtení a izolace dvou repozitářů; UI v aktivní kartě i klidném řádku a režimu Po projektech. Kandidáti: tests/web/test_web_overview.py, OverviewView.test.ts, RepoCard.test.ts, lib/overview.test.ts a relevantní browser test Přehledu.

Ověření: vyhledat přímé volající v celém aifactory/tests/ a zvolit jen testy dotčeného chování. Spustit každý změněný testovací soubor, just lint, just typecheck, just web-test, just web-build a příslušné browser testy změněných obrazovek podle AGENTS.md. Testy bez živých modelů a služeb, s izolovaným HAIFA_HOME; nespouštět celou sadu v tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
