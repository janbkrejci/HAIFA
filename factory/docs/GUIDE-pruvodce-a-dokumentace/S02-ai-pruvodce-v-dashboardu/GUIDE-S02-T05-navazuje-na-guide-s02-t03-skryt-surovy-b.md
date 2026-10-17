# AI průvodce: návrh akce během streamování

Když průvodce v odpovědi navrhuje akci, panel během streamování neukazuje surový blok
`haifa-action` s JSONem.

## Chování

- Jakmile průvodce začne psát blok `haifa-action`, místo něj se v rozepsané odpovědi ukáže
  zástupná karta **Připravuji návrh akce…**. Text před blokem i po něm se zobrazuje dál.
- Po dokončení odpovědi zástupnou kartu nahradí karta návrhu s náhledem změny a tlačítky
  **Provést** a **Zahodit**, stejně jako dosud.
- Ostatní bloky kódu (např. `sql`) se během streamování zobrazují jako kód.
