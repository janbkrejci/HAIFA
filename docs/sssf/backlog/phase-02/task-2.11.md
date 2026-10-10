Implementuj provider Azure DevOps (`az repos`) pro rozhraní `GitProvider` z 2.10.

Where: `aifactory/src/aifactory/providers/`, `aifactory/tests/`.

Done means:
- Provider umí všechno, co rozhraní z 2.10: vytvořit PR, stav, mergeability včetně `unknown`, merge se strategií, komentář.
- Nastavení organizace, projektu a repa je v `.factory/config.yaml`. Chybějící `az` nebo přihlášení vrací srozumitelnou chybu (`factory harness check` ne, vlastní kontrola provideru).
- Testy proti falešnému `az` pokryjí všechny operace a chybové stavy. Formát výstupů `az` odpovídá dokumentaci `az repos pr`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: ověření proti skutečnému Azure DevOps (udělá engineer, až bude k dispozici).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají síť.
