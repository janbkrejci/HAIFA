# HAIFA-S11-T06: Převzetí legacy voleb a kompatibilita sdíleného backlogu

CLI `factory config local legacy --repo PATH --json` a API `GET /settings/local/legacy`
ukazují effective hodnoty a jejich původ pro projekt, step a task. Harness binding počítá
historické pravidlo odstranění modelu při změně harnessu. Náhled nevytváří lokální záznam,
neimportuje ani nesynchronizuje databázový mirror backlogu.

`factory config local import --repo PATH --json` a `POST /settings/local/legacy` přijímají
explicitní rozhodnutí (`choices`) a volitelné `overwrite`. Shodné hodnoty se mohou převzít
přímo; jakýkoliv rozpor požaduje konkrétní volbu pro celé repo. Existující místní záznam
zůstává beze změny bez výslovného přepsání. Zápis probíhá pod stejným zámkem a přes stejné
atomické nahrazení jako ostatní místní volby, pouze do HAIFA_HOME. Opakování nemění soubor.
Model/thinking se zobrazují, ale lokální harness používá místní preset/roster.

Přehled nabízí náhled, výběr při rozporech a výslovné přepsání místních voleb. Staré CLI
zápisy `backlog auto-continue`, `backlog auto-merge` a `task edit --auto-merge` odmítá
`deprecated_option` s konkrétní alternativou `config local set`. Čtení metadat zůstává.
Návrhy parametrů tasku vracejí jen test_timeout, aby aplikace návrhu nesmazala staré
provozní hodnoty. Demo a běžné nové tasky provozní klíče nepotřebují.

Audit čtení: `run/scope` čte z effective pouze writes, `run/heal` auto_heal a
`run/quota_chain` samostatná quota pole; nejsou náhradou místní politiky auto merge či
continue. `backlog/render`, `web/backlog` a nový náhled čtou legacy metadata. Wrapper
`run/task.task_harness_values` je kompatibilní čtečka; Guide ověří kontext pomocí
`harness_values`, ale runtime volí přes místní context_binding. Pomocní agenti i běhy
používají místní nastavení; tento task nepřidává runtime fallback do frontmatterů.

Zmrazený reader v `tests/legacy_backlog` pochází z pre-S11 commitu 9c10094. Kompatibilitní
test přes něj načte zachovaný backlog po editaci, add, follow-up a označení hotovo
(textová operace sdílená approve/sync). Matice pokrývá chybějící záznam, on/off, import,
dva HAIFA_HOME, novou instanci služby, nový backlog bez klíčů i skutečný git pull změny
legacy voleb. Selhání atomického zápisu nezmění předchozí záznam. Testy jsou bez modelů
nebo živých služeb.

Uživatelská příručka, CLI help, zdroj generovaného factory skillu a docs/decisions.md
popisují vypnuté výchozí hodnoty, explicitní převzetí a běžný restart již spuštěného
dashboardu. Neupgradovaný počítač používá frontmattery, upgradovaný místní volby.
Přechod nevyžaduje commit ani bariéru minimální verze a neodstraňuje sdílená legacy pole.

## Ověřování ve workflow

Diagnosticky prošel jediný test
`just pytest tests/backlog/test_legacy_transition.py::test_cli_preview_and_explicit_import -n0`
(1 passed). Verifikaci ostatních změn provádí samostatný testovací krok:

- `just lint`, `just typecheck`.
- `just pytest tests/backlog/test_legacy_transition.py tests/backlog/test_backlog_auto_continue.py tests/backlog/test_backlog_auto_merge.py tests/test_skill.py tests/web/test_web_settings.py tests/web/test_web_task_advice.py tests/demo/test_demo_try.py`.
- `just web-test`, `just web-build` (včetně aktualizace distribuovaných statických assetů).
- `just pytest tests/e2e/test_overview_loading_browser.py -n0`.
- Vybrané existující integrace T02–T05:
  `just pytest tests/run/test_live_auto_continue.py::test_off_during_accepted_run_finishes_it_without_next_task tests/run/test_live_auto_continue.py::test_cli_auto_cannot_enable_local_off tests/run/test_auto_merge.py::test_local_switch_overrides_task_auto_merge tests/run/test_task_run.py::test_project_and_task_model_choices_are_legacy_metadata`.

Výběr zahrnuje všechny editované testovací soubory. Frontend testy zahrnují jednotkové
regrese LocalRepoControls; browser scénář ověřuje, že před explicitní volbou při rozporu
neodejde import a po převzetí zůstává zvolená automatizace vypnutá. Přímí volající byli
vyhledáni v celém aifactory/tests; ostatní používají nezměněný výchozí režim loaderu nebo
pouze metadata. Celá sada se v tomto tasku nespouští.

## Oprava po prvním ověřování

Logy běhu 04 odhalily tři nesrovnané importy, chybějící typy browser fixture,
překročení limitu délky příručky a nativní select/tooltip v novém náhledu.
Importy jsou seřazené podle Ruff, browser fixture má explicitní typy JSON payloadů.
Příručka má 4096 slov při zachování limitu 4100 a popisu ručního převzetí i restartu.
Náhled používá sdílený SelectMenu a Tooltip; testy ovládají jejich dropdown místo
nativního selectu a ověřují původ hodnot i explicitní volbu dědění harnessu.
Opětovné kontroly a regeneraci distribuovaného frontendu provede testovací krok.
