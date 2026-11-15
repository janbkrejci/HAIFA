# T54: Lokalizovat Review

Review používá společný katalog EN/CS a existující volbu jazyka dashboardu. Přepnutí jazyka mění popisky seznamu, detailu, potvrzovacích dialogů, akcí, kontrol, verdiktů a doprovodných textů diffu bez nového požadavku na API nebo remountu komponent.

Poznámka k vrácení, otevřené sekce, soubory diffu a probíhající akce musí zůstat zachovány. Po úspěšném vrácení se poznámka vymaže stejně jako před lokalizací. Obsah PR, patche, názvy a výstupy kontrol, verdikt a odpovědi agentů jsou původní data a nepřekládají se.

Chyby Review se překládají podle stabilních kódů API; již zobrazená chyba reaguje na změnu locale. Kód `trace_db_locked` nabízí opakování i v angličtině. Neznámý kód se zobrazí v lokalizované obecné hlášce. Systémová poznámka OB3 se vykresluje z katalogu, bez rozpoznávání českého textu backendu.

Regrese zahrnují EN/CS seznam a hotové PR, loading a prázdné stavy, zachování poznámky a otevřeného obsahu, potvrzení, konflikty, chyby API a oznámení výsledků akcí. Globální zpřístupnění přepínače a distribuovaný frontend řeší HAIFA-TODO-T35.
