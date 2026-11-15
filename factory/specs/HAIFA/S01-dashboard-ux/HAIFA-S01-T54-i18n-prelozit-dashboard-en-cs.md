# T54 — Lokalizace integrované příručky

Tento implementační díl převádí příručku na statický obsah EN/CS nad společným i18n základem T53. Není vydáním kompletní anglické lokalizace dashboardu; globální přepínač je podmíněn dokončením migrace všech obrazovek podle původní akceptace T54.

## Obsah a kompatibilita

České kapitoly zůstávají v kořeni balíčku `aifactory.guide`; anglické překlady jsou v podadresáři `en/` se stejnými názvy souborů a ID kapitol. Všechny kapitoly i veřejné odkazy na sekce existují v obou jazycích. Anglické nadpisy deklarují původní identifikátor komentářem `<!-- section:id -->`; komentář se nezobrazuje ve vykresleném obsahu ani názvech vyhledávání.

Python API příručky přijímá explicitní parametr `locale`. Jeho dosavadní výchozí čeština zůstává kvůli samostatnému instalačnímu návodu a existujícím volajícím. `GET /api/guide?locale=en|cs` vybírá obsah jednotlivého požadavku bez globálního nastavení serveru. Bez parametru vrací endpoint dosavadní český obsah; nepodporovaná hodnota požadavku používá EN. Tvar odpovědi se nemění.

## Reaktivita

Dashboard posílá aktuální UI locale při načtení příručky. Změna locale znovu načte překlad při zachování kapitoly, sekce a hledaného textu. Generace požadavků zabraňuje přepsání aktuálního obsahu opožděnou odpovědí jiného jazyka, včetně chybové odpovědi. Odpojená komponenta výsledek nepoužije.

Popisky příručky, hledání, načítání a chyby používají stabilní katalogové klíče. Technický text chyby je zachován v rozbalovacích podrobnostech. Překlad obsahu je součástí distribuce, za běhu se negeneruje.

## Ověření tohoto dílu

Regresní testy kontrolují shodné kapitoly a veřejné sekce, platnost interních odkazů v obou jazycích, zachování výchozího API a instalačního návodu, izolaci požadavků dvou klientů, přepnutí EN/CS/EN, zachování rozepsaného hledání a opožděné úspěchy i chyby. Browser scénář používá distribuované assety a statické API bez živých služeb; ověřuje český prohlížeč s výchozím EN, uložené CS, persistence, návrat EN a úzké okno.
