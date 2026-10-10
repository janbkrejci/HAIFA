# Výběr a vyřešení nálezů Factory

1. Na stránce **Factory** zaškrtni nálezy, které chceš vyřešit, a klikni na **Vyřešit vybrané nálezy**.
2. V předvyplněném úkolu zvol krok backlogu, workflow a povolené cesty. Zadání obsahuje vybrané nálezy a jejich doporučené opravy; můžeš je upravit.
3. Ulož úkol a použij **Commitnout backlog do base**. Tento commit zahrnuje všechny necommitnuté změny backlogu. Případné nové workflow nejprve zveřejni přes **Commitnout konfiguraci** na stránce Factory.
4. Zkontroluj upozornění a klikni na **Spustit**. Po spuštění se zobrazí odkaz na běh; pokud se běh ještě spouští, jeho stav přijde živě nebo ho obnov tlačítkem **Obnovit stav běhu**.

Opravný úkol zůstává v backlogu i po zavření panelu. Nová kontrola Factory vymaže výběr nálezů. Běh respektuje povolené cesty a chráněné soubory; u oprav počítače či knihovny mimo jeho oprávnění má popsat konkrétní postup pro operátora. Pokud konfigurace Factory znemožňuje spuštění samotného běhu, nejprve ji oprav běžnými operacemi Factory.

Implementace používá stávající API pro založení, commit a spuštění úkolu. Není potřeba nová konfigurace ani migrace.

Vizuální ukázka: [panel opravy](../aifactory/validation/artifacts/HAIFA-S05-T16-factory-repair.png).
