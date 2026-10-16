# HEAL-S02-T05: Resolve nevrací builderovi chybějící testy, které nesmí zapsat

## Co se změnilo

Auto-resolve PR, jehož konflikt byl jen v generovaném bundlu, selhal na `writes_violation`:
revize testů chtěla nový test, builder ho zapsal a guard resolve (smí měnit jen konfliktní
soubory) zápis vrátil. Teď:

- **Revize testů v resolve** (`review_mode: resolve`) kontroluje jen, že plán pokrývá obě
  strany rebase. Chybějící test nehlásí jako blokující, ale jako follow-up.
- **`missing_tests` v resolve nejdou builderovi.** Interpreter (`workflow/interpreter.py`)
  místo kroku `test_fix` založí za každý chybějící test follow-up a revidovaný plán spustí.
  Follow-upy se zapíšou do TODO stepu projektu i z běhu resolve, vždy jako neblokující.
- **Bez povolených souborů se neopravuje.** Když `ConflictWriteGuard.allows_writes()` vrátí
  `false` (konflikt jen v `generated:` výstupu), krok `fix` ani `test_fix` se nespustí.
  Červené testy běh ukončí s důvodem „the checks failed (…) and the run may change no
  file …“ (`failure_detail.cause: nothing_writable`) a větev zůstane, kde byla.

## Na co dát pozor

- Seed agent `test-reviewer` má novou sekci `review_mode`. Knihovna v `$HAIFA_HOME`, která
  má starší kopii agenta, proměnnou nedostane do promptu. Interpreter ale chybějící testy
  v resolve převede na follow-upy i tak.
- Follow-upy z resolve nikdy neblokují task (`blocks_task` a `blocked_by` se ignorují).
