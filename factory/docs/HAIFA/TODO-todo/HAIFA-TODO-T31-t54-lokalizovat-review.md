# T54: Lokalizace Review

Seznam a detail Review nyní používají EN/CS katalog. Přeloženy jsou sekce otevřených a hotových PR, stavy mergeability, schvalování, vracení, řešení konfliktů, potvrzení, kontroly, verdikty, popisky diffu a loading, prázdné i chybové stavy. Počty souborů používají pravidla množného čísla EN/CS.

Přepnutí jazyka zachovává rozepsanou poznámku, otevřené sekce, otevřený soubor diffu a potvrzovací dialog. Nemění obsah PR, diffy, workflow, názvy a výstupy kontrol ani odpovědi agentů. Systémová poznámka OB3 je přeložená v katalogu; API kontrakt zůstává stejný.

Chybové stavy se uchovávají odděleně od výsledného překladu. Překlad reaguje na locale i po selhání akce; nabídka opakování vychází z kódu `trace_db_locked`. Neznámé chyby API zobrazují lokalizovaný text s kódem.

Nové regresní scénáře jsou v `ReviewView.locale.test.ts`; původní testy Review explicitně používají češtinu. Očekávání sdíleného náhledu diffu ve Factory odpovídají výchozí angličtině. Diagnostické spuštění nového testu skončilo před spuštěním testů, protože v pracovním prostředí není nainstalovaný Vitest. Ověření provádí samostatný krok workflow. Distribuované assety a globální přepínač jsou součástí HAIFA-TODO-T35.
