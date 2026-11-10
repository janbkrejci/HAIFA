---
id: HAIFA-REFINEMENT-T112
title: Posouvat dlouhý Gantt uvnitř detailu bez překryvů kroků
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T111]
writes: [aifactory/web/src/lib/waterfall.ts, aifactory/web/src/lib/waterfall.test.ts, aifactory/web/src/components/runs/RunWaterfall.vue, aifactory/web/src/components/runs/RunWaterfall.test.ts, aifactory/web/src/components/runs/RunDetail.vue, aifactory/web/src/components/runs/RunDetail.test.ts, aifactory/tests/e2e/test_run_waterfall_scroll_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
V detailu běhu upravit RunWaterfall.vue a výpočet v aifactory/web/src/lib/waterfall.ts tak, aby velký počet kroků nezpůsoboval nečitelné zmenšení či překrývání bloků jedné swimlane. buildTimeline nyní při nedostatku místa stlačí i minimální šířky zpět do pevné procentní šířky. Zavést šířku plátna rostoucí podle potřeb rozložení a čitelnou minimální šířku bloků s mezerami; šířka samotná nesmí nahrazovat kontrolu skutečného nepřekrývání. Opravit také čekající fáze bez started_at, které RunWaterfall.vue nyní skládá po pěti pixelech přes sebe. Zachovat pořadí, rozdělení do swimlanes, význam časové osy, výběr fáze, tooltipy a značky nástrojů.

Horizontálně posouvat pouze oblast Ganttu včetně její osy. Detail běhu, hlavička a panel vybrané fáze musí zůstat v šířce viewportu. Podle potřeby upravit rozměrová omezení rodiče v RunDetail.vue. Nevytvářet samostatný nesynchronizovaný scrollbar pro každou swimlane a neřešit problém globálním skrytím přetékání. Krátké běhy mají dál využívat dostupnou šířku bez zbytečně širokého plátna.

Doplnit waterfall.test.ts a RunWaterfall.test.ts, případně RunDetail.test.ts, a browser test aifactory/tests/e2e/test_run_waterfall_scroll_browser.py se syntetickým dlouhým během. Zahrnout desítky krátkých dokončených kroků téhož vlastníka, opakované pokusy, běžící fázi i více čekajících fází. Browser test musí porovnávat skutečné obdélníky bloků, lokální scrollWidth/clientWidth a šířku dokumentu, potom posunout Gantt a vybrat poslední fázi. Bez živých modelů a služeb; přímé volající a existující testy vyhledat před změnou.

Hotovo znamená:
- Dokončené, běžící ani čekající bloky se v jedné swimlane nepřekrývají a zachovávají čitelnou minimální šířku i u dlouhého běhu.
- Dlouhý Gantt má funkční lokální horizontální posun, zatímco dokument a ostatní části detailu nepřetékají doprava.
- Po posunu lze kliknout na poslední fázi a zobrazit její detail; osa zůstává zarovnaná se všemi swimlanes.
- Krátký běh nevytváří zbytečný horizontální posun.
- Projdou just lint, just typecheck, just web-test a just pytest tests/e2e/test_run_waterfall_scroll_browser.py -n0; spustí se každý další editovaný testovací soubor.
- Proběhne just web-build a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
