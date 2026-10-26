---
id: HAIFA-REFINEMENT-T87
title: "Sdílení knihovny přes fork padá: gh repo fork odmítá --remote"
status: done
archived: true
depends_on: []
writes: [aifactory/src/aifactory/library/share.py, aifactory/tests/library/test_library_share.py]
---

## Zadání
Sdílení změn knihovny přes fork padá na novějším `gh`. Dashboard → Knihovna → **Obnovit výchozí agenty a workflows** skončil chybou `pr_failed: cannot open the pull request: gh repo fork: the --remote flag is unsupported when a repository argument is provided` a knihovna zůstala beze změny.

## Současný stav (naměřeno v NEO_HEF 2026-10-26, factory 0.1.537, gh 2.102.0)

- `aifactory/src/aifactory/library/share.py:285` volá `gh repo fork <owner>/<repo> --clone=false --remote=false`. `gh` 2.102.0 přepínač `--remote` u volání s argumentem repozitáře odmítá, i když má hodnotu `false`.
- Do větve s forkem se jde, když aktivní účet `gh` nemá do repa knihovny zápis (`viewerPermission` READ). Tady byl aktivní `JanKrejciASOL` místo `janbkrejci`. Po `gh auth switch -u janbkrejci` jde push přímo a chyba se neprojeví, ale každý uživatel bez práva zápisu do knihovny ji dostane vždy.
- Test `aifactory/tests/library/test_library_share.py:245` kontroluje jen `--clone=false`. Fake `gh` přepínač `--remote` nepozná, proto vada prošla.

## Co udělat

1. Z volání `gh repo fork` odebrat `--remote=false`. S argumentem repozitáře `gh` remote nepřidává.
2. Test fork větve doplnit o aserci, že žádný argument nezačíná `--remote`.
3. Projít ostatní volání `gh` v `aifactory/src` na přepínače, které `gh` u daného tvaru příkazu odmítá.

## Hotovo znamená

- Sdílení knihovny přes fork funguje s `gh` 2.102.0.
- Test zčervená, když se `--remote` do volání vrátí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-26 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/176 · náklady $0.00
