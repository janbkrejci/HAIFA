---
id: HAIFA-S03-T12
title: "Agenti: zakázané příkazy a výsledek testu pro review"
status: done
depends_on: []
---

## Zadání
Agenti spouštějí celou testovací sadu, i když jim to prompt zakazuje. Za 19 běhů od 2026-10-02 strávil builder v průměru 8 z 12 minut testy (jednou celou sadou) a reviewer 5 z 8 minut (1,3× celou sadou). Fáze test pak sadu pustí znovu, takže na task padne asi 7–8 minut navíc. Reviewer navíc výsledek fáze test nedostane: `previous_envelope` je jen jedna obálka (poslední z `input:`), proto si testy pouští sám.

Where: konfigurace agentů (`aifactory/src/aifactory/harness/`, načítání `.factory/agents.yaml`), adaptéry harnessů (claude, codex, pi), interpret workflow (`aifactory/src/aifactory/workflow/`), výchozí prompty v `aifactory/src/aifactory/defaults/`, testy v `aifactory/tests/`.

Done means:
- Agent v `.factory/agents.yaml` může mít seznam zakázaných příkazů (například `just check`, `just test`, `just e2e`, `just web-test`, `pytest` bez cesty). Adaptér ho předá harnessu, u claude jako `--disallowedTools`. Harness, který zákaz neumí, to při `factory check` a na začátku běhu nahlásí.
- Krok workflow může dostat víc vstupů: review dostane obálku builderu (nebo fixu či revize) i výsledek posledního testu (prošel, příkaz, cesta k logu) jako samostatnou proměnnou šablony.
- Výchozí prompt revieweru říká, že fáze test už sadu na stejném kódu pustila, a uvádí její výsledek.
- Testy: zákaz se dostane do příkazu harnessu, harness bez podpory zákazu se nahlásí, review dostane obě obálky.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: sandbox na úrovni systému, omezení sítě.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/26 · náklady $4.33
