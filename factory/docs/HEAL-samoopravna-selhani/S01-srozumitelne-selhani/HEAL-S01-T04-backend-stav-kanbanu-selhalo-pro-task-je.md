# HEAL-S01-T04: Stav kanbanu „Selhalo“ (backend)

## Co se změnilo

`GET /api/backlog` má nový stav `failed` (ve `states` hned za `blocked`). Task má
`board_state: "failed"`, když jeho nejnovější běh skončil jako `failed` nebo `aborted`
a druh selhání není `blocked`. Dřív se takový task vrátil do Připraveno.

Přednost mají `cancelled`, chyba dokončení, `done`, `running`, sloučené PR a otevřené PR.
Nový běžící nebo úspěšný běh task ze stavu `failed` vrátí. Běh druhu `blocked` (čeká na
jiné tasky) není selhání, task zůstane ve stavu podle závislostí.

Pravidlo je jedno pro kanban i seznam `failed` na Přehledu (`run_failed` v
`aifactory/web/backlog.py`). Počty `state_counts` a počty tasků na Přehledu `failed`
počítají, filtr `?status=failed` ho vybere.

Výběr dalšího tasku pro auto-continue se nemění. Frontend stav zobrazí v HEAL-S01-T05.
