---
id: HAIFA-REFINEMENT-T93
title: "Topbar: čipy jen jako ikona stavu s tooltipem"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/web/src/components/UpdateChip.vue, aifactory/web/src/components/OverviewReadiness.vue, aifactory/web/src/components/OverviewReadiness.test.ts, aifactory/web/src/components/LibraryChip.vue, aifactory/web/src/components/LibraryChip.test.ts, aifactory/web/src/components/UncommittedBanner.vue, aifactory/web/src/components/UncommittedBanner.test.ts, aifactory/web/src/components/LimitsBar.vue, aifactory/web/src/components/LimitsBar.test.ts, aifactory/web/src/components/ui/, aifactory/src/aifactory/guide/, aifactory/src/aifactory/web/static/]
---

## Zadání
Čipy v topbaru (`aifactory/web/src/App.vue`, `.topbar-right`) zabírají moc místa, protože vypisují celý text: „Systém je aktuální“, „Systém v pořádku“, „Knihovna OK“, „Necommitnutá konfigurace“, „Necommitnutý backlog (N)“, „Nakonfigurujte harnessy“ a další. Zmenši je na kompaktní kulatý čip, který ukazuje jen ikonu. Co čip říká, vysvětlí tooltip (`components/ui/Tooltip.vue`) a `aria-label`.

Co udělat:
- `components/UpdateChip.vue`: jen ikona (Spinner, Check, ArrowUpCircle, TriangleAlert). Dnešní text `label` a `hint` přesuň do tooltipu a `aria-label`. Barvy stavů zůstávají.
- `components/OverviewReadiness.vue` v režimu `chip`: loading a checking ukazují spinner, success ikonu Check, warning ikonu TriangleAlert. Tooltip říká, co stav znamená a co udělá klik („Systém v pořádku – kliknutím spustíš kontrolu znovu“, „Nalezeny problémy – kliknutím otevřeš seznam problémů“). Režim bez `chip` (stránka Přehled) se nemění.
- `components/LibraryChip.vue`: ikona Library u OK a TriangleAlert u chybějící knihovny, vysvětlení v tooltipu. Odkaz na knihovnu zůstává.
- `components/UncommittedBanner.vue` v režimu `chip`: ikona TriangleAlert a malý počet změn jako badge, text („Necommitnutý backlog“, „Necommitnutá konfigurace“, seznam souborů) v tooltipu. Panel backlogu i přímý commit konfigurace fungují dál stejně. Banner mimo topbar se nemění.
- `components/LimitsBar.vue`: stavy loading a empty („Nakonfigurujte harnessy“) mají jen ikonu s tooltipem. Lišty limitů se nemění.
- Sjednoť vzhled: stejná výška a velikost čipu (kruh nebo krátký ovál kolem ikony), stejné barvy stavů jako dnes (zelená OK, modrá probíhá, oranžová a červená problém). Ideálně jedna sdílená třída nebo malá komponenta, například `components/ui/StatusIconChip.vue`.

Tvrdá omezení:
- Zachovej všechny dnešní `data-test` atributy (`update-chip`, `readiness-*`, `library-chip-ok`, `library-chip-missing`, `backlog-chip`, `config-chip`, `harness-settings-open` …), protože na ně stojí unit testy i prohlížečový test knihovny.
- Text, který z čipu zmizí, musí být dostupný v tooltipu i v `aria-label`, aby se dal najít čtečkou a v testech.
- Uprav testy, které kontrolují viditelný text čipů (`App.test.ts`, `LibraryChip.test.ts`, `LimitsBar.test.ts`, `OverviewReadiness.test.ts`, `UncommittedBanner.test.ts`). Zkontroluj (grep) i příručku v `aifactory/src/aifactory/guide/`, kde se texty čipů zmiňují (kapitoly 03, 06, 08). Kde příručka popisuje text čipu, oprav ji na ikonu s tooltipem, aby dál procházel test souladu příručky s UI.
- Na konci přegeneruj statický build `just web-build` (`aifactory/src/aifactory/web/static/`).

Mimo rozsah: nový čip System info (samostatný task), změna chování čipů po kliknutí, tlačítko AI průvodce.

Hotovo znamená:
- V topbaru je každý stavový čip jen ikona (u necommitnutých změn ikona s počtem) a po najetí myší ukáže tooltip s dnešním vysvětlením.
- Kliknutí na čipy dělá totéž co dřív (update, kontrola znovu, problémy, knihovna, panel backlogu, commit konfigurace, dialog harnessů).
- Prochází vitest pro upravené komponenty a `App.test.ts`, test souladu příručky s UI a prohlížečový test knihovny.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/182 · náklady $0.00
