---
id: GUIDE-S01-T04
title: Nastavení projektu a stepu - reorganizace
status: done
archived: true
workflow: build-test-review
depends_on: []
---

## Zadání
Nastavení projektu (a stepu) je teď na stránce grafu, částečně schované pod grafem závislostí (`ContainerSettings` v `BacklogView.vue` pod `DependencyGraph`). Ve stromu backlogu je zatím jen panel přepínačů (tlačítko s posuvníky v `TreeNode.vue`, dvakrát `AutoContinueToggle`), a to jen pro auto-continue a auto-merge.

Vytáhnout nastavení na úroveň stromu backlogu: z řádku projektu/stepu ve stromu se otevře celé nastavení, ne jen tyto dva přepínače.

## Požadavky
- Z řádku projektu i stepu ve stromu backlogu jde otevřít celé nastavení: titulek a klíče `index.md`, které panel `ContainerSettings` umí dnes (workflow, writes, harness/model, quota_switch, auto-continue atd.), včetně zděděných hodnot a jejich původu. Panel nabízí jen klíče z `editable_keys` daného kontejneru, stejně jako dnes.
- Stávající přepínače auto-continue a auto-merge zůstanou dostupné na stejném místě: buď jako součást nového panelu, nebo vedle něj. Nesmí vzniknout dvě nekonzistentní místa pro tutéž hodnotu. `ContainerSettings` dnes umí `auto_continue`, ale ne `auto_merge`. Pokud se přepínače přesunou do panelu, musí auto-merge (vlastní hodnota / zdědit) fungovat stejně jako dnes v `TreeNode.vue`.
- Uložení používá stávající API (`editContainer` / `factory backlog edit`). Backend se nemění. Po uložení se strom obnoví (odznaky auto/merge, hodnoty).
- Chyby načtení a uložení se zobrazí u panelu ve stromu. Během uložení se zobrazí spinner jako dnes.
- Na stránce grafu nastavení už nebude pod grafem. Pokud tam zůstane, tak jen jako odkaz na strom, ne duplicitní formulář.

## Akceptační kritéria
- Ve stromu backlogu lze u projektu i stepu změnit a uložit nastavení. Změna se projeví v `index.md` a ve stromu.
- Auto-continue a auto-merge fungují dál.
- Testy komponent (`TreeNode`/`BacklogTree`, `ContainerSettings`, `BacklogView`) jsou upravené podle nového umístění a procházejí.
- Prohlížečový test `aifactory/tests/e2e/test_f3_browser.py` hledá dnes panel `[data-test="container-settings"]` na stránce grafu. Je upravený na nové místo ve stromu a prochází.
- Statický build dashboardu je přegenerovaný (`just web-build`).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/100 · náklady $3.36
