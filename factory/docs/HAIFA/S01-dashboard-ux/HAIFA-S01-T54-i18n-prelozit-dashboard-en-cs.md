# T54 — Dvojjazyčná příručka

Implementovaný díl přidává anglický překlad všech devíti kapitol integrované příručky. Český obsah a samostatný instalační návod zůstávají kompatibilní. Nejde o dokončenou anglickou lokalizaci celého dashboardu.

UI příručky používá společné katalogy EN/CS a požaduje obsah přes `/api/guide?locale=en|cs`. Server vybírá jazyk pro každý požadavek zvlášť; dva klienti nesdílejí jazykový stav. Endpoint bez parametru zachovává původní český obsah. Anglické soubory jsou statické součásti Python balíčku v `guide/en/`.

ID kapitol a sekcí se nepřekládají. Komentáře `<!-- section:id -->` v anglických nadpisech zachovávají existující odkazy; vykreslení komentáře skryje. Hledání používá přeložené názvy a text aktuálního jazyka. Změna jazyka zachová rozepsaný dotaz a adresu kapitoly i sekce. Opožděné odpovědi předchozího locale nemohou přepsat aktuální výsledek.

Na úzkém okně má příručka menší odsazení a zalamuje dlouhé řetězce; tabulky a bloky kódu mají vlastní horizontální posouvání. Hláška selhání se lokalizuje, původní technické podrobnosti jsou dostupné po rozbalení.

Jedno cílené diagnostické spuštění `bun run test src/views/GuideView.test.ts` prošlo všech devět scénářů. Následná úprava ukončuje komponenty před obnovením původního `fetch`, aby úklid testů nevyvolával síťové požadavky. Úplnou verifikaci, sestavení distribuovaného frontendu a browser kontrolu provádí samostatný testovací krok workflow.
