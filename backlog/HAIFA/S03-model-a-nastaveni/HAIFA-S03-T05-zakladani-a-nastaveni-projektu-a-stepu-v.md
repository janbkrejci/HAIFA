---
id: HAIFA-S03-T05
title: Zakládání a nastavení projektu a stepu v dashboardu
status: done
depends_on: [HAIFA-S01-T07, HAIFA-S03-T04]
---

## Zadání
Doplň do dashboardu zakládání a nastavení projektu a stepu. Na stránce grafu projektu nebo stepu jde upravit název a nastavení a z Backlogu jde založit nový projekt nebo step s kódem a názvem.

Where: `aifactory/web/src/` (`views/BacklogView.vue`, `components/backlog/`, `lib/backlog.ts`, `lib/router.ts` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Stránka grafu má panel Nastavení: název, `workflow`, `writes`, `test`, `source`, `target`, `specs_dir`, `docs_dir` a `auto_continue`. U každého klíče je vidět vlastní hodnota, nebo zděděná hodnota s původem. Zdědit vlastní hodnotu smaže.
- Popis z `index.md` je vidět jako markdown s Náhledem a Zdrojem.
- Backlog má akci Nový projekt a stránka projektu akci Nový step: formulář s kódem, názvem a popisem. Po založení se otevře graf nového projektu nebo stepu.
- Chyby validace se ukážou u formuláře a nic se nezapíše. Panel upozorní, že běhy použijí změnu až po commitu backlogu do base.
- Volání jdou na API dashboardu pro projekty a stepy (tytéž funkce core jako `factory backlog add` a `factory backlog edit`).
- Unit testy (vitest) panelu a formuláře. Prohlížečový test založí projekt a step, změní workflow stepu a založí v něm task.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: změna kódu, mazání projektu nebo stepu, editace popisu, commit z panelu.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/48 · náklady $3.04
