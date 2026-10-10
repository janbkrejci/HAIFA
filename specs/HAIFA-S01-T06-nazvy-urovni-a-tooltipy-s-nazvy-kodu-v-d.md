# HAIFA-S01-T06: Názvy úrovní a tooltipy s názvy kódů v dashboardu

## Cíl
Dashboard pojmenuje úrovně backlogu česky podle `levels` (project → Projekt, module → Modul,
step → Step, task → Task, jiné jméno beze změny) a každý kód projektu, stepu nebo tasku
má tooltip s názvem a úrovní (rozhodnutí *Úrovně backlogu* v `docs/decisions.md`).

## API
- `GET /api/backlog/names` → `{levels, names: {id: {title, level}}}` pro každý kontejner s id a každý task (backlog checkoutu, bez commitu).
- `GET /api/backlog`: step má `project` místo `module`.
- `GET /api/review` a `GET /api/review/{task_id}`: `project_id` místo `module_id`, nově `levels`.
- API běhů (`phases`, `phase_id`) beze změny.

## Frontend
- `lib/backlog.ts`: `levelLabel`, `levelNoun`, `levelsText`, `codeTooltip`, `codeWithTitle`, `namesFromBacklog`, `fetchNames`; tooltip Blokováno doplní názvy a úroveň.
- `lib/names.ts`: sdílená mapa názvů a `levels`; App.vue ji načte a obnoví při živé změně backlogu (`files`) a při `resync`; Backlog ji doplní z načteného stromu.
- `components/ui/CodeTip.vue`: kód s tooltipem `Úroveň: název`.
- Tooltip mají: strom, kanban, hlavička grafu a uzly grafu, detail tasku (hlavička, vazby, PR), nesplněné závislosti v dialogu spuštění, Review (seznam, detail, sloupec projektu), Běhy (seznam, náklady, hlavička běhu). Filtr tasku v Bězích ukazuje `kód: název`.
- Popisky, placeholdery a hlášky podle úrovní (formulář tasku, legenda grafu, sloupec Review).

## Testy
pytest `tests/web/test_web_backlog.py`, `tests/web/test_web_review.py`; vitest `lib/levels.test.ts`, `lib/names.test.ts`, `components/ui/CodeTip.test.ts`, `lib/blockedTooltip.test.ts`, `App.test.ts` a upravené testy komponent.
