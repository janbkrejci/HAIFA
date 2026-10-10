Implementuj obrazovku Běhy: běžící a dokončené běhy tasků, jejich fáze, trace a náklady, a zastavení běhu (tabulka „Dashboard“ v `docs/product-brief.md`).

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`. Zdroj: pohledy visualizeru `vendor/sssf/apps/visualizer/src/`.

Done means:
- Seznam běhů z `task_runs` a trace DB: task, workflow, stav, začátek, doba, tokeny, náklady, odkaz na PR. Filtr podle stavu a tasku.
- Detail běhu: fáze v pořadí se stavem, harnessem a modelem, výsledky gates, envelopes a tool calls jako ve visualizeru.
- Tlačítko Zastavit ukončí běžící běh stejnou funkcí core, jakou používá CLI, a běh se označí jako zastavený.
- Součet nákladů za task a za celý backlog.
- Testy API s trace DB z fixture a unit testy komponent.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: živé aktualizace (3.7), spouštění běhů (3.4).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
