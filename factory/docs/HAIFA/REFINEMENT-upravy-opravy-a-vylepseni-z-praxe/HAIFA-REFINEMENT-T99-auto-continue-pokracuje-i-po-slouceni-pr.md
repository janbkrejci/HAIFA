# T99: Auto-continue po externím sloučení

Pokud se PR sloučí přímo na GitHubu nebo v Azure DevOps, další periodický refresh
dashboardu obnoví jeho poslední řetěz zastavený na `not_merged`. Opakovaný refresh
řetěz znovu nespustí. Další připravený task běží přes dashboard launcher jako samostatný
proces; zachovává nastavení auto-continue i příznak `--auto` původního řetězu.

Task, jehož nejnovější PR je sloučený, fronta nespustí znovu ani tehdy, když má v base
ještě `status: todo`. V přeskočených položkách má důvod `merged_outside` a doporučení
spustit `factory backlog sync`. Platí to i pro „Spustit továrnu“.

Závislé tasky čekají, dokud backlog v base neobsahuje `status: done`.
Je proto potřeba provést `factory backlog sync` a sloučit jeho změny běžným postupem;
dashboard tento sync PR automaticky nevytváří ani neslučuje.

Regresní testy pokrývají launcher, jednorázové pokračování pouze po `not_merged`,
zachování `--auto`, přeskočení sloučeného tasku i blokování jeho závislostí.
