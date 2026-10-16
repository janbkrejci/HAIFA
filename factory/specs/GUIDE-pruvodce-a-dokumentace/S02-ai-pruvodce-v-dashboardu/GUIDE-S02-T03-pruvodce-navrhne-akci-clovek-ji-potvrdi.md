# Spec: Průvodce navrhne akci, člověk ji potvrdí

## Cíl

Průvodce (GUIDE-S02-T01, panel GUIDE-S02-T02) dál nic nezapisuje, ale místo vysvětlování
umí změnu navrhnout. Provede ji až člověk v panelu, stejnou cestou jako ruční akci.

## Návrh

- Agent `guide` vloží do odpovědi blok ```` ```haifa-action ```` s jedním JSON objektem
  (nejvýš 5 na odpověď). Druhy a pole (`repo` = id registrovaného repa je povinné všude,
  `reason` volitelné):
  - `create_task`: `step`, `title`, volitelně `body`, `writes`, `workflow`, `depends_on`,
  - `edit_task`: `task` a aspoň jedno z `title`, `body`, `writes`, `workflow`,
  - `run_task`: `task`, `note?`; `retry_run`: `run`, `note?`,
  - `approve_pr`: `task`; `cancel_task`: `task`.
- `web/assistant.py` (`parse_actions`) bloky z textu odpovědi odstraní, platné uloží do
  zprávy jako `actions` (`id`, pole, `status: proposed`). Neplatný blok (neznámý druh,
  neregistrované repo, chybějící nebo cizí pole, špatný JSON) nahradí citace
  „Návrh akce nejde nabídnout: …“. Návrh se parsuje z už redigovaného textu.
- Backend návrh nikdy neprovede. `ActionCard.vue` v panelu ukáže nadpis, důvod, náhled
  (pole po poli; u `edit_task` a `cancel_task` s aktuální hodnotou tasku z
  `GET /api/repos/{repo}/backlog/tasks/{task}`) a tlačítka **Provést** a **Zahodit**.
- **Provést** zavolá stávající zápisové API repa (`actionRequest` v `lib/assistant.ts`):
  `POST …/backlog/tasks`, `…/backlog/tasks/{task}/edit` (u `cancel_task`
  `{status: cancelled}`), `…/backlog/tasks/{task}/run`, `…/runs/{run}/retry`,
  `…/review/{task}/approve`. Platí tedy `WriteGuardMiddleware`, `StaleCodeMiddleware`
  a validace endpointu jako u ruční akce.
- Výsledek (nebo zahození) panel zapíše
  `POST /api/assistant/threads/{id}/actions/{action_id}` s `{status: done|failed|dismissed,
  message?}`. Endpoint jen zaznamená: nastaví stav návrhu a `outcome`, přidá do vlákna zprávu
  `role: action`. Rozhodnutý návrh vrací 409 `action_decided`, neznámý 404 `unknown_action`.
- Výsledky od poslední zprávy uživatele jdou agentovi s další zprávou v sekci
  „Outcome of your proposed actions“.

## Testy

- `tests/web/test_web_assistant.py`: návrhy bez potvrzení nic nezapíšou (soubor tasku,
  `git status`, HEAD), záznam výsledku nezapisuje do repa, opakovaný záznam 409, výsledek
  v promptu další zprávy právě jednou, validace polí.
- Vitest: `lib/assistant.test.ts` (mapování na API, náhled, text výsledku),
  `AssistantPanel.test.ts` (karta, Provést volá API až po kliknutí, Zahodit nic nezapíše).
- Browser: `tests/e2e/test_assistant_browser.py::test_assistant_proposed_action_browser`.
