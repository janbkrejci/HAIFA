# HAIFA-S05-T16: Opravit nálezy na stránce Factory

Uživatel může označit jednotlivé nálezy kontroly Factory a předat je opravnému běhu.

- Každý nález má přístupný checkbox, včetně nálezů počítače a knihovny. Výběr začíná prázdný a nová kontrola jej vymaže; opakovaný kód nálezu nespojuje jeho jednotlivé výskyty.
- Tlačítko „Vyřešit vybrané nálezy“ se aktivuje pouze s neprázdným výběrem po dokončení kontroly. Probíhající operace Factory blokují výběr a otevření opravy.
- Oprava předvyplní nový úkol v existujícím formuláři: název a zadání s kódem, rozsahem, závažností, zprávou, doporučenou opravou a akcí pouze vybraných nálezů. Uživatel zvolí krok backlogu, workflow a povolené cesty; může upravit zadání.
- Uložení volá existující API pro vytvoření úkolu, potom kontrolu běhu. Před spuštěním musí být úkol commitnutý v base a mít workflow i povolené cesty. Commit backlogu zůstává explicitní akcí a uživatel vidí, že zahrne všechny změny backlogu.
- Spuštění používá existující API a RunDialog včetně kontroly závislostí, varování konfigurace, chyb a odkazu na běh. Odpověď pending blokuje opakované spuštění; dokončení startu se dohledá přes živé události nebo ruční obnovu.
- Zadání oprav respektuje chráněné soubory a rozsah běhu. Pokud nález nelze v běhu opravit (například instalace nástroje na počítači), agent má uvést překážku a konkrétní postup pro operátora.

Backend a pravidla oprávnění se nemění. Prázdný backlog nebo jeho chyba mají samostatný stav. Zavření panelu po vytvoření úkolu tento úkol nemaže.

Ověření: cílené testy FactoryView, TaskForm a RunDialog; TypeScript kontrola, produkční build, Ruff. Vizuální náhled používá lokální fixture bez modelů a síťových služeb.
