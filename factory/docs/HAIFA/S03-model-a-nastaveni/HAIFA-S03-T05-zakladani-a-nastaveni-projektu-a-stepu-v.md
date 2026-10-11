# HAIFA-S03-T05: Zakládání a nastavení projektu a stepu v dashboardu

## Co se změnilo

- **Panel Nastavení na stránce grafu** (`#/backlog/graph/<id>`). Upravuje název a klíče `workflow`, `writes`, `test`, `source`, `target`, `specs_dir`, `docs_dir` a `auto_continue`. U každého klíče je platná hodnota s původem: vlastní, zděděná z úrovně (`Projekt M01`), z `.factory/config.yaml (test_command)`, výchozí nebo nenastaveno. Zaškrtnutí Zdědit pošle klíč v `clear` a vlastní hodnotu smaže. Odškrtnutí předvyplní zděděnou hodnotu. `writes` a `test` mají jednu položku na řádek a jeden příkaz `test` se uloží jako řetězec. Uložit posílá jen změněné klíče.
- Panel upozorní, že se změna zapíše do pracovního stromu a běhy ji použijí až po commitu backlogu do base. Popis z `index.md` je pod panelem jako `MarkdownView` (Náhled a Zdroj), jen ke čtení.
- **Nový projekt** na Backlogu a **Nový step** na grafu projektu otevřou formulář s kódem, názvem a popisem (`#/backlog/new-container[/<rodič>]`). Po založení se otevře graf nového projektu nebo stepu. Akce Nový step chybí u úrovně, která obsahuje jen tasky. Chyba validace (`duplicate_id`, `id_prefix`, `invalid_id`) se ukáže u formuláře a nic se nezapíše.
- Volání: `GET /api/backlog/containers/{id}`, `POST /api/backlog/containers` a `POST /api/backlog/containers/{id}/edit` (HAIFA-S03-T04).

## Kde to je

| Soubor | Změna |
|---|---|
| `aifactory/web/src/components/backlog/ContainerSettings.vue` | panel Nastavení |
| `aifactory/web/src/components/backlog/ContainerForm.vue` | formulář nového projektu nebo stepu |
| `aifactory/web/src/lib/backlog.ts` | typy, `fetchContainer`, `addContainer`, `editContainer`, `settingText`, `originText`, `childLevel` |
| `aifactory/web/src/lib/router.ts` | `NEW_CONTAINER`, `newContainerHref` |
| `aifactory/web/src/views/BacklogView.vue` | načtení detailu ke grafu, akce a formulář |
| `aifactory/src/aifactory/web/static/` | nový build |

## Testy

- `ContainerSettings.test.ts`, `ContainerForm.test.ts`, nové případy v `BacklogView.test.ts` a `router.test.ts`.
- `aifactory/tests/e2e/test_f3_browser.py::test_project_and_step_from_dashboard`: odmítnutý duplicitní kód, založení projektu M02 a stepu M02-S01, nastavení workflow stepu, task M02-S01-T01. Nic se necommituje a model se nevolá.
