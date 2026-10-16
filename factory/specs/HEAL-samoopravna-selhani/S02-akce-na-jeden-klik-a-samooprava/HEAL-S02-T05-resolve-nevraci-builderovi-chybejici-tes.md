# HEAL-S02-T05: Resolve nevrací builderovi chybějící testy, které nesmí zapsat

## Cíl

Běh `resolve` smí měnit jen konfliktní soubory. Nesmí proto posílat builderovi práci,
kterou guard vrátí a běh ukončí jako `writes_violation` (PR #75, běh c6773833).

## Chování

- Interpreter pozná běh resolve podle kódového kroku `rebase` ve workflow (`resolve`,
  `resolve-reviewed`).
- Revize testů dostane proměnnou `{{review_mode}}`: `resolve` v běhu resolve, jinak `task`.
  V režimu `resolve` posuzuje jen, zda plán pokrývá obě strany rebase. Chybějící test
  není blokující, revize ho ohlásí ve `follow_ups`.
- Vrátí-li revize plánu v resolve přesto `missing_tests`, interpreter nespustí `test_fix`.
  Každý chybějící test přidá jako follow-up do envelope revidovaného plánu („Doplnit
  chybějící test: …“) a revidovaný plán se spustí.
- Task run zakládá follow-upy i z běhu resolve, ale jen neblokující (`record(blocking=False)`):
  task je už postavený, `blocks_task` a `blocked_by` se v resolve ignorují.
- `ConflictWriteGuard.allows_writes()` říká, zda agent smí změnit aspoň jeden soubor. Bez
  konfliktu nebo s konfliktem jen v `generated:` výstupu je množina prázdná.
- Krok `fix` nebo `test_fix` se při prázdné množině nespustí. Běh skončí chybou
  `RunFailure` (`failure_kind: other`, `failure_detail.cause: nothing_writable`) s důvodem
  „… the run may change no file …“ a názvy selhaných kontrol. Větev se vrátí na původní tip.

## Ověření

`tests/run/test_task_resolve_generated.py`: konflikt jen v bundlu a revize s chybějícím
testem doběhne s jedním neblokujícím follow-upem a bez `test_fix`, červené testy při
stejném konfliktu skončí s důvodem místo `writes_violation`.
