# HAIFA-S05-T13: Obrazovky Tento počítač a Knihovna

Dashboard přidává globální hash routes `#/setup` a `#/library`, dostupné z přepínače repozitářů. Při prvním načtení prázdného registru otevře Tento počítač, pokud kontrola hlásí chybu, knihovna chybí nebo kontrolu nelze načíst. Zdravý počítač s knihovnou zůstane na prázdném přehledu. Explicitní navigace na jinou stránku se během kontroly respektuje.

Tento počítač seskupuje nálezy kontroly do HAIFA, Nástroje, Harnessy, Hosting, Knihovna a Prostředí. Oprava se kopíruje do schránky. Znovu zkontrolovat vyžádá čerstvý report. API přidává počty registrovaných rep podle harnessů; počty se obnovují i při použití cache kontroly. Stránka neinstaluje nástroje a nespouští přihlášení.

Knihovna na tomto počítači ukazuje cestu, remote a známé počty náskoku a zpoždění. Bez remote jsou Pull a Push zakázány. Založení ze semínka a klonování URL nejprve otevřou serverový plán v modálu; zápis vyžaduje potvrzení jeho digestu. Blokátory potvrzení zakazují.

Knihovna zobrazuje záložky Agenti, Workflow, Skilly a Rozšíření pi. API poskytuje účel nebo popis z commitnutých metadat, pořadí verze a použití. Detail načítá soubory pouze pro čtení, historické verze a použití se stavem, zaškrtnutím a Diff. Diff používá náhled cílené aktualizace repa, včetně konfliktů.

Přidání a aktualizace položky nejprve plánují vybraná repa. Uživatel volí commit do base nebo PR. Po potvrzení se dostupné plány provádějí postupně; zablokované nebo selhavší repo nezastaví ostatní. Výsledky ukazují commit, PR nebo blokátor. Operace vždy pracují s aktuální verzí knihovny, i při prohlížení starší verze.

Import vyžaduje složku pod domovem uživatele a typ položky. Backend kontroluje hranice cesty a poskytuje plán. Klient odesílá jen volby a digest, nikdy obsah ani seznam zapisovaných souborů. Změněný digest vyžaduje nový náhled.

Ověření zahrnuje cílené Vitest testy obou obrazovek, App, routeru a modálu; backendové testy metadat, počtů harnessů a existujících knihovních plánů; Playwright založení semínka s dočasným HAIFA_HOME a upravený scénář prvního spuštění M15. Statické assets se generují buildem Vue/Vite.
