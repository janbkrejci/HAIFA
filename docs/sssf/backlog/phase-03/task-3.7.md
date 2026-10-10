Dodej dashboardu živé aktualizace: změny souborů backlogu a `.factory/` a nové záznamy v trace DB se projeví v otevřeném UI bez obnovení stránky.

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Done means:
- Server sleduje `backlog/**` a `.factory/**` a posílá události přes Server-Sent Events. Změna souboru z CLI nebo editoru se v UI projeví do 2 s.
- Obrazovka Běhy načítá nové fáze a události z trace s kurzorem na `rowid`, bez opakovaného čtení celé tabulky.
- Obrazovky Backlog a Review se po události obnoví jen v dotčené části.
- Testy: změna souboru vyvolá událost, nový řádek v trace se objeví v odpovědi s kurzorem.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: vzdálený přístup, více uživatelů.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
