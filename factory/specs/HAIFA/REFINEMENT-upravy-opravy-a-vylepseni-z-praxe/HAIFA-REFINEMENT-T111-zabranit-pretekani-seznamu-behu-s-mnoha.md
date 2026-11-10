# Seznam běhů s mnoha fázemi

Seznam musí zobrazit všechny fáze ve vzestupném pořadí `seq`, včetně tooltipů a dosažitelnosti klávesou Tab. Počet fází nesmí zvětšovat šířku dokumentu.

## Rozložení

- `PhaseDots` má šířku 152 px, nejvýše šířku rodiče, a zalamuje ikony pomocí flexboxu.
- Sloupec fází má požadovanou šířku 172 px včetně odsazení buněk.
- Odkaz tasku má omezenou šířku a zalamuje i dlouhé řetězce bez mezer. Celý název zůstává viditelný.
- Tabulku obaluje oblast „Seznam běhů“ s `overflow-x: auto` a `tabindex="0"`. Na úzké obrazovce se posouvá pouze tato oblast. Dokument nemá globální zákaz horizontálního posunu ani oříznutý obsah.
- Kliknutí na řádek, odkazy, archivace, vrácení z archivu a mazání zachovávají dosavadní chování.
- Horní lišta i její skupina ovládacích prvků se při nedostatku místa zalamují, aby na úzkém viewportu samy nerozšiřovaly dokument.

## Regrese

Komponentové testy kontrolují 100 fází, jejich pořadí, popisky, tooltipy, focus a události řádku. Browser test nad distribuovanými soubory používá syntetická API data, 100 fází v obráceném vstupním pořadí a dlouhý název bez mezer. Při šířkách 1366 a 390 px měří šířku dokumentu vůči viewportu, skutečné zalomení a geometrii všech ikon, lokální posun, průchod Tab, tooltip a akce.

Přímým uživatelem `PhaseDots` je pouze `RunsList`; přímým uživatelem seznamu je `RunsView`. Související testy jsou `PhaseDots.test.ts`, `RunsList.test.ts`, `RunsView.test.ts`, `App.test.ts` a browserové scénáře seznamu v `test_f3_browser.py`. Vyhledávání proběhlo v celém repozitáři včetně `aifactory/tests/`.
