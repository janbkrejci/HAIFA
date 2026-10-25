---
id: HAIFA-REFINEMENT-T78
title: Prohlížečový test tajného terminálu
status: done
archived: true
workflow: build-test
depends_on: [HAIFA-REFINEMENT-T76, HAIFA-REFINEMENT-T77]
writes: [aifactory/tests/e2e/test_terminal_browser.py]
---

## Zadání
Přidej prohlížečový test `aifactory/tests/e2e/test_terminal_browser.py` po vzoru stávajících testů v `aifactory/tests/e2e/` (např. `test_assistant_browser.py`, jejich fixtures a spuštění dashboardu).

Test spustí dashboard na loopbacku a v prohlížeči postupně stiskne Control, Shift, Control, Shift. Ověří, že se objeví overlay terminálu. Pak napíše `echo haifa-terminal`, stiskne Enter a ověří výstup. Potom zadá `cd` do dočasného adresáře a ověří nové `cwd` v promptu. Nakonec overlay zavře klávesou `Esc`. Druhý případ ověří, že stisk Control, Shift, A, Control, Shift overlay neotevře.

Mimo rozsah: změny backendu nebo frontendu. Když test odhalí chybu, ohlas ji jako follow-up.

Hotovo znamená:
- `aifactory/tests/e2e/test_terminal_browser.py` prochází.
- Ostatní testy v `aifactory/tests/e2e/` nejsou dotčené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-test · PR https://github.com/janbkrejci/HAIFA/pull/167 · náklady $0.00
