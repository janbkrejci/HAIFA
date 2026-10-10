# `factory onboard`: jednorázový onboarding `.factory/` z doby před knihovnou

Task `HAIFA-S06-T03` · spec `specs/HAIFA-S06-T03-jednorazovy-onboarding-factory-onboard-a.md`

## Co se změnilo

Přibyl příkaz `factory onboard`. Repo ve stavu `pre_library` (má `.factory/`, ale nemá manifest) jednou vytěží do knihovny a do commitnuté `.factory/` s `.factory/manifest.yaml` a blokem `onboarding` (rozhodnutí 8). Převod sssf (O4) sem zatím nepatří. Takové repo dostane blokátor `sssf_not_supported`, ale extraktor vrací strukturu `Extraction`, kterou O4 naplní.

```
factory onboard [--repo PATH] [--dry-run | --commit [--pr] [--expect DIGEST] [-m TEXT]]
                [--keep-local TYP/JMÉNO]… [--name TYP/JMÉNO=NOVÉ]… [--json]
```

- Bez `--commit` příkaz vrátí jen plán. Pracovní strom zůstane beze změny, posunou se nanejvýš remote-tracking refy po fetch.
- Kontrola remote je jediný síťový krok: `git fetch <remote> <base>` a `git ls-remote --heads <remote> factory-config/onboarding`. Když je manifest už v remote base, plán vrátí `onboarded_in_remote` (oprava: `factory config pull`, pak `factory adopt`). Existující větev (remote i lokální) dá `onboarding_pending`. Selhání fetch nebo ls-remote dá `remote_unchecked`. Repo bez remote dostane varování `no_remote` a commit zůstane jen lokální.
- Každý agent z rosteru a každé workflow z `.factory/workflows/` se zahashuje a dostane kód zprávy:
  - `linked`: knihovna obsah má, buď jako verzi v historii položky stejného jména, nebo jako hlavu jiné položky.
  - `converted`: vznikne nová položka. Dostane jméno slotu, když je volné, jinak `<slot>-<slug kořenové složky repa>` (D30), nebo jméno z `--name`.
  - `carried_over`: platí s `--keep-local`. Slot se napojí na položku stejného jména a rozdíl zůstane v repu.
  - `manual`: nejde o platnou položku, slot zůstane lokální.
  - `left_in_place`: ostatní soubory (`config.yaml`, `agents.yaml`, `adws/` …).
  - `changed_meaning` a `not_converted` jsou rezervované pro O4.
  - Workflow, která backlog v base jmenuje a v repu chybí, se přidají z knihovny.
- Existující soubory `.factory/` zůstanou bajtově stejné. Plán smí jen přidávat soubory pod `.factory/` a připojovat řádky na konec `.gitignore`. Hlídá to `_check_invariant`, který při porušení vyhodí `RuntimeError`.
- Plán validuje konfiguraci a preflight workflow (`install_commit._validate`). Při potížích vrátí `invalid_plan` a seznam `issues`. Digest kombinuje digest části repa a digest plánu knihovny (`onboard_digest`). Manifest se do digestu počítá bez časových polí (`_stable`).
- `--commit`: plán se přepočítá a při neshodě s `--expect` skončí chybou `plan_changed`. Pak dostane commit a push knihovna (`import_items`, `expect_head`). Když ji remote odmítne, skončí to dřív, než se na repo sáhne. Repo se commitne bez checkoutu přímo do base (`publish_direct`), nebo s `--pr` na pevnou větev `factory-config/onboarding` s PR (`publish_pr`). Když repo selže až po pushi knihovny, chyba nese `data.library_commit` a `fix: factory onboard --dry-run`. Opakovaný běh pak nové položky `linked` napojí.
- Zpráva po kódech je v `--json` (`data.report`), v těle commitu i v popisu PR (`report_text`).

Blokátory: `already_onboarded`, `not_installed`, `config_not_committed`, `sssf_not_supported`, `source_not_committed`, `library_missing`, `library_dirty`, `library_behind`, `library_diverged`, `onboarded_in_remote`, `onboarding_pending`, `remote_unchecked` a blokátory M7 (`base_behind`, `base_diverged`, `not_on_base`, `run_in_progress`, `dirty_paths`, `invalid_plan`). `--name` a `--keep-local` mohou skončit chybou `name_taken` nebo `unknown_item`.

## Kde to je

- `aifactory/src/aifactory/onboard/extract.py` (nový): `extract_pre_library`, `Extraction`, `ReportRow`, `REPORT_CODES`, pojmenování nových položek (`slug`, `_new_name`) a workflow z backlogu (`_backlog_workflows`).
- `aifactory/src/aifactory/onboard/onboard.py` (nový): `plan_onboard` (stavové blokátory, kontrola knihovny a remote, manifest, `.gitignore`, validace, digest), `run_onboard` (nejdřív knihovna, pak repo), `ONBOARDING_BRANCH`, `OnboardPlan` a `OnboardResult`.
- `aifactory/src/aifactory/onboard/__init__.py`: exporty nových symbolů.
- `aifactory/src/aifactory/providers/git.py`: `remote_branch_exists` přes `git ls-remote --heads`. Při nedostupném remote vrací `None`.
- `aifactory/src/aifactory/providers/publish.py`: porovnání s remote base je vyčleněné do `compare_remote` (bez fetch). `publish_pr` přijímá pevnou větev přes `branch=`, a když už lokálně existuje, skončí chybou `commit_failed`.
- `aifactory/src/aifactory/cli.py`: podpříkaz `onboard` (argumenty, kontrola konfliktů voleb, textový i JSON výstup).
- `aifactory/src/aifactory/skill/codes.py` a `skill/skill.md`: nové chybové kódy, skupiny `onboard_report` a varování `onboard` (`no_remote`, `remote_note`, `gitignore_dirty`, `harness_missing`, `unknown_workflow`) a postup pro agenta.
- Testy: `aifactory/tests/onboard/onboard_repo.py` (fixtury s kopií `.factory/` HAIFA, sssf a holými remote) a `aifactory/tests/onboard/test_onboard.py`. V `aifactory/tests/test_smoke.py` je `onboard` mezi implementovanými příkazy.

## Jak používat

1. `factory check --json`: musí vrátit `state: pre_library` a `action: onboard`.
2. `factory onboard --dry-run --json`. Uživateli ukaž `data.report`, `data.files`, `data.library_plan.files` a `data.digest`.
3. Až uživatel souhlasí: `factory onboard --commit [--pr] --expect <digest> --json`.
4. Ostatní stroje pak spustí `factory adopt`. Druhý `onboard` skončí blokátorem `already_onboarded`.

## Jak ověřit

```bash
uv run pytest aifactory/tests/onboard/test_onboard.py
just test && just typecheck && just lint
```

Testy pokrývají tyto scénáře:
- kopie HAIFA: dry-run i commit, agenti se napojí, přibude manifest a workflow backlogu.
- sandbox: nové položky, `--keep-local` a chybné volby.
- `already_onboarded` po úspěchu.
- `onboarded_in_remote` z druhého klonu.
- `onboarding_pending`: lokální i pushnutá větev a PR.
- `remote_unchecked` a `no_remote`.
- odmítnutý push knihovny nechá repo beze změny.
- odmítnutý push repa po pushi knihovny a následné opakování.
- `source_not_committed`, `library_missing`, `library_dirty` a stavové blokátory.
- neznámé workflow z backlogu.
- stabilita digestu a textový výstup.

Testy nevolají model ani síť.
