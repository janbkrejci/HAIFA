# HAIFA-S01-T20: Přidání repozitáře, správa repozitářů a záložka Factory

## Co se změnilo

Repozitář jde nově přidat a odebrat přímo v dashboardu, už ne jen příkazem `factory obs --repo`. Každé repo má navíc záložku **Factory** s výsledkem `factory check`. Frontend používá serverová API `/api/repos/inspect`, `POST /api/repos`, `DELETE /api/repos/<id>`, `/api/fs/dirs`, `/api/fs/pick` a `/api/dashboard/settings`. Tento diff je nemění, z backendu jen rozšiřuje odpověď kontroly factory a mění cíl `factory obs`.

Přidání ani odebrání nic nezapíše do repa, mění se jen registr dashboardu (`dashboard.yaml`).

### `#/repos/add`: průvodce přidáním (`views/ReposAddView.vue`)

- **Složka.** Pole cesty je předvyplněné `~/`. Komponenta `components/repos/PathField.vue` našeptává podsložky z `/api/fs/dirs` se štítky `git` a `factory`. Ovládá se šipkami ↑↓, Enter, Esc, a když je seznam zavřený, Enter spustí kontrolu. Tlačítko **Procházet…** otevře modál `components/repos/FolderBrowser.vue`, který začíná v domovské složce. **Vybrat ve Finderu…** se ukáže jen tehdy, když `GET /api/fs/pick` vrátí `available: true`. **Zkontrolovat** zavolá inspect. Na relativní cestu (`usage_error`) odpoví „Zadej absolutní cestu nebo cestu začínající ~.“
- **Karta repa** (`components/repos/InspectCard.vue`) ukazuje kořen repa, větev, remote, stav factory, trace DB a u podsložky „Použije se kořen repozitáře …“. Podle výsledku inspect pak nabídne jedno z tohoto:
  - **problém:** důvod odmítnutí, texty jsou v `lib/addRepo.ts` (`PROBLEM_TEXT`): `path_not_found`, `not_a_directory`, `not_git` („HAIFA nespouští git init“), `linked_worktree` s tlačítkem **Použít hlavní checkout**, `run_worktree`, `bare_repo`, `no_commits` a `trace_db_shared`. Tlačítko Přidat se v tom případě neukáže.
  - **už registrované:** odkaz **Otevřít**.
  - **`none`:** příkazy `factory init --dry-run` a `factory init --commit`, repo se nepřidá.
  - **`sssf`:** příkaz `factory onboard --repo <cesta> --dry-run`, repo se nepřidá.
  - **`pre_library`, `working_tree`, `onboarded`:** tlačítko **Přidat**. U `onboarded` karta ukáže, kdo, kdy a z čeho repo onboardoval (`onboardingText`). U `working_tree` upozorní, že konfigurace není commitnutá. Po přidání `App.vue` znovu načte seznam repozitářů a otevře `#/r/<id>/factory`.

### `#/repos`: správa (`views/ReposView.vue`, `components/RepoList.vue`)

- Tabulka repozitářů má sloupce Název, Cesta, Stav a Přidáno. Tlačítko **Otevřít** vede u repa ve stavu `ok` na Backlog, u ostatních na Factory. Druhé tlačítko je **Odebrat z dashboardu**.
- Odebrání řeší `useRemoveRepo` v `lib/repos.ts`. Před smazáním se zeptá ve sdíleném `ConfirmDialog` textem z `removeConfirm`: „Odebrat <name> z dashboardu? Ve složce <path> se nic nezmění: …“. Potom pošle `DELETE`. Kód `unknown_repo` (repo mezitím odebral někdo jiný) bere jako úspěch. Když je odebírané repo právě otevřené, přejde na `#/overview`.
- Komponenta `components/repos/DashboardSettings.vue` nastavuje port dashboardu (1–65535, platí po restartu, při `restart_required` ukáže poznámku) a zobrazuje cestu k registru a domovskou složku.
- Prázdný stav `#/repos` i přehledu (`views/OverviewView.vue`) nabízí odkaz **Přidat repozitář**. Karta repa v přehledu (`components/overview/RepoCard.vue`) má u stavu `missing` tlačítko Odebrat. Otevřené repo s chybějící složkou ukáže v `App.vue` prázdnou obrazovku s tlačítkem Odebrat.

### Záložka Factory (`views/FactoryView.vue`)

- Nový screen `factory` v `lib/router.ts` (pořadí záložek: Backlog, Běhy, Review, Factory, Nastavení), registrovaný v `components/RepoScreen.vue`.
- Při otevření sama zavolá `GET /api/repos/<id>/factory/check`. Tlačítko **Znovu zkontrolovat** pošle `?fresh=1`.
- Ukazuje verdikt, stav repa, manifest (`formát N, zapsal …`, nebo „bez manifestu“), verzi balíčku, base a commit s počtem commitů napřed a pozadu, onboarding a čas kontroly s příznakem mezipaměti.
- Nálezy dělí do dvou skupin: „Repozitář: opravit a commitnout“ (`scope === 'repo'`) a „Tento počítač: opravit lokálně“ (ostatní scope, nálezy knihovny mají štítek). Uvnitř skupiny jsou seřazené podle závažnosti.
- `fetchFactoryCheck` v `lib/api.ts` vrátí report i u chyby `checks_failed`. Zajišťuje to nový parametr `tolerated` funkce `readEnvelope`. `ApiError` nově nese `data` neúspěšné obálky.

### Backend

- `aifactory/src/aifactory/web/factory.py`: `check_view` přidává `_manifest_view(root)`, tedy `manifest` (`{format, written_by}` nebo `null`), `manifest_error` a `version`. Tyto údaje se nikdy neberou z mezipaměti. Docstring v `web/app.py` je upravený.
- `aifactory/src/aifactory/cli.py`: `factory obs --repo` otevře `#/r/<id>/backlog` jen tehdy, když `repo_status(entry)["status"] == "ok"`. Jinak otevře `#/r/<id>/factory`.

### Build

Do `aifactory/src/aifactory/web/static/` se vygeneroval nový build: `index-CZc3MHpY.js` a `index-BnvgyYHu.css` nahradily `index-BRuX839l.js` a `index-CXZEo5T8.css` a `index.html` na ně odkazuje.

## Ověření

```bash
just test        # mimo jiné test_obs_cli.py, test_web_factory.py
just typecheck
just lint
just e2e         # test_add_and_remove_repo_in_browser
```

- Vitest: `ReposAddView.test.ts` (stavy a chyby průvodce včetně `sssf`, `pre_library` a `onboarded`, našeptávání, viditelnost tlačítka pro Finder), `ReposView.test.ts` (odebrání přes modál, port), `FactoryView.test.ts`, `addRepo.test.ts`, `api.test.ts`, `App.test.ts`, `OverviewView.test.ts` a `router.test.ts`.
- Python: `test_obs_cli.py` kontroluje, že repo bez factory se otevře na `…/factory` a onboardované repo ve stavu `ok` na `…/backlog`. `test_web_factory.py::test_check_carries_manifest_and_version` kontroluje nová pole v odpovědi kontroly.
- E2E `tests/e2e/test_f3_browser.py::test_add_and_remove_repo_in_browser` napíše cestu do pole, repo přidá a ověří, že záložka Factory se zkontrolovala sama. Odpověď `factory/check` podvrhuje přes `page.route`, takže test nevolá claude ani gh. Pak repo odebere přes modál a ověří, že se v repu nic nezměnilo (`git status` je čistý a HEAD stejný).
- Ručně: `just dash`, otevřít `#/repos/add`, zadat cestu ke složce, zkontrolovat ji, přidat repo a pak ho odebrat na `#/repos`.
