# HAIFA-S01-T25: Běhy – skrýt dokončené běhy

## Zadání

Na obrazovku Běhy přidat přepínač „Skrýt dokončené“. Když je zapnutý, seznam neukazuje
běhy ve stavu `succeeded` (úspěch). Běžící, neúspěšné, přerušené a zastavené běhy zůstanou
vidět. Výchozí stav je vypnuto, prohlížeč si volbu pamatuje (localStorage).

## Návrh

- `lib/runs.ts`: `HIDE_DONE_KEY = 'haifa.runs.hideDone'`, `loadHideDone()`,
  `saveHideDone()` (stejný vzor jako `loadShowDone` v `lib/review.ts`) a
  `visibleRuns(runs, hideDone)`.
- `components/runs/RunsList.vue`: nová prop `hideDone`, checkbox `data-test="hide-done"`
  v liště filtrů, emit `update:hideDone`. Tabulka ukazuje `visibleRuns(...)`. Prázdný
  stav uvádí počet skrytých běhů.
- `views/RunsView.vue`: drží `hideDone` (počáteční hodnota z `loadHideDone`) a při změně
  volá `saveHideDone`. API se nemění. Filtrování probíhá jen na klientu, takže se
  kombinuje s filtry stavu a tasku, které dál jdou na server.
- `CostTotals` dál dostává `totals` ze serveru, takže součty počítají se všemi běhy.

## Testy

- `lib/runs.test.ts`: `visibleRuns` a paměť volby.
- `RunsList.test.ts`: přepínač a prázdný stav s počtem skrytých běhů.
- `RunsView.test.ts`: výchozí stav, uložení a obnovení volby, kombinace s filtry
  a nezměněné součty.

## Build

`just web-build` → `aifactory/src/aifactory/web/static/`.
