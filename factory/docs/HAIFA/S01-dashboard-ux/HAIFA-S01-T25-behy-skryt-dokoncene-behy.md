# HAIFA-S01-T25: Běhy – skrýt dokončené běhy

## Co se změnilo

V liště filtrů na obrazovce Běhy přibyl přepínač **Skrýt dokončené**. Když je zapnutý,
seznam schová běhy ve stavu úspěch. Běžící, neúspěšné, přerušené a zastavené běhy
zůstanou vidět.

- Výchozí stav je vypnuto. Volba se ukládá do `localStorage` pod klíčem
  `haifa.runs.hideDone` (`'1'` nebo `'0'`).
- Přepínač filtruje jen na klientu (`visibleRuns` v `lib/runs.ts`) a kombinuje se
  s filtry Stav a Task, které se dál posílají na `/api/runs`. API se nezměnilo.
- Když přepínač skryje všechny běhy, prázdný stav ukáže kolik, např.
  „Žádné běhy (skryté dokončené: 3)“.
- Součty nákladů (`CostTotals`) se berou z `totals` ze serveru, takže dál zahrnují
  všechny běhy.

## Soubory

- `aifactory/web/src/lib/runs.ts`: `HIDE_DONE_KEY`, `loadHideDone`, `saveHideDone`,
  `visibleRuns`
- `aifactory/web/src/components/runs/RunsList.vue`: checkbox, prop `hideDone`,
  emit `update:hideDone`
- `aifactory/web/src/views/RunsView.vue`: stav přepínače a jeho uložení
- testy: `lib/runs.test.ts`, `components/runs/RunsList.test.ts`, `views/RunsView.test.ts`
- přebuildovaný frontend v `aifactory/src/aifactory/web/static/`
