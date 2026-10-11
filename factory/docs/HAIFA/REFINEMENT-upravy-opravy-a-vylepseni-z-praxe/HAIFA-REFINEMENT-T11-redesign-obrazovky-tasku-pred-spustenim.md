# HAIFA-REFINEMENT-T11 – Redesign obrazovky Tasku před spuštěním

Detail tasku (`#/r/<repo>/backlog/<task-id>`) má nové rozvržení: hlavička s akcemi,
banner připravenosti a dva sloupce místo jednoho dlouhého. Změna je jen ve frontendu,
API, Python ani rozhraní komponenty (props, emits) se nemění. Všechny `data-test`
háčky zůstaly.

## Co se změnilo

### Hlavička
- Kód, název, `StateChip` a vpravo tlačítka **Spustit**, **Upravit** (ikona tužky)
  a **Zrušit**. Řádek se zalamuje, takže dlouhý název tlačítka nepřekryje.
  Podmínky pro zobrazení a zakázání tlačítek jsou stejné jako dřív.
- Pod názvem je cesta k souboru (`data-test="path"`, drobným písmem). Chyby souboru
  (`task-issues`) jsou hned pod ní jako žluté varování s ikonou.

### Banner připravenosti (`data-test="run-readiness"`, atribut `data-tone`)
Nový computed `readiness` v `TaskDetail.vue` určí tón a text:
- `muted` – task je hotový nebo zrušený (text stejný jako tooltip Spustit), případně
  běží nebo čeká na review (`<Task> je ve stavu …`, s odkazem na poslední běh).
- `warn` – **Před spuštěním je potřeba:** a seznam důvodů
  (`data-test="readiness-reason"`): chybějící workflow (`NO_WORKFLOW_HINT`), každá
  nesplněná závislost z `blocked_by` (přes `unmetLine`), chyby souboru.
- `ok` – **Připraveno ke spuštění · workflow <název>**.

Banner jen informuje. Tlačítko Spustit se řídí stejnou logikou jako dřív (`runBlocked`).

### Dva sloupce (`.body-grid`, pod 1100 px pod sebou)
- **Hlavní sloupec:** karty Zadání, Běhy (s počtem) a PR (s počtem). Během úpravy
  nahradí kartu Zadání formulář `TaskForm`. Prázdné zadání zobrazí „Zadání je prázdné.“
- **Boční sloupec (320 px):**
  - **Spuštění** – Workflow (vlastní / `(zděděno)` / žluté `bez workflow`), pod ním
    výběr workflow s tlačítkem Přiřadit a tlačítko „Upravit a navrhnout workflow“.
    Dál Auto-merge, Writes jako štítky a Auto continue s přepínačem. Samostatná
    sekce Workflow zmizela.
  - **Vazby** – Závisí na, Blokuje a Související pod sebou, každá s počtem. Do polí
    pro přidání vazby jde potvrdit i klávesou **Enter**.

## Soubory
- `aifactory/web/src/components/backlog/TaskDetail.vue`: šablona, computed
  `readiness` a `adviceBlocked`, obsluha Enteru, nové ikony z `lucide-vue-next`, styly.
- `aifactory/web/src/components/backlog/TaskDetail.test.ts`: nové testy pro banner
  (ok, warn bez workflow, warn s nesplněnými závislostmi, muted pro hotový task),
  pro skrytí zadání při úpravě a pro přidání závislosti Enterem.
- `aifactory/src/aifactory/web/static/` (`index.html`, `assets/index-*.js|css`):
  přegenerovaný build.

## Ověření
- `just web-test` (vitest včetně nových testů), `just check`, `just e2e`
  (`test_f3_browser.py`, `test_workflow_advice_browser.py` používají stejné háčky).
- Ručně: `just dash`, otevřít detail tasku při šířce okna ~1400 px a ~900 px.
  Tlačítka v hlavičce nesmí překrývat dlouhý název a pod 1100 px se boční sloupec
  přesune pod hlavní.
