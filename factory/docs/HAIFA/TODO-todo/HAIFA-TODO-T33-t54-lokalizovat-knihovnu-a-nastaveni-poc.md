# T54: Knihovna a nastavení počítače v EN/CS

Katalog `setup` pokrývá stránku Knihovna, založení a klonování knihovny,
synchronizaci a pull requesty, import, obnovu výchozích položek, historii,
kopie repozitářů, ignorování položek, kontrolu počítače, port dashboardu a dialog
harnessů. Změna locale překládá otevřené formuláře a potvrzení bez opětovného
načtení dat. Cesty, obsah souborů, názvy, modely, hashe a diagnostika zůstávají daty.

Nálezy a opravy používají stabilní kódy. Původní zpráva a oprava jsou dostupné
v technických detailech; kopírování opravy zachovává původní příkaz.
Chyba portu poskytuje `message_code: port_range` a číselné meze. Test harnessu
poskytuje neutrální `error_code`, zatímco původní diagnostiku zachovává.
Locale se neukládá do backendu ani do sdílené cache a nevstupuje do digestu plánu.

Regresní testy pokrývají přepnutí EN/CS s rozepsaným portem, importní cestou,
pravidlem ignorování a volbami harnessu, otevřenou historickou revizi, překlad
potvrzení a výsledku importu, překlad chyb podle kódů a dva klienty s různými
jazykovými preferencemi nad společnou kontrolou a plánem knihovny.
Browserová očekávání knihovny a přesunu kopie odpovídají výchozí EN.

Ověření provádí samostatný testovací krok workflow. Jediný pokus builderu o
cílený diagnostický test skončil před spuštěním testu: frontend neměl nainstalovaný
`vitest`. Vydání distribuovaných assetů a globální přepínač jazyka zajišťuje
navazující HAIFA-TODO-T35 podle rozdělení původního T54.
