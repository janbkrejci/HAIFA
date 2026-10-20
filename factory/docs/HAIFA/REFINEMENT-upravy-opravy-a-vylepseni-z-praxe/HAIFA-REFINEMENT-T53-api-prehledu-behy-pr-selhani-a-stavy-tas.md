# Přehled repozitáře po projektech

`GET /api/overview` vrací u repozitáře také `projects`: seznam objektů
`{id, title, tasks}` v pořadí projektů načteného backlogu. Projektové `tasks`
obsahuje všechny stavy kanbanu včetně nul. Stav každého tasku se vyhodnotí jednou
a započítá současně do součtu repozitáře i jeho projektu.

Položky `running`, `review`, `automerge`, `failed`, `merged_outside` a
`auto_actions` obsahují `project`, tedy id nejvyššího předka tasku. Pokud task
v backlogu chybí nebo má backlog méně než tři úrovně, hodnota je `null`.
Bez projektové úrovně či čitelného backlogu je `projects` prázdný seznam.
Stejně se chovají zástupné odpovědi `missing`, `not_git`, `timeout` a `error`.

Součty `tasks` repozitáře a `totals` zůstávají zachovány. Přehled používá již
načtený backlog a trace; nepřidává zápisy ani volání gitu nebo providera.
Frontend není součástí této změny.

Pokrytí v `tests/web/test_web_overview.py` ověřuje rozdělení běhů, PR a selhání
mezi dva projekty, projektové součty a jediný výpočet stavu každého tasku,
backlog bez projektů, neznámé tasky, přiřazení automatických akcí a zástupné odpovědi.
