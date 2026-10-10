Implementuj workflow `resolve` a `factory task resolve <task-id>` pro PR, který nejde mergovat kvůli konfliktu (krok 6 v sekci „Běh úkolu“ v `docs/product-brief.md`, riziko R2).

Where: `aifactory/src/aifactory/defaults/workflows/resolve.yaml`, role v `defaults/roles.yaml`, `run/`, CLI, `aifactory/tests/`.

Done means:
- `task resolve` spustí nový běh na větvi PR: rebase na aktuální `base`, agent vyřeší konflikty jen v souborech s konfliktem, test, push, PR se aktualizuje.
- Když rebase projde bez konfliktu, agent se nevolá.
- Když agent konflikt nevyřeší nebo test neprojde, běh selže a větev zůstane ve stavu před rebase.
- `task approve` při chybě `conflict` doporučí `task resolve`.
- Testy s providerem `local` a falešným harnessem: dva tasky nad stejným řádkem, první se mergne, druhý jde `resolve` a pak approve.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: automatické spuštění `resolve` bez příkazu.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
