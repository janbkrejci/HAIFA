# Příloha pro autory workflow

Workflow je YAML se jménem, popisem, kroky a podmínkou přijetí `accept`. Vlastní ulož do `.factory/workflows/<jméno>.yaml` repa nebo do knihovny a ověř přes `factory workflow check .factory/workflows/<jméno>.yaml`.

## Kroky

**Kroky agentů** (role z registru rolí): `plan` (planner), `scout` (scout), `build`, `fix`, `revise`, `ask` a `resolve` (builder), `test_plan` (tester), `test_review` (test-reviewer), `review` (reviewer) a `document` (documenter). Krok může mít `agent`, `harness`, `model`, `thinking`, `when`, `id`, `description` a `input` (výstupy kterých kroků dostane).

**Kódové kroky** běží bez modelu: `test` (spustí kontroly vybrané testerem, všechny i po prvním selhání), `commit`, `changes` (diff běhu pro dokumentaci), `command` (`id`, `argv`, `timeout`), `rebase` a `rebuild` (přegenerování `generated`).

`coverage` je volba kroku `test_plan`: `full` žádá plán celé sady testů, `scoped` jen kontroly změny. Plán jiného rozsahu gate odmítne.

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
  - commit:
      when: test.passed and review.approved
accept: test.passed and review.approved
```

Auto-merge mergne jen PR workflow, které má krok `review`.

## roles.yaml

`.factory/roles.yaml` přepisuje, který agent vykonává který krok. Nech v něm jen role, které měníš; úplná kopie vestavěného registru (`roles_full_copy`) by tě odstřihla od jeho budoucích změn.
