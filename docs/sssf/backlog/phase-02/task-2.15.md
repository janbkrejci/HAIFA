Přenes auto-continue a bezpečné paralelní běhy do `aifactory` (krok 8 v sekci „Běh úkolu“ v `docs/product-brief.md`, D10, Q9).

Where: `aifactory/src/aifactory/run/`, CLI, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/queue.py`, oprava souběhu SQLite z úkolu 1.12.

Done means:
- `task run --auto` a přepínač auto-continue u modulu nebo stepu: po úspěšném běhu (PR vytvořen) se spustí další připravený task v pořadí backlogu. Selhání řetěz zastaví.
- Task, který závisí na nemergnutém PR, se přeskočí a spustí se další, který spustit jde (Q9).
- Dva běhy různých tasků mohou běžet současně, dva běhy téhož tasku ne. Trace DB je ve WAL a první souběžné běhy nekončí `database is locked`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: plánovač napříč moduly.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
