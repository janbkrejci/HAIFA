# HAIFA-S01-T37: Vytvoření stepu v dashboardu

V hlavičce Backlogu je vedle tlačítek pro nový projekt a task také **Nový step**. Je dostupné ve stromu i v kanbanu.

1. Klikni na **Nový step**.
2. Vyber nadřazený projekt podle kódu a názvu.
3. Vyplň kód stepu, název a případně popis. Klikni na **Založit**.

Po vytvoření se otevře graf nového stepu. Při chybě se zobrazí důvod a vyplněný formulář zůstane zachovaný. **Zrušit** vrací do Backlogu. Změna projektu vymaže formulář, aby nezůstal kód předchozího projektu.

Pokud zatím není žádný projekt, obrazovka nabídne jeho založení. U konfigurace bez mezilehlé úrovně step se tlačítko nezobrazuje. Názvy tlačítek a polí respektují nastavené úrovně backlogu.

Vytvoření stepu z grafu projektu je nadále dostupné a má projekt předvyplněný.

## Ověření

Prošly cílené testy BacklogView, jeho spinnerů a routingu (65 testů), produkční build včetně Vue/TypeScript kontroly, striktní mypy a Ruff lint i kontrola formátování. Testy kontrolují i zachování rozepsaného formuláře při obnovení seznamu projektů. V prohlížeči byl ověřen výběr projektu, zobrazení formuláře a návrat přes Zrušit; zkušební step se neukládal.

![Tlačítko Nový step v Backlogu](../aifactory/validation/results/HAIFA-S01-T37-new-step-button.png)

![Formulář stepu po výběru projektu](../aifactory/validation/results/HAIFA-S01-T37-new-step-form.png)
