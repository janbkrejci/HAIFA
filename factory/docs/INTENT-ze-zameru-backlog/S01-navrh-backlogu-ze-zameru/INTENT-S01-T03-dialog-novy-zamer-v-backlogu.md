# INTENT-S01-T03: Dialog Nový záměr v Backlogu

Backlog má tlačítko **Nový záměr** (`#/r/<repo>/backlog/intent[/<projekt nebo step>]`). Z grafu projektu nebo stepu dialog předvybere jeho kontejner.

## Tok

1. Člověk napíše záměr a vybere, kam návrh patří: projekt (agent navrhne nový step s tasky) nebo existující step (nové tasky). **Navrhnout** spustí agenta `proposer` stejně jako `factory backlog propose`: read-only v izolovaném klonu base commitu, s validací a jednou opravou.
2. Během návrhu dialog ukazuje průběh aktuálního kola: start agenta, jeho nástroje, vrácení návrhu ke kontrole, čekání na providera. Čte je z `events.jsonl` běhu v `.factory/data/backlog-propose/<job>/`.
3. Výsledek je strom: step (nový nebo existující) a jeho nové tasky. Každý task jde rozbalit (zadání, workflow, writes, závislosti, nálezy kontroly kvality), upravit (titulek a zadání) nebo odebrat (a vrátit). Závislosti na odebraném tasku návrhu se při použití vypustí.
4. **Upřesni** pošle připomínku a návrh tak, jak ho člověk upravil, do stejné session agenta (stejné `job_id`, stejný klon, pokračovací prompt `## Continuation`). Agent vrátí celý upravený návrh, ten projde stejnou validací. Když upřesnění selže, zůstane předchozí návrh.
5. **Použít** zapíše návrh (validace jako `propose --apply`) a commitne backlog jako tlačítko commitu backlogu (`factory backlog commit`). Když commit selže (např. hlavní checkout není na base), soubory zůstanou zapsané a dialog to oznámí. Pak dashboard ukáže graf stepu.

## API

- `POST /api/backlog/intent` `{intent, project | step}` → job (202).
- `GET /api/backlog/intent/{id}` → `{state, round, proposal, progress, error, issues, notes, applied}`; `state` je `queued | running | ready | failed | applying | applied`.
- `POST /api/backlog/intent/{id}/refine` `{note, tasks?}` → job (202).
- `POST /api/backlog/intent/{id}/apply` `{tasks?}` → zapsaný návrh s `commit` a `warnings`.
- `POST /api/backlog/intent/{id}/discard` → zavře návrh a smaže klon.

`tasks` je seznam ponechaných tasků `{code, title, body}` v jejich pořadí. Návrh bez aktivity zanikne po hodině; současně běží nejvýš dva návrhy.

## Testy

- `aifactory/tests/web/test_web_intent.py`: API s fake harnessem (návrh, upřesnění ve stejné session, úpravy, použití s commitem, chyby, zavření).
- `aifactory/web/src/components/backlog/IntentDialog.test.ts` a `BacklogView.test.ts`: vitest dialogu.
- `aifactory/tests/e2e/test_intent_browser.py`: celý tok v prohlížeči s fake harnessem.
