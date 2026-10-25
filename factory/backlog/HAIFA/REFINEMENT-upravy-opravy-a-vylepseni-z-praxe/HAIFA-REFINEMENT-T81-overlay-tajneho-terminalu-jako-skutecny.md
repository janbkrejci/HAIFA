---
id: HAIFA-REFINEMENT-T81
title: Overlay tajného terminálu jako skutečný terminál (xterm.js nad PTY sezením)
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T79]
writes: [aifactory/web/package.json, aifactory/web/bun.lock, aifactory/web/src/lib/terminal.ts, aifactory/web/src/lib/terminal.test.ts, aifactory/web/src/lib/secretKeys.ts, aifactory/web/src/lib/secretKeys.test.ts, aifactory/web/src/components/terminal/, aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/src/aifactory/web/static/, THIRD_PARTY_NOTICES, aifactory/THIRD_PARTY_NOTICES, aifactory/tests/e2e/test_terminal_browser.py]
---

## Zadání
## Zadání
Přepiš overlay tajného terminálu (`aifactory/web/src/components/terminal/TerminalOverlay.vue`) z dnešního `<pre>` a řádkového inputu na skutečný emulátor terminálu nad PTY sezením z HAIFA-REFINEMENT-T79. Musí v něm jít pustit vim, mc, claude, herdr, top atd.

Kde:
- `aifactory/web/package.json` a `aifactory/web/bun.lock`: přidej `@xterm/xterm` a `@xterm/addon-fit` (instalace přes `bun add`). Tím ruší dřívější zákaz xterm.js z T77, protože bez emulátoru VT to nejde.
- `aifactory/web/src/lib/terminal.ts` (+ `terminal.test.ts`): klient pro `POST /api/terminal/sessions`, stream `GET /api/terminal/sessions/{id}/stream` (čtení `ReadableStream` po `Uint8Array`, předává se bez dekódování), `input`, `resize` a `DELETE`. Stávající `execTerminal` ponech jen jako záložní režim (viz níže), případně ho odstraň, pokud už ho nic nepoužívá.
- `aifactory/web/src/components/terminal/TerminalOverlay.vue` (+ `TerminalOverlay.test.ts`): celoobrazovkový overlay s instancí xterm.js. Použij `FitAddon`, `ResizeObserver` → `resize` sezení, `onData` → `input`, výstup streamu → `term.write(bytes)`. Písmo je neproporcionální a barvy ladí s tmavým motivem dashboardu. Při otevření se fokus přesune do terminálu. Když shell skončí, overlay ukáže hlášku a nabídne nové sezení (Enter).
- Esc, Ctrl+C, Ctrl+Z, Tab, šipky a F-klávesy patří programu v terminálu, overlay je neruší. Overlay proto už nezavírá Esc. Zavírá se tajnou sekvencí Control, Shift, Control, Shift (jako dnes) a nenápadným křížkem. Zavření (i odchod ze stránky) ukončí sezení přes `DELETE` a zrušení streamu.
- `aifactory/web/src/App.vue` (+ `App.test.ts`) a případně `aifactory/web/src/lib/secretKeys.ts` (+ `secretKeys.test.ts`): ověř, že detektor sekvence dostane `keydown` modifikátorů i s fokusem ve skryté textarea xterm.js. Pokud xterm.js propagaci zastaví, zaregistruj posluchač ve fázi capture.
- Když `GET /api/terminal` vrátí `enabled: false`, overlay jako dnes ukáže hlášku o loopbacku. Když vrátí `pty: false`, overlay použije stávající řádkový režim přes `exec`, nebo ukáže hlášku, že interaktivní terminál na tomto stroji není dostupný.
- `aifactory/src/aifactory/web/static/`: přegeneruj build (`just web-build`).
- `THIRD_PARTY_NOTICES` a `aifactory/THIRD_PARTY_NOTICES` (obsah obou je shodný): přidej položku pro xterm.js (`@xterm/xterm`, `@xterm/addon-fit`, MIT) s verzí a licencí ve stejném formátu jako Vue a lucide.

Omezení: funkce zůstává tajná, tedy žádné tlačítko, položka menu ani zmínka v příručce. Kromě dvou balíčků xterm žádná další npm závislost.

Mimo rozsah: backend, více záložek, kopírování/vkládání nad rámec toho, co umí xterm.js sám.

Hotovo znamená:
- `terminal.test.ts`, `TerminalOverlay.test.ts` a `App.test.ts` procházejí (`vitest run`) a pokrývají: vytvoření sezení s rozměry; bajty ze streamu jdou do `term.write`; `onData` volá `input`; změna velikosti volá `resize`; Esc overlay nezavře; zavření volá `DELETE`; `enabled: false` ukáže hlášku. xterm.js můžeš v testech mockovat.
- `vue-tsc --noEmit` je bez chyb a `just web-build` projde.
- V prohlížeči se po Control, Shift, Control, Shift otevře terminál, `vim` se vykreslí přes celý overlay, `Esc` a `:q` ho ukončí a sekvence overlay zavře.
- Oba THIRD_PARTY_NOTICES obsahují xterm.js.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
