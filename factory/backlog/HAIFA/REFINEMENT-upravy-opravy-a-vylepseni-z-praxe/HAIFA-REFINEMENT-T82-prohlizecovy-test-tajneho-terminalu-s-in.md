---
id: HAIFA-REFINEMENT-T82
title: Prohlížečový test tajného terminálu s interaktivním programem
status: todo
workflow: build-test
depends_on: [HAIFA-REFINEMENT-T81]
writes: [aifactory/tests/e2e/test_terminal_browser.py]
---

## Zadání
## Zadání
Uprav prohlížečový test `aifactory/tests/e2e/test_terminal_browser.py` podle nového overlaye s xterm.js nad PTY sezením (HAIFA-REFINEMENT-T79, HAIFA-REFINEMENT-T81). Dnešní test zavírá overlay klávesou Esc a čte výstup z `<pre>`. To po změně neplatí.

Test spustí dashboard na loopbacku a v prohlížeči stiskne Control, Shift, Control, Shift. Ověří, že se objeví overlay s terminálem (prvek `.xterm`). Výstup čte z DOM rendereru xterm.js (`.xterm-rows`) nebo přes `page.evaluate` z bufferu terminálu, pokud je komponenta vystaví pro testy. Pak ověří:
- `echo haifa-terminal` + Enter vypíše `haifa-terminal`;
- stdin je TTY: `python3 -c "import sys;print('tty', sys.stdin.isatty())"` vypíše `tty True` (použij interpret testu přes `sys.executable`);
- interaktivní program funguje: spusť krátký Python skript s `curses` nebo `input()`, který čeká na stisk klávesy a pak vypíše výsledek. Pošli klávesu a ověř výstup. Pak `Esc` předaný programu overlay nezavře;
- Ctrl+C přeruší běžící `sleep 100` a shell zase odpovídá;
- sekvence Control, Shift, Control, Shift overlay zavře.
Druhý případ jako dnes ověří, že Control, Shift, A, Control, Shift overlay neotevře. Na Windows test přeskoč, pokud `GET /api/terminal` vrací `pty: false`.

Mimo rozsah: změny backendu nebo frontendu. Když test odhalí chybu, ohlas ji jako follow-up.

Hotovo znamená:
- `aifactory/tests/e2e/test_terminal_browser.py` prochází.
- Ostatní testy v `aifactory/tests/e2e/` nejsou dotčené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
