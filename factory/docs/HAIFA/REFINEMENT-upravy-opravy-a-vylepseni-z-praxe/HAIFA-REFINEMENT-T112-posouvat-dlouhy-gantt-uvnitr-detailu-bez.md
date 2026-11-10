# T112: Dlouhý Gantt se posouvá uvnitř detailu

Bloky fází v Ganttu detailu běhu mají i u dlouhého běhu čitelnou minimální šířku
(132 px) a mezi sebou mezeru. Dokončené, běžící ani čekající fáze se nepřekrývají.
Čekající fáze leží za poslední spuštěnou fází v pořadí kroků a nejsou naskládané u pravého
okraje přes sebe.

Když se kroky nevejdou, plátno Ganttu se rozšíří a posouvá se vodorovně jen oblast Ganttu
s osou. Popisky swimlanes zůstávají vlevo viditelné. Hlavička detailu, metadata a panel
vybrané fáze zůstávají v šířce okna. Osa se posouvá spolu se swimlanes a její popisky
sledují skutečné pozice bloků. Krátký běh vyplní dostupnou šířku bez posuvníku.

Testy: `waterfall.test.ts` (rozložení dlouhého a krátkého běhu, mezery, pořadí, osa),
`RunWaterfall.test.ts` a `RunDetail.test.ts` (jediná oblast posunu, čekající fáze, měření
šířky) a prohlížečový test `tests/e2e/test_run_waterfall_scroll_browser.py`. Ten na
syntetickém dlouhém běhu porovnává skutečné obdélníky bloků, `scrollWidth`/`clientWidth`
oblasti a šířku dokumentu, posune Gantt a vybere poslední fázi.
