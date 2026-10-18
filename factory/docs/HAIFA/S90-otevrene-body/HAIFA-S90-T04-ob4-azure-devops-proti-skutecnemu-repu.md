# HAIFA-S90-T04 — OB4: Azure DevOps proti skutečnému repu

Validace (`just validate`) má nový režim `--remote azure`. Scénáře R2, RESOLVE,
R3 a F2 v něm běží proti skutečnému repu na Azure DevOps se skutečnými
harnessy. Falešné `az` v testech provideru teď vypisuje totéž co skutečné
`az` 2.91 (rozšíření azure-devops 1.0.9). Logika `providers/azure.py` se nezměnila,
upravil se jen docstring: provider už se skutečným `az` fungoval.

## Výsledek běhu

`aifactory/validation/results/2026-10-18/azure-172554/`: R2, RESOLVE, R3 i F2
mají `outcome: passed`. Sandbox byl
`https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox`, base
`haifa-validate/20261018-172554` a roster `rosters/claude-sonnet`.

## Režim `--remote azure`

- **Sandbox** se zadává v `HAIFA_AZURE_SANDBOX_REPO`, v `.env` nebo v prostředí.
  `sandbox.normalize_azure_repo` přijme `https://<org>.visualstudio.com/<projekt>/_git/<repo>`,
  `https://dev.azure.com/<org>/<projekt>/_git/<repo>` (i s `org@`) nebo
  `<org>/<projekt>/<repo>` a vrátí `AzureRepo` (URL organizace, projekt, repo).
  Když proměnná chybí, skončí to exit 2, a to ještě před spuštěním jakéhokoli procesu.
- **Preflight** (`runner.preflight_azure`) kontroluje postupně `just`,
  `az --version`, rozšíření `azure-devops`, přihlášení (`az account show`;
  s `AZURE_DEVOPS_EXT_PAT` se přeskočí), sandbox (`az repos show`), přístup gitu
  (`git ls-remote`) a harnessy rosteru. Kontroly harnessů a `just` jsou
  společné s režimem github (`_require_just`, `_preflight_harnesses`). Binárku
  `az` jde přepsat přes `AIFACTORY_AZ`.
- **Autentizace gitu** jde přes credential helper
  (`sandbox.azure_credential_helper`). Při každém volání gitu vypíše
  `$AZURE_DEVOPS_EXT_PAT`, a když ten chybí, čerstvý token z
  `az account get-access-token --resource 499b84ac-…`. Helper se zapíše do
  repo-lokální konfigurace klonu, takže ho zdědí i worktree, které vytváří
  HAIFA. Globální helpery se vynulují a token se nikam neukládá.
- **Sandbox** (`sandbox.setup_azure`) naklonuje repo a z výchozí větve založí
  `haifa-validate/<stamp>`. Výchozí větev zůstane beze změny. Šablona
  `config.yaml.tmpl` má nový zástupný symbol `$provider_settings`, za který se
  pro azure vloží sekce `azure:` (organizace, projekt, repo). Pro local
  a github zůstane prázdný.
- **Scénáře** (`scenarios.py`): merge mimo factory v R3 volá
  `az repos pr update --status completed --squash true` a čeká, dokud PR
  není `completed` (nejdéle 120 s). Zavření PR je `--status abandoned`. Číslo PR
  se podle větve hledá přes `az repos pr list --status all`. R3 zapíše do
  pozorování hlasy recenzentů po `task approve` (`az repos pr reviewer list`).
  Hlášky, které dřív zmiňovaly jen GitHub, teď uvádějí hosting (`ctx.hosting`).
- **Předpoklady R3**: nová první fáze `prerequisites`. Když R10 nebo R1 nejsou
  v `--only`, R3 sám spustí jejich úkoly (`R10_TASK`, `R1_TASK`). Když vybrané
  jsou, ale selhaly, znovu se nespouštějí. Neúspěšný běh se zapíše jako check
  `prerequisite_<task>`. Kvůli tomu `Context` dostal pole `selected`.
- **Roster `rosters/claude-sonnet`** obsahuje všechny agenty i kroky
  `simple-sdlc` na claude `sonnet`. Komentář v `agents.yaml` vysvětluje proč:
  codex neumí gpt-5.5 s ChatGPT účtem a haiku neopravil slugify v R10.
  R1 a R10 s tímto rosterem vyjdou `inconclusive`.

## Rozdíly skutečného `az` proti falešnému

Promítnuté do `tests/providers/az_fake.py` a testů:
- `repository.webUrl` je v `pr create/show/list` `null`, takže provider
  skládá URL PR z nastavení. Výchozí `pr_json` má teď `webUrl: None`. Přibyl
  test `test_create_pr_url_from_web_url` pro případ, kdy `webUrl` vyplněné je.
- Data mají šest desetinných míst a offset (`…37.209982+00:00`). Nový případ
  je v `test_utc_iso.py`.
- `lastMergeCommit` je `null`, dokud PR není dokončený. Opuštěný PR má
  `mergeStatus: null` a `test_status` pro to dostal nový případ.
- Chybějící PR se hlásí jako `ERROR: TF401180 …` s exit 1, výsledek je `az_failed`.

## Ověření

- `cd aifactory && uv run pytest tests/providers tests/validation -n0` spustí nový
  `test_validation_azure.py`. Ten pokrývá parsování URL, credential helper,
  sekci `azure` v configu, preflight proti falešnému `az` a předpoklady R3.
  Testy validace skrývají i `HAIFA_AZURE_SANDBOX_REPO`.
- Živý běh spouští jen engineer, ručně:
  `just validate --remote azure --only R2,RESOLVE,R3,F2 --roster aifactory/validation/rosters/claude-sonnet`.
  Výsledky z azure se commitují.
- Úklid po běhu (PR přes `az repos pr update --status abandoned` a větve
  `factory/*`, `factory-sync/*`, `haifa-validate/*`) je popsaný
  v `aifactory/validation/README.md` v části „Úklid po běhu na Azure DevOps“.
