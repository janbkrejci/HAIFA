# Příloha pro autory workflow

Workflow je YAML se jménem, popisem, kroky a podmínkou přijetí `accept`. Vlastní ulož do `.factory/workflows/<jméno>.yaml` repa nebo do knihovny a ověř přes `factory workflow check .factory/workflows/<jméno>.yaml`.

## Kroky

**Kroky agentů**: `plan`, `scout`, `build`, `fix`, `revise`, `ask`, `resolve`, `test_plan`, `review`, `document`. Volby: `agent`, `harness`, `model`, `thinking`, `when`, `id`, `description`, `input`.

**Kódové kroky**: `test` (vykoná plán testera), `commit`, `changes`, `command` (`id`, `argv`, `timeout`), `rebase`, `rebuild`.

Tester používá lokální profil projektu s příkazy, pravidly výběru a naměřenými časy; při změně konfigurace ho obnoví. Selhání řeší builder, chybějící testy závěrečný reviewer. Automatická revize plánu ani triáž neběží; `test_review` lze uvést explicitně.

`test_plan.coverage`: `full` žádá celou sadu, `scoped` kontroly změny; jiný odmítne.

## Podmínky a smyčky

- `repeat: {max: N, until: podmínka}` s vnořenými `steps` opakuje kroky; `until` se vyhodnotí po každém kroku.
- `when: podmínka` krok přeskočí, když neplatí.
- `accept: podmínka` rozhodne, zda běh uspěl.

Podmínky čtou pole výstupů kroků (`test.passed`, `test.coverage`, `review.approved`, `rebase.conflict`) a umějí `and`, `or`, `not` a porovnání. Nikdy se nevyhodnocují jako kód.

```yaml
name: build-test-review
description: Build, test with repairs, review with revision
steps:
  - build
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix
      - test_plan
  - repeat: {max: 2, until: review.approved}
    steps:
      - review:
          input: [build, fix, revise]
      - revise
      - test_plan:
          id: replan
          input: [review]
      - test:
          id: retest
  - commit:
      when: test.passed and review.approved
accept: test.passed and review.approved
```

Auto-merge mergne jen PR workflow, které má krok `review`.

## roles.yaml

`.factory/roles.yaml` přepisuje, který agent vykonává který krok. Nech v něm jen role, které měníš; úplná kopie vestavěného registru (`roles_full_copy`) by tě odstřihla od jeho budoucích změn.
