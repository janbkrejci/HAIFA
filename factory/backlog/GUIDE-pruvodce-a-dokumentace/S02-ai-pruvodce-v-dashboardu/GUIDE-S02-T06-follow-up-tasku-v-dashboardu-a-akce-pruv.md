---
id: GUIDE-S02-T06
title: Follow-up tasku v dashboardu a akce průvodce follow_up
status: done
archived: true
workflow: build-test-review
depends_on: [GUIDE-S02-T03]
---

## Zadání
Dashboard a AI průvodce mají umět totéž co `factory task follow-up ID --body TEXT [--title TEXT] [--run]`, a to se stejnou logikou, ne s kopií.

Zadání:
1. Zápisové API dashboardu dostane endpoint pro follow-up hotového tasku. Volá stejnou funkci jako CLI (kontrola `not_done`, `follows: ID`, převzetí vlastních writes a workflow, výchozí titulek „Navazuje na ID: …“, volitelně commit backlogu a spuštění). Pokud logika žije jen ve vrstvě CLI, vytáhni ji do sdílené funkce a CLI na ni přepoj.
2. Detail hotového tasku dostane tlačítko **Navázat follow-upem** s formulářem (titulek, zadání, volba „commitnout a spustit“).
3. Průvodce dostane nový druh akce `follow_up` (`task`, `body`, volitelně `title`, `run`). Karta ukáže náhled včetně převzatých writes a workflow a provede se přes nový endpoint se stejnou ochranou jako ruční akce. Aktualizuj prompt semínka `guide` a kapitolu příručky o průvodci.
4. Detail tasku zobrazí `follows` a `followed_by` s odkazy.

Hotovo znamená:
- Test, že CLI i endpoint dají pro stejný vstup stejný výsledek, a test odmítnutí tasku, který není hotový.
- Test, že akce `follow_up` bez potvrzení nic nezapíše; Vitest karty a browser test potvrzení.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

Mimo rozsah: změny chování CLI kromě přepojení na sdílenou funkci.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/106 · náklady $3.43
