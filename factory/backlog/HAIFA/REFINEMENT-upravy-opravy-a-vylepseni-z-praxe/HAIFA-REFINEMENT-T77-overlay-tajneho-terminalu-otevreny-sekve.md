---
id: HAIFA-REFINEMENT-T77
title: "Overlay tajného terminálu otevřený sekvencí Ctrl, Shift, Ctrl, Shift"
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T76]
writes: [aifactory/web/src/lib/secretKeys.ts, aifactory/web/src/lib/secretKeys.test.ts, aifactory/web/src/lib/terminal.ts, aifactory/web/src/lib/terminal.test.ts, aifactory/web/src/components/terminal/, aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/src/aifactory/web/static/]
---

## Zadání
Přidej do dashboardu skrytý terminálový overlay nad API z HAIFA-REFINEMENT-T76.

Kde:
- `aifactory/web/src/lib/secretKeys.ts` (+ `secretKeys.test.ts`): detektor sekvence. Sekvence jsou čtyři stisky samotných modifikátorů hned po sobě, tedy `keydown` s `event.key` `Control`, `Shift`, `Control`, `Shift`, každý do 1 s od předchozího. Opakovaný `keydown` při držení klávesy (`event.repeat`) se nepočítá. Jakákoli jiná klávesa mezi nimi sekvenci zruší. Funguje i s fokusem v textovém poli.
- `aifactory/web/src/lib/terminal.ts` (+ `terminal.test.ts`): klient pro `GET /api/terminal` a `POST /api/terminal/exec`. NDJSON stream čte přes `fetch` a `ReadableStream`, příkaz ruší přes `AbortController`.
- `aifactory/web/src/components/terminal/TerminalOverlay.vue` (+ `TerminalOverlay.test.ts`): celoobrazovkový overlay ve stylu dashboardu (tmavý, neproporcionální písmo). Má výstup s odlišeným stderr, řádek s promptem `cwd $` a historii příkazů na šipkách nahoru a dolů. `Ctrl+C` zruší běžící příkaz, `Esc` nebo křížek overlay zavře. Když `GET /api/terminal` vrátí `enabled: false`, overlay místo vstupu ukáže hlášku, že terminál je dostupný jen při dashboardu na tomto počítači (loopback).
- `aifactory/web/src/App.vue`: zaregistruje posluchač `keydown` na `window` a připojí overlay. Stejná sekvence otevřený overlay zavře.
- `aifactory/src/aifactory/web/static/`: přegeneruj build (`just web-build`), aby ho `factory obs` servíroval.

Omezení: funkce je tajná. Nemá žádné tlačítko, položku menu ani zmínku v uživatelské příručce. Nepřidávej novou npm závislost (žádný xterm.js). Stávající sdílené prvky a styl (`style.css`, komponenty v `components/ui/`) použij jen tam, kde se hodí.

Mimo rozsah: backend, interaktivní programy s TTY, více záložek terminálu.

Hotovo znamená:
- `secretKeys.test.ts`, `terminal.test.ts` a `TerminalOverlay.test.ts` procházejí (`vitest run`) a pokrývají: správná sekvence overlay otevře; jiná klávesa uprostřed nebo prodleva nad 1 s sekvenci zruší; `repeat` se nepočítá; stream se rozparsuje na výstup a exit; `cd` přenese nové `cwd` do promptu; `Esc` overlay zavře; `enabled: false` ukáže hlášku.
- `aifactory/web/src/App.test.ts` dál prochází a `vue-tsc --noEmit` je bez chyb.
- V prohlížeči se po Ctrl, Shift, Ctrl, Shift otevře overlay a `echo ahoj` vypíše `ahoj`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/166 · náklady $0.00
