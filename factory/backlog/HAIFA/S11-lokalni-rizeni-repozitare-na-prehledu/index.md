---
id: HAIFA-S11
title: Lokální řízení repozitáře na Přehledu
---

## Cíl a rozhodnutí pro implementaci

Auto merge, auto continue a výchozí harness jsou provozní volby pro dvojici místní instalace / repozitář. Ovládají se na kartě repozitáře na Přehledu a ukládají mimo Git do HAIFA_HOME. CLI i dashboard používají stejnou službu, také bez registrace repozitáře v dashboardu. Worktree sdílí identitu hlavního checkoutu; jiný klon ani jiný počítač volby nepřebírá. Rozsah odpovídá uživateli služby a jeho HAIFA_HOME, nikoli všem OS účtům.

Nová instalace má obě automatizace vypnuté a harness dědí z místního nastavení stroje. Žádný tichý import true z backlogu. Přechod nabídne explicitní náhled starých hodnot a jejich převzetí pro celou repo; rozporné hodnoty vyžadují výběr uživatele. Lokální false je konečná hodnota, nikoli pokyn k fallbacku. Zapnutí samo nespouští práci; Spustit továrnu nebo ruční spuštění zahájí běh.

Vypnutí auto continue je bariéra pro další automatické starty. Všechny již přijaté běhy doběhnou; nedoplňují se paralelní sloty ani nevznikají nové automatické retry/heal běhy. Vypnutí nepřerušuje fáze aktuálního běhu a samo nevypíná auto merge. Potvrzení zápisu a přijetí dalšího startu mají společné synchronizační pravidlo, aby mezi kontrolou a spawnem nebyla mezera. Platí i pro řetěz původně spuštěný přes --auto.

Repo přepínač platí pro všechny projekty; nemění dosavadní pořadí fronty, rozsah výběru řetězu, závislosti, kapacitu ani vyloučení v kanbanu. Auto merge nenahrazuje review, CI ani ochrany hostingu. base_pr_merge pro administrační PR je samostatná politika a tato změna ji nepřepíná.

## Přechod mezi verzemi

První kompatibilní release ponechá existující auto_merge, auto_continue a harness/model/thinking v backlogu beze změny a umí je číst jako legacy metadata. Nový runtime pro automatizace nepoužívá frontmatter ani při chybě místního úložiště. Výchozí harness nové verze je místní; stará backlogová volba je dostupná pro náhled/import, nikoli skrytá nadřazená volba. Nové tasky tyto provozní klíče nepotřebují. Parser ani běžná editace, schválení a sync nesmějí staré klíče hromadně odstraňovat či přepisovat.

Přechod znamená různé verze na různých počítačích: kdo ještě neupgradoval, dál používá původní frontmattery; kdo nainstaluje novou Factory, používá místní volby. U již spuštěného dashboardu stačí běžný restart po aktualizaci. Návrat ke staré verzi ani souběh či řízení starých procesů na upgradovaném počítači nejsou požadavkem a nepřidávají se pro ně mechanismy ani testy. Neměnit sdílený formát backlogu ani vynucovat minimum verze během přechodu. Hromadné odstranění legacy klíčů je až samostatně schválený pozdější krok po ukončení podpory starých instalací; není součástí tohoto plánu.

## Provádění a ověřování

T01 vytvoří základ a kontrakt, T02 a T03 napojí automatizace, T04 harness, T05 Přehled, T06 uzavře kompatibilitu a dokumentaci. Dílčí změny vydat uživatelům společně, aby nevznikl release s lokálním přepínačem, který runtime ignoruje.

Každý task má vlastní writes včetně potřebných cest mimo děděné aifactory/ a justfile. Před implementací dohledat přímé volající všech změněných funkcí, modulů, seedů a helperů v celém aifactory/tests/. Vždy just lint a just typecheck; cílené just pytest podle změněného chování a přímých volajících, nikdy celou sadu v task runu. Všechny editované testovací soubory spustit. Pro změny webu just web-test a just web-build; browser test jen změněné obrazovky přes just pytest tests/e2e/<soubor> -n0. Testy bez živých modelů a služeb, souběhy deterministicky pomocí bariér. Konkrétní kandidáti testů jsou v úkolech; vybrat relevantní případy, ne celé adresáře pouze kvůli importům. Limity nastavit podle reálného výběru s rezervou; při překročení rozdělit task před spuštěním.
