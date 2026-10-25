# HAIFA-REFINEMENT-T77 — Implementace a ověření

Interní technická dokumentace změny; funkce nemá odkaz ani ovládací prvek v navigaci či příručce.

Posluchač na `window` v capture fázi zpracuje čtyři stisky Control, Shift, Control, Shift i při fokusu v textovém poli. Interval mezi sousedními stisky smí být nejvýše 1000 ms. Opakované keydown události se ignorují a neposouvají časový limit. Jiná klávesa rozpracovanou sekvenci zruší; nový Control může začít novou sekvenci. Dokončení přepíná přítomnost overlaye; při odpojení aplikace se posluchač odstraní.

Klient načítá dostupnost a počáteční cwd z API. Streamované NDJSON zpracovává po řádcích včetně rozdělených UTF-8 znaků a závěrečného řádku bez odřádkování. Výstup stderr je barevně odlišený; exit aktualizuje cwd a nenulový kód vypíše. Neúplný stream či HTTP chyba se zobrazí ve výstupu. Příkazy se vkládají jako text, nikoli HTML.

Overlay drží historii příkazů a rozepsaný vstup při procházení šipkami. Ctrl+C během běhu přeruší fetch přes AbortController. Escape, křížek a opětovná sekvence overlay zavřou; odpojení ruší také probíhající požadavky. Fokus při otevření přejde do overlaye a při zavření se vrací. Nedostupný terminál zobrazí loopback vysvětlení bez vstupu. Nové otevření má novou historii i cwd načtené z API.

## Provedené kontroly

- V `aifactory/web`: `bun run test src/lib/secretKeys.test.ts src/lib/terminal.test.ts src/components/terminal/TerminalOverlay.test.ts src/App.test.ts` — 4 soubory, 48 testů prošlo.
- `just web-build` — úspěšný vue-tsc i produkční build v distribuovaných static souborech.
- `git diff --check` — bez chyb.
- Ego Browser proti sestavenému frontendu a skutečným endpointům `terminal_get`/`terminal_exec` na lokálním ASGI serveru: fyzická sekvence modifikátorů otevřela overlay, `echo ahoj` vypsalo `ahoj`, `cd /` změnilo prompt na `/ $` a další sekvence overlay zavřela. Ostatní dashboardové endpointy tento izolovaný server neposkytoval.

Pro navazující testovací fázi jsou relevantní stejné čtyři soubory Vitest a frontendový typecheck. Vyhledání v celém `aifactory/tests/` nenašlo přímé volající nových frontendových funkcí; backend zůstal beze změny. Testy backendového terminálu jsou v `aifactory/tests/web/test_web_terminal.py`; automatizované prohlížečové pokrytí samostatně řeší navazující task T78.
