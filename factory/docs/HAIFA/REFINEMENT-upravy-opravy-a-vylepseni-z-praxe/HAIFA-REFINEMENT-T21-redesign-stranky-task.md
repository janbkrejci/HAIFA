# HAIFA-REFINEMENT-T21: redesign stránky Task

## Co se změnilo a proč

Stránka tasku měla duplicitní ovládání: workflow i vazby šly měnit jak v read-only detailu, tak ve formuláři, a návrh agenta vyžadoval výběr harnessu a modelu plus samostatné potvrzení. Teď se úpravy dělají na jednom místě, ve formuláři, a návrh agenta je jedno velké zelené tlačítko **„Vylepšit agentem“** (ikona `Wand2` z `lucide-vue-next`).

### „Vylepšit agentem“ (`ImproveButton.vue`, nahrazuje `TaskAdvice.vue`)

- Nic se nevybírá. Frontend posílá `POST /api/backlog/task-advice` jen s `task_id` a `draft`, bez `harness` a `model`.
- Backend (`workflow_advice.py`, `AdviceManager.start`) pak vezme agenta, se kterým by task sám běžel: `harness_settings.effective_override(ctx["effective"], None)` (task, předci, config, počítač). Když z toho harness nevyjde, použije se původní `_resolve` (výchozí nastavení počítače, jinak plan agent z rosteru). Explicitní `harness`/`model` v API dál fungují.
- Job (`Job.to_dict`) nově vrací `advisor` (`harness`, `model`, `thinking`).
- Během běhu má tlačítko spinner a text „Agent vylepšuje…“, pole formuláře jsou zamčená (`<fieldset :disabled="parameterBusy">`) a Uložit je vypnuté.
- Výsledek se zapíše rovnou do formuláře (`applyParameters`), bez kroku „Použít návrh“. Pod tlačítkem zůstane zavíratelná poznámka: důvod, `harness · model · thinking` a cena/tokeny („Provider cenu nevykázal“ místo `$0.0000`).
- Když se zadání během běhu změní, job se zahodí s hláškou „Zadání se změnilo. Spusť vylepšení znovu.“
- Zablokované tlačítko vysvětluje důvod v tooltipu (`blocker`), místo dřívějšího odstavce `advice-blocker`.
- Styl tlačítka je globální třída `btn-improve` ve `style.css`.

### Detail (`TaskDetail.vue`)

- V hlavičce přibylo „Vylepšit agentem“ (jen mimo editaci). Kliknutí otevře formulář s `autoImprove = true` a agent se v něm spustí hned po připojení (`autostart`). „Upravit“ otevře formulář bez agenta. Pro task ve stavu done, cancelled, running nebo in review je tlačítko vypnuté s tooltipem „… už nejde měnit.“
- Odstraněno: výběr workflow s tlačítkem „Přiřadit“ (událost `assign-workflow` a `onAssign` v `BacklogView.vue`), tlačítko „Upravit a navrhnout workflow“ a pole „Přidat“ pro závislosti a související tasky. Odebrání vazby křížkem v detailu zůstalo.
- Karta „Spuštění“ se jmenuje „Nastavení“.

### Formulář (`TaskForm.vue`)

Pořadí shora: nadpis + „Vylepšit agentem“ vpravo; u nového tasku Step a Kód vedle sebe; Titulek; Zadání (14 řádků); Workflow a „Navrhnout workflow“ (`WorkflowAdvice` zůstal); sbalené **„Další nastavení“** (`details[data-test="advanced"]`) se statusem a auto-merge (jen úprava), writes, „Závisí na“, „Související“ a parametry. Maximální šířka formuláře je 900 px.

„Další nastavení“ je rozbalené, když task v editaci používá cokoli z nich (status jiný než `todo`, vlastní auto-merge, writes, vazby nebo parametry), nebo když agent některé z těchto polí změnil. Parametr `thinking` má nově výběr z `THINKING_LEVELS`.

## Soubory

- Backend: `aifactory/src/aifactory/web/workflow_advice.py`
- Frontend: `aifactory/web/src/components/backlog/ImproveButton.vue` (nový), `TaskAdvice.vue` (smazán), `TaskDetail.vue`, `TaskForm.vue`, `aifactory/web/src/views/BacklogView.vue`, `aifactory/web/src/style.css`
- Build: `aifactory/src/aifactory/web/static/` (`index.html` a nové hashované assety)
- Testy: `aifactory/tests/web/test_web_task_advice.py` (`test_advisor_inherits_task_settings`), `aifactory/tests/e2e/test_f3_browser.py` (vazba se přidává přes Upravit → Další nastavení), `ImproveButton.test.ts` (nový), `TaskAdvice.test.ts` (smazán), `TaskDetail.test.ts`, `TaskForm.test.ts`, `BacklogView.test.ts`, `BacklogView.spinner.test.ts`

## Ověření

```
just lint && just typecheck
just pytest tests/web/test_web_task_advice.py
just web-test
just pytest tests/e2e/test_f3_browser.py -n0
```

Ručně v dashboardu (`just dash`): otevři task ve stavu K řešení a klikni na „Vylepšit agentem“. Otevře se formulář, pole se zamknou a po doběhnutí agenta je v nich návrh a pod tlačítkem poznámka s agentem z nastavení tasku. Návrh ulož tlačítkem Uložit, nebo ho zahoď tlačítkem Zrušit. U hotového tasku je tlačítko šedé a tooltip vysvětlí proč.

Endpoint `GET /api/backlog/task-advice/options` se nezměnil, ale tento formulář ho už nevolá.
