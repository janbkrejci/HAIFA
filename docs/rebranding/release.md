# Poslední HAIFA a přechod na GIRO

Podporovaná cesta je pouze **stará HAIFA → poslední HAIFA H → kliknutí v dashboardu
→ GIRO G z nového repo**. H zůstává HAIFA, včetně CLI, vzhledu, distribučního jména
`aifactory` a jediného assetu `haifa-H.zip` s kořenem `haifa-H/`. G má jediný
`giro-G.zip` s kořenem `giro-G/`. Wheel zůstává podle T01
`aifactory-G-py3-none-any.whl`; wheel nazvaný `giro` se odmítá. Obě vydání mají
constraints, instalátory, licence a SHA256SUMS ve stejném dosavadním formátu.
Nevydávají se další kompatibilní názvy assetů.

## Zdroje, pořadí a identifikace uchovaného zdroje

Původní updater hledá H na `janbkrejci/HAIFA/releases/latest`. Globální alert
„HAIFA se přejmenovává na GIRO“ / „Klikněte zde pro přechod“ (také anglicky)
volá `POST /api/updates/migrate`. Až tento požadavek hledá stabilní G na pevně
určeném `janbkrejci/GIRO/releases/latest`; ignoruje HAIFA_UPDATE_REPO. Běžné
načtení dashboardu GIRO nestahuje ani neinstaluje. Starý update chip nadále
instaluje pouze HAIFA. Další aktualizace běžící GIRO řady 1.x již vybírají GIRO ZIP
z nového defaultního repo. Legacy override přesně `janbkrejci/HAIFA` se pro GIRO
nepoužije, ostatní firemní override a explicitní GIRO_UPDATE_REPO se respektují.
T02 doplňuje jednotný resolver včetně diagnostiky původu nastavení podle T01.

Verze H je `0.1.N`, vyšší než předchozí publikovaná HAIFA. G je `1.0.M`, kde M
je run number nového repo. Číslování se neporovnává pouze podle poslední složky:
`1.0.1 > 0.1.99999`; stejná nebo nižší verze neprojde. Přechod vyžaduje stabilní
GIRO 1.x a odmítá verzi pod min_factory_version knihovny.

Uchovávaný zdroj je výsledný ověřený commit **HAIFA-S12-T04**, před T02/T03,
včetně statik vytvořených `just web-build`. Výchozí commit implementačního běhu
byl `93518ead08d3c85089b1f907c9219460e454a272`; není to hotový přechodový zdroj.
Workflow vytváří finální commit až po builderově reportu a test kroku. Jeho přesný
SHA se z výsledku tohoto tasku zapíše do cutover evidence a repo proměnné
`HAIFA_TRANSITION_SHA`; stabilní tag **`haifa-transition-source`** musí ukazovat
právě na tento SHA. T05/T06 nesmějí vybrat pozdější rebrandingový main. Identita
se ověřuje současně přes SHA v cutover evidenci, repo proměnnou, tag a SHA události
v CI. Builder tag ani commit nezakládá. Bez vyplněného přesného SHA gate nepovolí
publikaci. Tester musí ponechat generované statiky ve výsledném task commitu;
před uchováním zdroje se ověří browser scénář proti těmto statikám.

T06 nejprve publikuje a ověří G ze skutečného GIRO zdroje, včetně checksumů,
instalace a restartu. Teprve potom povolí poslední H. Tento dokument a zdrojová
příprava nepředstavují již existující GIRO release ani provedený cutover.

## Publikační gate poslední HAIFA

`.github/workflows/ci.yml` již nemá push trigger. Spouští se pouze ručním dispatch
z `refs/tags/haifa-transition-source` na veřejném `janbkrejci/HAIFA`. Vyžaduje
přesnou shodu `github.sha` s `HAIFA_TRANSITION_SHA` a explicitní repo proměnnou
`HAIFA_TRANSITION_PUBLISHED=false`. Prázdná hodnota znamená zamítnutí. Checkout
používá schválený SHA, nikoli main. Stejná kontrola běží před buildem i těsně před
publikací, včetně existence stabilního GIRO 1.x s kanonickým GIRO assetem,
monotónní HAIFA verze a nepřítomnosti tagu `haifa-transition-published`.

Před vytvořením release workflow atomicky publikuje tag
`haifa-transition-published` na schválený SHA. Ten znemožní další dispatch
publikovat nové H, i kdyby se změnil run number nebo někdo znovu nastavil boolean
proměnnou. Concurrency všech dispatchů je společná, bez rušení probíhajícího běhu.
Po vydání T06 nastaví `HAIFA_TRANSITION_PUBLISHED=true` a zachová oba tagy.
Pokud publikace po vytvoření pojistného tagu selže, T06 dokončí **totéž** H a jeho
draft podle logu; tag se nemaže a neopakuje se publikace s novou verzí. Ochranu
tagů a proměnných nastaví provozní cutover. Rebrandingové commity ve starém main
nevydávají nic. GIRO release workflow v novém repo je samostatný zdroj T02/T06.

## Kliknutí, záloha a restart

Akce používá tentýž objekt Updates a tentýž write guard jako normální update.
Aktivní tasky se kontrolují před i po čtení release. Dvojí kliknutí ani další
zápisy za upgradu neprojdou. EN/CS UI ukazuje čekání, probíhající instalaci a
opakování; původní technická chyba zůstává v rozbalitelných podrobnostech.

Koordinátor ověří přesnou URL/release/ZIP kořen, SHA256SUMS, metadata aifactory
wheelu a cílovou verzi existujícím `run_upgrade`. Před změnou uchová i ověřený H
bundle pro návrat. Vedle home vytvoří privátní
`<home>.pre-giro-<UTC>-<id>/` s kopií původního tool prostředí a plánem. Sdílený
migrační zámek serializuje přípravu a start CLI/dashboardů. Živé procesní leases
ostatních posledních HAIFA znamenají čekání. Poslední HAIFA odmítá CLI start a
webové zápisy nad prepared i committed markerem `giro-migration.json`.

Dashboard předá řízení kopii svého Python prostředí a skončí. Koordinátor počká
na jeho konec (na Windows také na jeho factory/giro launcher, nikoli shell).
Teprve bez původního procesu zálohuje celý home, včetně env, knihovního `.git`,
dirty/untracked dat a historie, externí knihovnu a u všech registrací celé
`.factory/`, případnou externí trace DB a journal `<git-common-dir>/haifa`.
SQLite kopíruje backup API s integrity checkem. Záloha a manifest mají kontrolní
součty. Soubory `-wal`/`-shm` se vynechávají pouze vedle rozpoznané SQLite databáze,
jejíž obsah zahrne backup API; obyčejné soubory a adresáře s těmito koncovkami
zůstávají zachované. Sdílený DB server, nečitelná konfigurace, nedostupná registrace, neověřené
symlinky či nemožnost vytvořit zálohu znamenají bezpečné odmítnutí.

Při explicitním HAIFA_HOME zůstává cílový home stejný. U defaultu se připraví
ověřený staging a atomicky zveřejní sousední `giro`; již existující cíl se odmítá.
Obě env jména v novém procesu míří na stejný cíl. T02 navazuje resolverem defaultů
na manifest zdroje/cíle. GIRO může prepared cíl otevřít jen s ID tohoto předání;
webové zápisy a background monitoring čekají na commit. Koordinátor instaluje
jediným stávajícím `run_upgrade`, s vypnutým destruktivním refresh knihovny.
Knihovna se zachová přesně; uživatel v GIRO použije nedestruktivní seed plán.

Restart zachovává původní argv, host a port; `factory` alias stejné instalace
zůstává dle T01 platný. Nové API musí do 60 sekund potvrdit `giro-dashboard`,
přesnou G verzi, cílový home a shodná ID/cesty/názvy registrovaných repozitářů.
Až pak koordinátor zapíše committed do obou home i uchovaného plánu. Prohlížeč
sleduje restart a znovu načte UI na témže origin; GIRO alert nezobrazuje. Locale,
rozpracované formuláře a ostatní storage klíče se nepřejmenovávají.

## Návrat a opakování

Chyba sítě, chybějící release, neplatný hash/ZIP/wheel nebo chyba přípravy
neinstaluje nic. HAIFA ukáže konkrétní diagnostiku a tlačítko lze znovu použít.
Po chybě instalace nebo ověření restartu koordinátor zastaví pouze vlastní nový
proces, uchová jeho data, obnoví kompletní původní sadu a ověřený H software,
a spustí HAIFA na původní adrese. Uchování chybného stavu podporuje také externí
knihovnu, repozitář či tool na jiném disku: přesun při rozdílném filesystému
přejde na kopírování a odstranění zdroje až po dokončení kopie.
Pokud uv selže i při návratu, použije ověřenou
kopii původního tool prostředí. HAIFA po startu ukáže uchovanou konkrétní chybu
z `giro-transition-error.json`; nové kliknutí vytvoří nový privátní pokus a
nesmaže starou zálohu. Knihovna se nikdy neseeduje pomocí --all.

Při výpadku stroje nebo neúspěšné obnově zůstávají journal, záloha a `worker.log`
pro kontrolovanou obnovu. Připravený plán se znovu nespouští naslepo. Po zastavení
všech zapisujících procesů se ověří bundle_hashes, data_hashes a tool_hashes
z plan.json; zachová se i současný stav. Každá položka `paths[i]` se obnoví
ze zálohy `data/i` na původní absolutní cestu, software z ověřeného H bundlu
nebo `tool` na `tool_source`. Nový cílový home se uchová odděleně, neslučuje se.
Marker se odstraní z obnovené původní sady až při obnově a ověření HAIFA.
Pokud neprojde ani health HAIFA, koordinátor vrátí blokující marker a vyžaduje
kontrolu zachované zálohy. Zálohy se automaticky nemažou.

Procesy **starší než H** tento protokol neznají: před přechodem musí být ukončeny,
stejně jako nezávislí zapisující klienti externí DB. Neznámý nebo neověřitelný stav
není souhlas s migrací. Celé ověření implementace používá pouze fake hosting,
izolované home/tool adresáře a falešné nástroje; nic se nepublikuje a neupgraduje
na operátorově instalaci. T07 zopakuje skutečnou platformní matici podle T01.
