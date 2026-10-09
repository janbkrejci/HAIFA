---
id: HAIFA-S03-T16
title: "Auto-continue: souběžné běhy s limitem a bez kolize zápisových cest"
status: done
workflow: simple-sdlc
depends_on: []
---

## Zadání
Auto-continue dnes spouští další task až po doběhnutí předchozího, tedy jeden po druhém. Přidej limit souběžných běhů a výběr dalšího tasku, který nesahá na cesty běžících běhů ani otevřených PR, aby vznikalo co nejméně konfliktů.

Where: `aifactory/src/aifactory/run/queue.py` (výběr a řetěz), konfigurace v `aifactory/src/aifactory/config/`, `aifactory/src/aifactory/run/scope.py` (efektivní `writes`), dashboard (stav řetězu, Nastavení), testy.

Done means:
- Konfigurace `max_parallel_runs` (výchozí 1) určuje, kolik běhů auto-continue drží naráz. Při hodnotě nad 1 řetěz spouští další připravené tasky, dokud limit nevyčerpá, a po každém doběhnutém běhu doplní další.
- Task se souběžně spustí jen tehdy, když se jeho efektivní `writes` nepřekrývají (prefixem cesty) s `writes` běžících běhů ani se soubory změněnými v otevřených, nesloučených PR. Jinak ho řetěz přeskočí s důvodem `writes_overlap` (který běh nebo PR a které cesty) a zkusí další.
- Task, jehož `writes` pokrývají celý balíček nebo repo (HAIFA dnes dědí `aifactory/` a `justfile`), se souběžně s ničím nespustí. Řetěz to uvede v přehledu.
- Dashboard ukazuje běhy řetězu, volné sloty a přeskočené tasky s důvodem. `max_parallel_runs` jde nastavit v Nastavení.
- Testy: limit souběhu, přeskočení při překryvu s během i s otevřeným PR, doplnění po doběhnutí, `max_parallel_runs: 1` se chová jako dnes.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: automatické zúžení `writes` tasků (například podle Where), plánovač napříč projekty.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/44 · náklady $8.34
