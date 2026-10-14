# HAIFA-REFINEMENT-T21: redesign stránky Task — plán

## Cíl

1. Stránka tasku (detail i formulář přidání/úpravy) má méně inputů a méně duplicitních funkcí.
2. Vpravo nahoře je velké zelené tlačítko s ikonou kouzelné hůlky (SVG, `Wand2` z `lucide-vue-next`) **„Vylepšit agentem“**. Agent, model a thinking level se nevybírají: použijí se ty, které task zdědí (task → step → projekt → config → nastavení počítače), tj. stejné, se kterými by task běžel.
3. Stisk tlačítka v read-only detailu přepne do editačního formuláře a návrh v něm rovnou spustí.

## Analýza použitelnosti (současný stav → problém)

Detail (`aifactory/web/src/components/backlog/TaskDetail.vue`):
- Workflow jde změnit na třech místech: SelectMenu + „Přiřadit“ v kartě Spuštění, tlačítko „Upravit a navrhnout workflow“ a pole ve formuláři.
- Vazby mají vlastní inputy a tlačítka „Přidat“ (závisí na, související) a ještě se upravují i ve formuláři.
- Readonly pohled tak obsahuje 3 inputy a 5 akčních tlačítek, která dělají totéž co formulář.

Formulář (`TaskForm.vue`):
- Všechna pole mají stejnou váhu: titulek, status, workflow, zadání, dvě sekce návrhů agenta, auto-merge, writes + checkbox, vazby a „Další parametry“ (8 polí).
- `TaskAdvice.vue` chce po uživateli harness a model (2 selecty), pak vypíše celý návrh jako surový text a teprve tlačítko „Použít návrh do formuláře“ ho zapíše. Jsou to tři kroky a hodně šumu.
- Zadání (hlavní obsah) má jen `rows="6"`.

## Návrh

### A. Backend: návrh tasku se zděděným agentem

Soubor `aifactory/src/aifactory/web/workflow_advice.py`, `AdviceManager.start` (větev `if self.task_parameters:`):
- Když request **nemá** `harness` ani `model`, nastav
  `ctx["advisor"] = harness_settings.effective_override(ctx["effective"], None)` (převeď `ValueError` na `UsageError` jako v `_resolve`). `ctx["effective"]` už obsahuje zděděné `harness`/`model`/`thinking` z `context()` v `workflow/adaptive.py` (config settings → defaults předků → vlastní hodnoty tasku → parametry draftu). Když výsledek nemá `harness` (počítač nemá nastavení harnessů a nic se nezdědilo), použij dosavadní fallback `_resolve(repo, {})` (plan agent z rosteru).
- Explicitní `harness`/`model` v requestu se dál přijímají a validují jako dnes (API zůstává kompatibilní, testy `test_repeat_select_cost_and_save` dál platí).
- `recommend()` v `adaptive.py` už dělá `apply_agents_override(rc, ctx["advisor"])` a `OVERRIDE_KEYS` obsahuje `thinking`, takže thinking se propíše bez další změny. Ověř to testem.
- `Job.json()` doplní `"advisor": self.context.get("advisor")` (pro workflow advice bude `None`), aby UI mohlo ukázat, kdo návrh dělá (`claude · claude-opus-5-5 · medium`).
- Docstring `_resolve` a komentář upravit: výchozí volba je teď zděděné nastavení tasku, `_resolve` je fallback.
- Endpoint `/backlog/task-advice/options` nech beze změny (UI ho přestane volat; mazat není potřeba).

Testy v `aifactory/tests/web/test_web_task_advice.py`:
- Nový test `test_advisor_inherits_task_settings`: repo, kde step nebo projekt (`index.md` defaults) nebo task má `harness: codex`, `model: gpt-5.5`, `thinking: high`, k tomu `machine_settings(monkeypatch)`. `manager.start(repo, {"task_id": ..., "draft": {...}})` bez harness → `ctx["advisor"] == {"harness": "codex", "model": "gpt-5.5", "thinking": "high"}` (thinking přesně podle toho, co vrací `effective_override`). Podívej se, jak `make_repo` / fixtures zapisují defaults, a použij stejný postup.
- Ověř, že `test_advisor_defaults` dál prochází (bez zděděného harnessu a bez nastavení počítače → plan agent z rosteru). Kdyby se kvůli zděděné hodnotě z configu změnilo očekávání, uprav ho a změnu zdůvodni v komentáři.
- Assert, že job JSON obsahuje `advisor`.

### B. Frontend: tlačítko „Vylepšit agentem“

Nová komponenta `aifactory/web/src/components/backlog/ImproveButton.vue` (nahradí UI `TaskAdvice.vue`, logiku jobu z něj převezme):
- Props: `draft: Record<string, unknown>`, `taskId?: string`, `disabled?: boolean`, `blocker?: string` (text tooltipu, proč nejde spustit), `autostart?: boolean`.
- Emits: `result: [proposal: TaskProposal]`, `busy: [value: boolean]`.
- Vzhled: velké zelené tlačítko (`data-test="improve"`), ikona `<Wand2 :size="18" />`, text „Vylepšit agentem“; při běhu `<Spinner />` + „Agent vylepšuje…“ a `aria-busy`. Styl: `border-color: var(--green)`, `background: color-mix(in srgb, var(--green) 22%, var(--panel))`, `color: var(--green)`, `font-weight: 600`, `padding: 8px 18px`, `font-size: 15px`. Disabled tlačítko zabal do `Tooltip` s `blocker` a nastav `pointer-events: none` jako u `button.run.no-workflow`.
- Start: `POST /backlog/task-advice` s `{task_id?, draft}` **bez** harness/model, pak polling `GET /backlog/task-advice/{id}` po 800 ms. Převezmi z `TaskAdvice.vue` generation/abort/hashchange ochrany (`stop()`, `scopeChanged`, `onBeforeUnmount`).
- Hotovo: emit `result` (formulář návrh rovnou aplikuje). Pod tlačítkem (nebo jako poznámka ve formuláři, viz C) se ukáže krátký blok `data-test="improve-note"`: `reason`, kdo návrh dělal (`advisor.harness · model · thinking`) a cena (`cost_usd`/tokeny, stejný text jako dnes `task-advice-cost`). Blok jde zavřít (×).
- Chyba: `role="alert"` s textem (`data-test="improve-error"`).
- Když se během běhu změní `draft` (watch na `JSON.stringify([taskId, draft])`), job se zahodí (`stop()`) a ukáže se „Zadání se změnilo. Spusť vylepšení znovu.“ Formulář ale během běhu inputy zamyká (viz C), takže by to nastat nemělo.
- `autostart`: v `onMounted`, pokud `autostart && !disabled && !blocker`, zavolej `start()` jednou.
- `TaskProposal` typ přesuň do `ImproveButton.vue` (export z `<script lang="ts">` bloku jako dnes v TaskAdvice) nebo do `@/lib/backlog.ts`. Doplň do Job typu `advisor?: {harness?: string; model?: string; thinking?: string} | null`.
- `TaskAdvice.vue` a `TaskAdvice.test.ts` smaž. Testy přepiš do `ImproveButton.test.ts`: start bez harness/model v POST body, spinner a busy, apply výsledku (emit), chyba, autostart, změna draftu během běhu, cena a advisor v poznámce. Vzor mockování API vezmi z `TaskAdvice.test.ts`.

### C. Formulář `TaskForm.vue` (add i edit)

Rozložení shora:
1. Hlavička: vlevo `h2` („Nový task“ / „Upravit T…“), vpravo `ImproveButton` (flex `justify-content: space-between`). Tím je „Vylepšit agentem“ vpravo nahoře i ve formuláři.
2. Add mode: Step (SelectMenu) a Kód (volitelné) v jednom řádku (grid 2 sloupce).
3. Titulek.
4. Zadání: textarea `data-test="body"`, `rows="14"`, přes celou šířku. Formulář `max-width` zvětši na ~900px.
5. Workflow (SelectMenu) a pod ním `WorkflowAdvice` beze změny chování (umí navrhnout i **nové** workflow, a to `ImproveButton` neumí, proto zůstává; e2e `test_workflow_advice_browser.py` ho používá přes `[data-test="workflow-advice"] button`).
6. `<details data-test="advanced">` „Další nastavení“, sbalené. Otevři ho, když má task v editaci jiný než výchozí stav (status ≠ todo, vlastní auto-merge, vlastní writes, vazby, vlastní parametry) nebo když návrh agenta něco z toho změnil. Obsahuje:
   - Status (jen edit, s dosavadní poznámkou pro done),
   - Auto-merge (jen edit),
   - Writes + checkbox „dědit writes“,
   - Závisí na / Související (řádek se 2 sloupci),
   - parametry (harness, model, thinking, source, target, test_timeout, auto_continue, auto_merge v add mode). Dnešní vnořené `<details data-test="task-parameters">` zruš a pole dej přímo do „Další nastavení“ pod nadpis `h4` „Parametry (prázdné = zděděno)“. Element s `data-test="task-parameters"` ponech jako obalový `div`, ať selektory testů fungují. Pozor: dnešní seznam `parameterFields` nemá `thinking`, i když ho backend (`TaskParameters`) přijímá. Přidej `thinking` jako SelectMenu s volbami `Zděděno` + úrovně z backendu (`harness/override.py` `THINKING_LEVELS`; ověř, jestli je frontend už někde má, např. `lib/machineHarnesses` nebo roster UI, a použij je). Popisek vezmi ze `SETTING_LABELS` nebo ho doplň.
7. Akce: Uložit (primary) a Zrušit, IssueList.

Chování vylepšení:
- `ImproveButton` dostane `:draft="parameterDraft"`, `:task-id="task?.id"`, `:disabled="busy || adviceBusy"`, `:blocker="adviceBlocker"`, `:autostart="autoImprove"`. Nový prop formuláře `autoImprove?: boolean`.
- `@result="applyParameters"`: zachovej dnešní `applyParameters` (zapíše titulek, zadání, writes, vazby, workflow, parametry, auto-merge) a navíc otevři „Další nastavení“, pokud návrh změnil něco, co je v něm.
- Dokud běží vylepšení (`parameterBusy`), obal pole do `<fieldset :disabled="parameterBusy">` (bez rámečku, `border:0; padding:0; margin:0; min-width:0`), aby uživatel nepsal do formuláře, který návrh za chvíli přepíše. Uložit je zakázané už dnes přes `canSubmit`.
- Dnešní `<p data-test="advice-blocker">` zruš, důvod je v tooltipu tlačítka.
- Logika `editInput`/`addInput`/`attachAdvice` se nemění.

### D. Detail `TaskDetail.vue` (readonly)

Hlavička:
- Řádek 1: `id`, titulek, StateChip. Vpravo (`head-buttons`, `margin-left:auto`) v tomto pořadí: Spustit (modré, beze změny), Upravit (`data-test="edit"`), Zrušit (červený text, jen `queueable`) a jako poslední, nejvíc vpravo, **velké zelené „Vylepšit agentem“** (`data-test="improve"`). V detailu je to jen tlačítko (ne `ImproveButton`): `editing = true; autoImprove = true`. Disabled při `busy || adviceBlocked`, tooltip „Task už nejde měnit.“ podle stavu (stejné stavy jako `adviceBlocked`). Styl zelené varianty sdílej: buď třída v `style.css` (globální `.btn-improve`), nebo stejný scoped CSS. Preferuj globální třídu v `aifactory/web/src/style.css`, kterou použijí obě komponenty.
- `TaskForm` v detailu dostane `:auto-improve="autoImprove"`. `autoImprove` se resetuje na `false` po zavření formuláře (cancel / uložení / změna tasku ve watch na `detail`), aby další ruční „Upravit“ nespustilo agenta.
- Když je formulář otevřený, tlačítko „Vylepšit agentem“ v hlavičce detailu skryj (`v-if="!editing"`), ať nejsou na stránce dvě. Formulář má svoje.

Odebrat z detailu (dělá to formulář):
- V kartě Spuštění: SelectMenu `workflow-select`, tlačítko `assign` a „Upravit a navrhnout workflow“. Workflow zůstane jen jako text (`dd[data-test="workflow"]`, e2e ho čte). Smaž `workflowChoice`, `workflowOptions`, `assign()`, emit `assign-workflow` a nepoužité importy (`SelectMenu`, `SelectOption`, `Wand2` jen pokud nebude použit u nového tlačítka; bude).
- Ve Vazbách: inputy a tlačítka „Přidat“ (`link-input`, `link-add`, `related-input`, `related-add`) a stav `dependsInput`, `relatedInput`, `addLink`, `linkPlaceholder`. **Odebírací křížky (`unlink-*`, `unrelate-*`) ponech.** Jsou to rychlé jednokliknutí a stačí jim emit `link` s `remove: true`. Emit `link` tak zůstává.
- Kartu „Spuštění“ přejmenuj na „Nastavení“ a nech v ní: Workflow (text + „(zděděno)“), Auto-merge, Writes, Auto continue (toggle zůstává, je to fronta, ne editace souboru).
- Cestu k souboru (`.path`) nech, je drobná a faint.

`BacklogView.vue`: odeber handler `@assign-workflow` a jeho funkci, pokud ji už nic nepoužívá (grep `assign-workflow`, `assignWorkflow`, `busyAction === 'assign'`). Pokud ji používá jen TaskDetail, smaž ji i s testy, které ji testují. `onLink` zůstává (remove).

### E. Testy frontendu

- `TaskDetail.test.ts`: odstraň testy přiřazení workflow a přidávání vazeb. Přidej testy:
  - tlačítko `improve` je vidět v readonly režimu; klik otevře `TaskForm` a ten dostane `autoImprove === true` (ověř prop přes `findComponent(TaskForm).props('autoImprove')`),
  - `improve` je disabled pro stavy done/cancelled/running/in review,
  - po kliknutí na „Upravit“ má `autoImprove` hodnotu false,
  - vazby se dál dají odebrat křížkem (emit `link` s remove).
- `TaskForm.test.ts`: uprav selektory (`task-parameters`, `advice-blocker`, `task-advice-*`) na nové rozložení. Přidej testy: výsledek `ImproveButton` aplikuje titulek a zadání a otevře „Další nastavení“, když změní writes nebo vazby; pole jsou během běhu disabled (fieldset); `autoImprove` se předá do `ImproveButton` jako `autostart`; parametr `thinking` se pošle v `parameters`.
- `BacklogView.test.ts` a `backlogFixtures.ts`: uprav, co se týká odebraných selektorů a eventů.
- Pomocí grepu najdi všechny `data-test` hodnoty, které odebíráš (`workflow-select`, `assign`, `link-input`, `link-add`, `related-input`, `related-add`, `task-advice`, `task-advice-start`, `task-advice-apply`, `task-advice-result`, `task-advice-cost`, `advice-harness`, `advice-model`, `advice-no-agents`, `advice-blocker`) v `aifactory/web/src` i v `aifactory/tests` (e2e i python), a uprav je.

### F. Build a dokumentace

- `just web-build` (vygeneruje commitovaný `aifactory/src/aifactory/web/static`). Výstup patří do změny.
- Dokumentace tasku: `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T21-redesign-stranky-task.md` (česky). Popiš nové rozložení detailu a formuláře, tlačítko „Vylepšit agentem“, odkud se berou agent, model a thinking, a co z detailu zmizelo a kde se to teď dělá.
- Když README v `aifactory/` popisuje výběr harness/modelu u návrhu parametrů tasku, aktualizuj ho (`grep -rn "Navrhnout parametry\|návrh parametrů" aifactory/README* aifactory/docs 2>/dev/null`). `docs/decisions.md` v kořeni repa není v povolených cestách, neměň ho.

## Ověření

Spouštěj z kořene worktree:
- `just lint`, `just typecheck`
- `just pytest tests/web/test_web_task_advice.py tests/web/test_web_workflow_advice.py tests/web/test_web_backlog.py`
- `just web-test` (vue-tsc + vitest)
- `just web-build`
- `just pytest tests/e2e/test_workflow_advice_browser.py -n0` a `just pytest tests/e2e/test_f3_browser.py -n0` (používají `edit`, `save`, `title`, `textarea[data-test="body"]`, `workflow-advice`, `dd[data-test="workflow"]`, které musí zůstat).

Ruční kontrola (volitelná, `just dash`): detail tasku má vpravo nahoře zelené tlačítko s hůlkou. Klik otevře formulář a hned spustí návrh (spinner), formulář je zamčený a po dokončení jsou pole vyplněná a pod tlačítkem je důvod, agent a cena.

## Rizika a poznámky

- `ctx["effective"]` zahrnuje i parametry draftu. Když uživatel ve formuláři vybere jiný harness/model/thinking, vylepšení použije je. To je záměr: stejné nastavení, se kterým by task běžel.
- `fingerprint(ctx)` obsahuje `advisor`, deduplikace jobů tedy funguje dál.
- Neměň `.factory/` (protected), soubory engine ani nic mimo povolené cesty.
