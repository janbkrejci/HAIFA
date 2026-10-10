Oprav tři chyby, které ukázala validace proti GitHubu s rosterem `claude-haiku` (běh `github-185807`):

1. **V7, ochrana dat:** builder v R4 vrátil necommitnuté změny v hlavním checkoutu (`.factory/agents.yaml`, `.factory/prompts/planner/user.md`). Hlídač zápisů to zachytil, ale ohlásil `REVERTED-BY-AGENT (uncommitted work lost, cannot restore)`. Agent tak může smazat neuloženou práci engineera.
2. **V6:** planner v R10 zapsal `plan.md` do `context_handoff/` uvnitř worktree místo do session adresáře a hlídač běh shodil (`worktree: context_handoff/plan.md — deleted`).
3. **V8:** R10 hlásí `inconclusive`, i když běh selhal (`run_ok` neprošel). Chybějící harness v rosteru tak schovává skutečné selhání.

Where: hlídač zápisů v `aifactory/src/aifactory/run/`, prompty agentů v `aifactory/` (výchozí konfigurace i `aifactory/validation/template/.factory/prompts/`), `aifactory/validation/scenarios.py`, `aifactory/tests/`.

Done means:
- Před každým voláním agenta hlídač uloží necommitnuté změny hlavního checkoutu (sledované i nesledované soubory, mimo gitignorované). Když agent hlavní checkout změní nebo vrátí, hlídač obnoví přesně stav před voláním, fáze selže a chyba jmenuje soubory. Hláška `cannot restore` už nenastane.
- Test s falešným harnessem: v hlavním checkoutu je necommitnutá změna sledovaného souboru i nový nesledovaný soubor, agent spustí `git checkout -- .` a `git clean -fd`, po fázi jsou obě změny zpět a fáze selhala.
- Prompty agentů říkají, že `context_handoff_dir` je absolutní cesta mimo repo a zapisuje se přesně na ni, nikdy do adresáře stejného jména v repu. Test ověří, že to říká každý prompt, který `context_handoff_dir` používá.
- Scénáře s kontrolou harnessu v rosteru (R1, R10) hlásí `failed`, když selže běh nebo jiná kontrola, a `inconclusive` jen tehdy, když chybí výhradně harness. Test to ověří pro oba případy.
- `just validate --remote local` projde bez `failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna modelů v rosterech, sandboxování agentů na úrovni OS.

Pevná omezení:
- Hlídač nikdy nesmaže ani nepřepíše necommitnou práci engineera. Při pochybnosti uloží zálohu a fázi shodí.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
