Implementuj `factory --skill` a sjednoť `--json` u všech příkazů (D12).

Where: `aifactory/src/aifactory/skill/`, CLI, `aifactory/tests/`.

Done means:
- `factory --skill` vypíše skill pro agenta z aktuální verze kódu: všechny příkazy s argumenty, formát backlogu (hlavička tasku, `index.md`), formát workflow, postupy převodu plánu do backlogu, spuštění, review, schválení, vrácení a `resolve`. Seznam příkazů se generuje z definice CLI, ne ručně.
- Každý příkaz umí `--json` se stejnou obálkou (`ok`, `data`, `error.code`, `error.message`, `warnings`) a stabilními kódy chyb. Seznam kódů je ve skillu.
- Test ověří, že každý příkaz CLI je ve skillu a že každý příkaz s `--json` vrací platnou obálku.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: dashboard.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
