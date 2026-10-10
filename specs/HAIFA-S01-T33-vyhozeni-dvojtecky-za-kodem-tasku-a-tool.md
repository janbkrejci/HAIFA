# HAIFA-S01-T33: Vyhození dvojtečky za kódem tasku a tooltipu nad ním

## Cíl
- Za kódem tasku (např. `HAIFA-S01-T01`) se před názvem nepíše dvojtečka, jen mezera.
- Nad kódem tasku se nezobrazuje tooltip s názvem tasku (`CodeTip`).

## Změny
- `ReviewList.vue`, `ReviewDetail.vue`, `RunsList.vue`, `RunDetail.vue`, `CostTotals.vue`: `ID: Název` → `ID Název`, bez `CodeTip` nad kódem tasku.
- `lib/runs.ts` `taskOptionLabel`: volba filtru `ID Název`.
- `TreeNode.vue` (řádek tasku), `KanbanBoard.vue` (karta), `TaskDetail.vue` (hlavička, Závisí na, Blokuje, Související), `RunDialog.vue` (nesplněné závislosti), `TaskForm.vue` (nadpis „Upravit <kód>“): bez `CodeTip` nad kódem tasku.
- Tooltip zůstává nad kódy projektů a stepů (kontejner ve stromu, hlavička grafu, sloupec projektu v review) a nad odkazem na PR v detailu tasku (odkaz zobrazuje číslo a název PR, ne kód tasku).
