Přenes engine sssf do balíčku: moduly z `vendor/sssf/templates/adws/adw_modules/` do `aifactory/src/aifactory/engine/` beze změny logiky a pokryj testy chování, které prototyp i sssf dnes spoléhají (riziko R6 v briefu).

Where: `aifactory/src/aifactory/engine/`, `aifactory/tests/engine/`.

Done means:
- Engine se importuje jako `aifactory.engine` a nepotřebuje `sys.path` ani `vendor/`.
- Rozšíření enginu z prototypu (`prototype/src/haifa_proto/engine.py`, `roles.py`) jsou přenesená do `aifactory/src/aifactory/engine/`.
- Testy s falešným harnessem pokryjí: rollback zápisů mimo `writes` a `protected_files`, re-prompt téže session při nevalidním envelope, gate correction do téže session, ukončení dětí agenta při SIGTERM, zápis fází a událostí do trace DB a `run.finish(accepted=…)`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: harnessy claude, codex a pi (2.3), workflow interpret (2.7), změny chování enginu.

Pevná omezení:
- Logika modulů se nemění, jen importy a umístění. Každá změna chování je chyba.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
