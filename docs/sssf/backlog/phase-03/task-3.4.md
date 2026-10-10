Doplň obrazovku Backlog o graf závislostí, spuštění tasku a přepínač auto-continue u modulu a stepu.

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Done means:
- Graf závislostí modulu nebo stepu: uzly jsou tasky se stavem, hrany `depends_on`. Klik na uzel otevře detail tasku.
- Tlačítko Spustit u tasku s volitelnou poznámkou volá tutéž funkci core jako `factory task run`. Před spuštěním UI ukáže varování na necommitnutou konfiguraci (D4) a nesplněné závislosti s možností spustit přesto (`--force`).
- Přepínač auto-continue u modulu a stepu zapisuje stejné nastavení jako CLI.
- Běh spuštěný z UI běží na pozadí serveru a server přitom dál odpovídá.
- Testy API s falešným harnessem: spuštění z API vytvoří běh v `task_runs`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: plánovač napříč moduly.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
