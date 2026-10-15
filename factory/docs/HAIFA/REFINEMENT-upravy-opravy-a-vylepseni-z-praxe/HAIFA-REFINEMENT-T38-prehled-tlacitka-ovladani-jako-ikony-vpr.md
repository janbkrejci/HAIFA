# HAIFA-REFINEMENT-T38: Přehled – tlačítka ovládání jako ikony vpravo nahoře

## Co se změnilo a proč

Karty repozitářů na Přehledu byly zbytečně vysoké. Široká textová tlačítka ovládání továrny zabírala vlastní řádek a cesta k repu se vypisovala v hlavičce. Repo v klidu navíc vypadalo jinak než ostatní karty.

Teď:

1. **Tlačítka jako ikony vpravo nahoře.** Spustit továrnu, Pauza, Pokračovat a Stop jsou malé ikonové tlačítka (26 × 26 px) v pravém horním rohu karty, hned vedle menu (`RepoMenu`). Název akce ukáže tooltip (`components/ui/Tooltip`) a pro čtečky obrazovky ho nese `aria-label`. Podmínky zobrazení, spinner, potvrzení u Stop, zprávy, chyby i atributy `data-test` (`factory-start`, `factory-pause`, `factory-resume`, `factory-stop`, `factory-start-message`, `factory-control-error`) zůstaly beze změny. Repo v klidu má stejnou hlavičku.
2. **Poslední aktivita je vždy dole.** Na kartě i u repa v klidu je „Poslední aktivita“ posledním prvkem.
3. **Jednotné pozadí.** Všechny karty mají solidní pozadí `var(--panel)` jako repo v klidu.
4. **Cesta v tooltipu.** Cesta k repu se už nevypisuje. Ukáže ji tooltip po najetí na název repa (nebo při fokusu).

## Kde to je

- `aifactory/web/src/components/overview/RepoActions.vue` (nový): ikonová tlačítka, potvrzovací dialog Stop a volání API. Výsledek akce posílá událostí `feedback` (`{message, error}`) a po dokončení emituje `changed`.
- `aifactory/web/src/components/overview/feedback.ts` (nový): typ `ControlFeedback` a prázdná hodnota `NO_FEEDBACK`.
- `aifactory/web/src/components/overview/RepoControls.vue`: už jen stav pod hlavičkou, tedy průběh stopu nebo pauzy, výsledek posledního tlačítka (prop `feedback`), chyby a souhrn tasků se sloty. Tlačítka v něm nejsou. Prop `compact` zanikl.
- `aifactory/web/src/components/overview/RepoCard.vue`: hlavička obsahuje název s tooltipem a vpravo `RepoActions` s `RepoMenu`. Pozadí je `var(--panel)`.
- `aifactory/web/src/views/OverviewView.vue`: řádek repa v klidu je sloupec. Nahoře je hlavička (název s tooltipem, „v klidu“, tlačítka, menu), pod ní `RepoControls` a dole poslední aktivita. Výsledek tlačítek se drží po repech (`feedback[repo.id]`).

## Jak ověřit

- `just web-test`, nebo samostatně `bun run test src/components/overview/RepoActions.test.ts src/components/overview/RepoControls.test.ts src/components/overview/RepoCard.test.ts src/views/OverviewView.test.ts src/App.test.ts` v `aifactory/web`.
  - `RepoActions.test.ts`: podmínky zobrazení, tlačítka bez textu s `aria-label` a tooltipem, spinner, zprávy a chyby přes `feedback`, potvrzení Stop.
  - `RepoControls.test.ts`: stav stopu a pauzy, zobrazení `feedback` a souhrn tasků.
  - `RepoCard.test.ts`: tlačítka a menu v hlavičce, poslední aktivita jako poslední prvek a cesta jen v tooltipu. Kontroluje i to, že zpráva a chyba tlačítka dojdou z hlavičky do `RepoControls` na kartě.
  - `App.test.ts`: repo v klidu na `#/overview` nemá vypsanou cestu a ukáže ji v tooltipu nad názvem. Jeho tlačítka jsou ikony s `aria-label` vedle menu a „Poslední aktivita“ je poslední. Po kliknutí na Spustit továrnu se v řádku objeví zpráva.
- Ručně v `just dash`: najet myší na ikony a na název repa, spustit a zastavit továrnu a porovnat pozadí karet a rep v klidu.
- Statický build `aifactory/src/aifactory/web/static/` se v tomto běhu nepřegeneroval, protože není mezi povolenými cestami. Změnu v dashboardu ukáže až `just web-build`.
