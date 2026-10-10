# Názvy úrovní a tooltipy s názvy kódů v dashboardu

**Task:** HAIFA-S01-T06

## Co se změnilo
- Úrovně backlogu se v dashboardu jmenují česky podle `levels`: Projekt, Modul, Step, Task; jiné jméno úrovně zůstává, jak je v konfiguraci. Platí pro strom, hlavičku grafu, legendu grafu (`mimo projekt/step`), formulář tasku, placeholdery a hlášky. Sloupec projektu na obrazovce Review se jmenuje podle první úrovně.
- Každý kód projektu, stepu nebo tasku má po najetí myší tooltip `Úroveň: název` (např. `Task: Názvy úrovní…`). Tooltip Blokováno uvádí u kódů názvy (`M01-S01-T02 (Loader) – task není hotový`), uzel grafu má tooltip s úrovní.
- Filtr tasku na obrazovce Běhy ukazuje `kód: název`.
- Názvy se obnovují živě: po změně souboru v backlogu (live událost `files`) dashboard znovu načte `GET /api/backlog/names`, takže přejmenování se projeví bez obnovení stránky.

## API
- Nový `GET /api/backlog/names`: `{levels: [...], names: {"<id>": {"title": "...", "level": "project"}}}`.
- `GET /api/backlog`: u stepů klíč `project` (dříve `module`).
- `GET /api/review`, `GET /api/review/{task_id}`: klíč `project_id` (dříve `module_id`) a `levels`.

## Jak ověřit
`just dash`, najeď myší na kód v backlogu, Review nebo Bězích; přejmenuj task (Upravit → Titulek) a tooltip jeho kódu se změní bez obnovení stránky.
