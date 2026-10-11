# HAIFA-REFINEMENT-T11 – Redesign obrazovky Tasku před spuštěním

Detail tasku (`#/r/<repo>/backlog/<task-id>`, komponenta `TaskDetail.vue`) má nové
rozvržení. Jde jen o frontend, API ani Python se nemění.

## Hlavička

- Kód, název a stav tasku v jednom řádku, tlačítka vpravo: **Spustit** (zvýrazněné),
  **Upravit**, **Zrušit** (červené). Dlouhý název se zalomí, tlačítka nepřekrývá.
- Pod názvem je cesta k souboru (drobným písmem) a případné chyby souboru jako žluté
  varování.

## Banner připravenosti

Nový pruh pod hlavičkou (`data-test="run-readiness"`) říká, jestli jde task spustit:

- zelený **Připraveno ke spuštění · workflow …**,
- žlutý **Před spuštěním je potřeba:** se seznamem důvodů (chybí workflow, nesplněné
  závislosti, chyby souboru),
- šedý pro hotový, zrušený, běžící task nebo task v review (u běžícího odkaz na
  poslední běh).

Banner je jen informační, tlačítko Spustit se řídí stejně jako dřív.

## Dva sloupce

- **Hlavní sloupec:** Zadání, Běhy (s počtem) a PR (s počtem). Při úpravě nahradí
  kartu Zadání formulář.
- **Boční sloupec:**
  - karta **Spuštění** – workflow (vlastní nebo zděděné), výběr a přiřazení workflow,
    tlačítko „Upravit a navrhnout workflow“, auto-merge, writes jako štítky
    a auto continue. Samostatná sekce Workflow zmizela.
  - karta **Vazby** – Závisí na, Blokuje a Související pod sebou s počty. Vazbu jde
    přidat i klávesou Enter.

Pod šířkou 1100 px se sloupce složí pod sebe.
