# Poslední HAIFA — přechodové vydání

Dashboard HAIFA má nad obsahem všech obrazovek EN/CS alert s přímou instalační
akcí. Běžný HAIFA updater zůstává na původním distribučním formátu; přechodové
kliknutí vybírá výhradně stabilní GIRO 1.x z janbkrejci/GIRO. Wheel zůstává
aifactory, veřejný ZIP a kořen jsou giro. Duplicitní kliknutí i aktivní běhy
respektují původní update guard a druhou kontrolu po síťovém požadavku.

Zachované prostředí koordinuje offline zálohu a předání, ale samotnou instalaci
provádí existující run_upgrade. Checksumy/verze se ověřují před změnou; home,
externí knihovna, runtime repozitářů, DB a journal se uchovávají s manifestem.
Prepared/committed marker chrání poslední HAIFA před návratem k zápisům.
Knihovna se nerefreshuje destruktivním seed --all. Chyba instalace či ověření
nového dashboardu obnoví původní sadu a zpřístupní diagnostiku s opakováním.

Publikace je pouze z explicitního uchovaného SHA/tagu, až po dostupném stabilním
GIRO. Jednorázový publikační tag blokuje další HAIFA release i při opakovaném
dispatch. Zdroj poslední HAIFA se uchová před rebrandingem včetně statik;
konkrétní workflow commit/tag a skutečná H/G zaznamená provozní cutover T06.
Podrobnosti: [release postup](../../../../docs/rebranding/release.md).

Builder nepouští samostatný testovací gate ani reálný upgrade. Diagnostický test
pracoval výhradně nad fake hostingem a izolovanými daty; odhalil příliš široký
Popen mock, který blokoval čtení knihovního Gitu. Mock je omezen na supervisor.
Test krok ověří opravený finální kód včetně frontendové sady a browseru proti
znovu sestaveným statikám. Skutečné releasy, změna hostingu a přechod operátorovy
instalace nejsou součástí tohoto implementačního běhu.

Mezikrok runneru dokončil web-build a backendový výběr (209 passed, 9 skipped).
Opravný builder rozdělil dlouhé výrazy, upravil import sdílené pytest fixture
a přímé importy závislostí v testech pro strict mypy. Browser používá stabilní
selektor migračního tlačítka i při změně jeho popisku během instalace; výchozí
lokalizovaný popisek nadále ověřuje samostatně. Jediná cílená EN browser diagnostika
po opravě prošla. Původní frontendový příkaz neměl instalaci závislostí a skončil
před spuštěním Vitestu; finální just web-test zahrnuje bun install a celou sadu.
Tyto dílčí výsledky nenahrazují ověření finálního kódu samostatným test krokem.

Oprava po review zachovává běžné soubory i adresáře s koncovkami -wal/-shm;
vynechávají se jen souborové sidecary vedle rozpoznané SQLite databáze. Regrese
kontrolují jejich přenos do GIRO, uchování v záloze i obnovu při rollbacku a
samostatně skutečný SQLite WAL s potvrzenými daty. Uchování chybného stavu používá
přesun podporující rozdílné filesystémy, také pro externí knihovnu a tool.
Regrese simulují EXDEV i WinError 17 po chybě instalace a restartu a kontrolují
původní externí data, uchovaný chybný stav a restart HAIFA. Jediná builderova
cílená diagnostika varianty restart/EXDEV prošla (1 test). Úplné finální ověření,
včetně povinné celé frontendové sady just web-test, provádí tester/runner.
