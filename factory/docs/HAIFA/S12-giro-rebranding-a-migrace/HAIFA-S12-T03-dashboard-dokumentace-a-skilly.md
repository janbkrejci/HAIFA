# GIRO — dashboard, dokumentace, demo a skilly

Dashboard zobrazuje slovní značku `giro`, titulky GIRO a slogan
`Goal in. Release out.` v přístupném názvu a tooltipu. Třípruhová ikona
zůstává převzatou značkou se zachovanými licencemi. Navigace, onboarding,
průvodce i diagnostické texty používají GIRO. Frontendové package metadata
jsou `giro-dashboard`; přibalené statiky regeneruje `just web-build`.

README, CS/EN příručka, agentní instrukce, nové demo a validační šablony
používají primární příkaz `giro`. Distribuce a namespace `aifactory`, technické
cesty `.factory/` a `factory/`, knihovna HAIFA-LIBRARY a identita skillu
`skill/factory` zůstávají. Seed i CLI generují stejný GIRO skill. Regrese
nedestruktivního refresh zachovává týmovou úpravu skillu bez druhé položky.

Návody rozlišují dosud aktivní HAIFA releases a cílové GIRO repo po T06.
Popisují přechod přes poslední HAIFA s alertem, zachování záloh, offline
migraci, návrat a uninstall stejné distribuce. Automatický seed chrání úpravy;
explicitní `--take` nebo `--all` představuje vědomé přepsání. Browserové storage
klíče a protokoly průvodce se nemění. Výjimky shrnuje mapa T01 v
`docs/rebranding/giro.md`.

Testy ověřují nové titulky a wordmark, lokalizované názvy, příručku proti CLI,
obsah generovaného skillu a zachování týmové úpravy. Browserové scénáře příručky
a demo onboardingu obsahují kontroly titulků a přístupné značky. Jediná
builderova diagnostika příručky odhalila chybný název tlačítka a překročení
limitu délky; obě příčiny byly opraveny bez zvyšování limitu. Úplné ověření
provádí samostatný testovací krok.

Po testovacím kroku byly opraveny zbývající staré texty v očekáváních testů,
formátování browserových kontrol a přepínání obou home aliasů v knihovním
helperu. Veřejné kotvy úvodu a konfigurace zůstávají historickými URL v obou
jazycích a mají explicitní regresi. Bundle opět generuje INSTALL.md ze stejné
instalační kapitoly jako dashboard; test ověřuje GIRO příkazy, kompatibilní
HAIFA bundle i uninstall distribuce aifactory. Tím se odstraňuje druhý,
neúplný instalační text. Příklady haifa-H.zip se neverzují číslem GIRO.

Review oprava zachovává skutečný výchozí docs_root `factory` v CS/EN příručce,
v popisu backlogu i u --docs-root ve skillu. Nové regrese porovnávají tyto
údaje přímo s ProjectSettings. Vizuální inspekce skutečných přibalených statik
na desktopu EN a mobilu CS potvrdila značku, titulky a vstupy do onboardingu;
snímky a posouzení jsou v handoff artefaktech T03-visual-*. Nefunkční direktivu
sloganu nahradila sdílená komponenta Tooltip, s regresí focusu. Statiky byly
znovu sestaveny příkazem just web-build.
