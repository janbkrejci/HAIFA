# T54: Lokalizovat obrazovku běhů

Obrazovka Běhy používá existující EN/CS locale dashboardu. Překlady zahrnují seznam a filtry, archivaci a mazání, ovládání běhu, detail a fáze, waterfall, náklady, řetězy, selhání a nabídky opakování i změny harnessu.

Přepnutí jazyka překreslí texty bez nového načtení dat nebo remountu komponent. Zachová vybraný běh a fázi, filtry, rozbalené události a prompty, rozepsanou poznámku a vybraný harness. Živé aktualizace pokračují se stávajícími kurzory.

Chyby požadavků se zobrazují podle existujících stabilních API kódů. Neznámý kód má lokalizovanou obecnou hlášku obsahující kód. Retry při obsazené databázi se řídí kódem, nikoli přeloženou větou. Stav a důvod přeskočení v řetězu používají kódy; původní podrobnosti jsou dostupné jako technická diagnostika.

Logy, prompty, odpovědi agentů, uložené chyby, poznámky, názvy fází, tasků, modelů, cest a API enumy se nepřekládají ani nepřepisují. Locale se neposílá jako globální přepnutí serveru.

Regrese pokrývají EN → CS → EN při sledování běhu a příjmu tail události, otevřenou fázi a obsah, retry poznámku, již zobrazenou chybu API, potvrzovací dialog, filtr, náklady, řetěz a zvolený záložní harness. Browser testy layoutu běhů používají explicitní CS locale.
