---
id: HEAL-S01-T01
title: Druh selhání běhu jako typované pole
status: done
depends_on: []
---

## Zadání
Selhaný běh dnes nese jen volný text v `task_runs.error`. Dashboard, CLI ani řetěz z něj nepoznají, co se stalo a co s tím.

Zadání:
1. Při selhání běhu zapsat do trace typovaný druh selhání (např. `failure_kind`) a strukturovaný detail. Druhy podle dat z HAIFA: `accept_not_met`, `nothing_to_do` (builder ohlásil fail, protože práce už je hotová nebo zadání nic nežádá), `quota` (harness hlásí vyčerpanou kvótu nebo kredity), `writes_violation` (zápis mimo worktree nebo writes), `invalid_output` (agent nevrátil platný envelope), `process_gone`, `stopped`, `other`.
2. Rozpoznání kvóty dělá adaptér harnessu (`harness/`), ne regulární výraz nad textem chyby v `run/`.
3. Druh a detail vrací `factory task show --json`, `factory task runs --json` a API běhu.
4. Staré běhy bez pole se zobrazí jako `other`.

Hotovo znamená:
- Testy pokrývají každý druh na úrovni místa, kde vzniká (fake harness, guard, envelope).
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/65 · náklady $6.11
