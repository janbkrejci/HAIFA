---
id: HAIFA-REFINEMENT-T67
title: "Přehled: chip Běží na prvním místě"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/lib/overview.ts, aifactory/web/src/lib/overview.test.ts, aifactory/web/src/views/OverviewView.test.ts, aifactory/web/src/components/overview/RepoControls.test.ts, aifactory/web/src/components/overview/RepoCard.test.ts, aifactory/src/aifactory/web/static/]
---

## Zadání
Na Přehledu má být stavový chip Běží v souhrnu tasků vždy první, pokud existují běžící tasky. Platí pro souhrn repozitáře i jednotlivých projektů (sdílené taskSummary). Pořadí ostatních chipů zachovat; nulové počty se nadále nezobrazují. Globální BOARD_STATES a pořadí kanbanu neměnit. Horní součty už Běží první mají. Stačí malá úprava sdíleného pořadí taskSummary, přizpůsobit existující testy pořadí bez nové testovací infrastruktury. Znovu sestavit dodávaný statický frontend přes just web-build. Ověřit just lint, just typecheck, just web-test a pouze browser test změněné obrazovky: just pytest tests/e2e/test_multi_repo_browser.py -n0. Ne celou sadu uvnitř factory běhu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
