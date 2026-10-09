---
id: HAIFA-S01-T02
title: Vlastní dropdown místo nativního selectu
status: done
depends_on: [HAIFA-S01-T01]
---

## Zadání
Nahraď všech devět nativních `<select>` v dashboardu lepším dropdownem ve vzhledu dashboardu.

Where: `aifactory/web/src/` (`components/backlog/BacklogFilters.vue`, `components/backlog/TaskForm.vue`, `components/backlog/TaskDetail.vue`, `components/runs/RunsList.vue`, `components/settings/SettingsForm.vue`, `style.css`, `views/` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Filtr stavu v Backlogu, filtry stavu a tasku v Bězích, step, status a workflow ve formuláři tasku, workflow v detailu tasku a git provider a merge strategie v Nastavení používají jednu sdílenou komponentu. Otevřený seznam má vzhled dashboardu, ne systémový.
- Ovládání myší i klávesnicí: šipky, Enter, Esc, Tab a skok na položku podle prvních písmen. Klik mimo seznam ho zavře. Seznam leží nad horní lištou a neořízne ho rolovací kontejner.
- Ve formulářích se chová jako dnešní select: vázaná hodnota, zakázaný stav, chybový stav v Nastavení, popisek pro čtečky obrazovky. Atributy `data-test` zůstávají na stejných polích.
- Unit testy (vitest) komponenty (myš, klávesnice, vázaná hodnota) a upravené testy všech devíti míst.
- Prohlížečový test vybírá step novým dropdownem.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: vyhledávání v seznamu, výběr více hodnot.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/3 · náklady $2.99
