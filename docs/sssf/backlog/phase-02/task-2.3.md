Přenes adaptéry harnessů claude, codex a pi a jejich registr do `aifactory` a doplň společné kontraktové testy, které platí pro všechny tři adaptéry.

Where: `aifactory/src/aifactory/harness/`, `aifactory/tests/harness/`. Zdroj: `prototype/src/haifa_proto/harness/`, `vendor/sssf/templates/adws/adw_modules/agent_cc.py` a `agent_pi.py`.

Done means:
- Harness se u agenta zapisuje výslovně (`harness: claude|codex|pi`) a jde přepsat u kroku workflow spolu s modelem a thinking (D13). Z jména modelu se neodvozuje.
- `factory harness check [--json]` ověří, že CLI každého harnessu použitého v konfiguraci je na PATH, a vypíše verze.
- Kontraktové testy s falešnými procesy pro všechny tři adaptéry: stejný tvar envelope, obnovení téže session v opravném kole (Codex přes `codex exec resume`), zápis událostí do trace, a cwd agenta je adresář, který mu předá volající.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: běh ve worktree (2.9), konfigurace `.factory/` (2.4).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani skutečné CLI harnessů.
