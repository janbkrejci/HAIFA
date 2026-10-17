# INTENT-S02-T03: Detail hotového tasku: Otevřít navazující task

Hotový task se znovu nespouští ani neupravuje. Jeho detail proto nemá tlačítka **Spustit**, **Upravit** ani **Vylepšit agentem**, má místo nich **Otevřít navazující task**.

## Tok

1. **Otevřít navazující task** otevře v detailu dialog: textové pole „Co změnit, předělat nebo dodělat“ (povinné), volitelný titulek (bez něj platí „Navazuje na <ID>: <titulek původního>“) a volba **Spustit hned**, výchozí zapnutá.
2. Potvrzení zavolá `POST /api/backlog/tasks/{id}/follow-up` `{body, title?, run}` (INTENT-S02-T01). Backlog se commitne do base při každém potvrzení. S **Spustit hned** ho commitne server a spustí běh nového tasku. Bez této volby ho commitne dialog (`POST /api/backlog/commit`, jako `factory backlog commit`). Když commit selže, task zůstane zapsaný v pracovním stromu. Dialog pak ukáže chybu a místo nového založení nabídne otevření tasku.
3. Dashboard pak otevře detail nového tasku. Chyba API se ukáže v dialogu.

## Vazby v detailu

- Navazující task ukazuje pod cestou odkaz „Navazuje na <ID>“ s titulkem původního tasku (`follows` z detailu tasku).
- Původní task má v kartě Vazby skupinu „Navazují na něj“ se seznamem tasků, které na něj navazují, a jejich stavem (`followed_by`).

## Testy

- `aifactory/web/src/components/backlog/FollowUpDialog.test.ts`: vitest dialogu (commit bez běhu, selhaný commit).
- `aifactory/web/src/components/backlog/TaskDetail.test.ts`: tlačítka hotového tasku, založení z dialogu, odkazy `follows` a `followed_by`.
- `aifactory/tests/e2e/test_follow_up_browser.py`: celý tok v prohlížeči s fake harnessem (založení, commit, běh, odkazy v obou směrech).
