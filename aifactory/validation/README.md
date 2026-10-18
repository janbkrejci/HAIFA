# Validační scénáře aifactory (`just validate`)

Skript připraví testovací repo se šablonou backlogu (`template/`) a spustí scénáře nad CLI `factory`. Ověřují rizika R1 až R5 a R10 (viz Scénáře), řešení konfliktu přes `task resolve` (RESOLVE), hlídač zápisů do hlavního checkoutu (B1) a akceptační scénář fáze F2 (F2). Každý běh úkolu má vynucené opravné kolo review → revise. R10 má navíc vynucené kolo test → fix.

```
just validate --remote local     # bez sítě a bez modelů, zdarma
just validate --remote github    # sandbox z HAIFA_SANDBOX_REPO, skutečné harnessy
just validate --remote azure     # sandbox z HAIFA_AZURE_SANDBOX_REPO na Azure DevOps, skutečné harnessy
```

Další přepínače:
- `--only R1,RESOLVE`: jen vybrané scénáře. Pořadí je vždy R1, R10, R2, RESOLVE, R3, R4, R5, B1, F2. Když scénáři chybí předpoklad z dřívějšího scénáře, vyjde `inconclusive` (třeba RESOLVE bez konfliktu z R2). Výjimkou je R3: když R1 nebo R10 v `--only` vůbec nejsou, spustí jejich úkoly (`M02-S01-T02`, `M01-S02-T01`) sám. Když vybrané jsou, ale selhaly, R3 je znovu nespouští.
- `--workdir PATH`: pracovní adresář. Výchozí je nový dočasný adresář.
- `--keep-workdir`: pracovní adresář se na konci nesmaže. Bez tohoto přepínače se smaže, ale jen pokud ho skript sám vytvořil.
- `--results-dir PATH`: kam se zapíšou výsledky (výchozí `aifactory/validation/results`).
- `--r5-samples N`: počet měřených worktree (výchozí 3).
- `--roster DIR`: pro daný běh nahradí `.factory/agents.yaml` a `.factory/workflows/simple-sdlc.yaml` ze šablony sandboxu soubory `DIR/agents.yaml` a `DIR/workflows/simple-sdlc.yaml`.
  - Relativní cesta se bere od kořene HAIFA.
  - Roster musí mít agenty `planner`, `builder`, `tester`, `test-reviewer`, `reviewer` a `documenter`, jinak skript skončí kódem 2.
  - Prompty (`.factory/prompts/`) včetně pravidla reviewera zůstávají ze šablony.
  - Když roster nemá harness, který R1 nebo R10 ověřuje, scénář hlásí `inconclusive` místo `failed`. R1 potřebuje claude, codex i pi v jednom workflow, R10 build i fix na codexu. Skutečná chyba jiného checku zůstává `failed`.
  - Použitý roster a harness po krocích jsou v `summary.json` (`roster`, `harness_per_step`).
  - Příklad: `just validate --remote local --roster aifactory/validation/rosters/pi-haiku` (vše na pi, planner, tester, test-reviewer a documenter na claude haiku).
  - Příklad: `just validate --remote github --roster aifactory/validation/rosters/claude-codex-pi` (planner, tester, test-reviewer a documenter na claude, builder na codexu, reviewer na pi s modelem z OB5; ověří R1 i R10).
  - Příklad: `just validate --remote azure --only R2,RESOLVE,R3,F2 --roster aifactory/validation/rosters/claude-sonnet` (všichni agenti na claude `sonnet`; R1 a R10 by s ním vyšly `inconclusive`, R2, RESOLVE, R3 a F2 harness neověřují).

Kód návratu:
- 0: všechny scénáře skončily `passed` nebo `inconclusive`;
- 1: některý scénář skončil `failed`;
- 2: chyba přípravy. Chybí `HAIFA_SANDBOX_REPO` nebo `HAIFA_AZURE_SANDBOX_REPO`, selže `gh auth status`, kontrola `az` (instalace, rozšíření `azure-devops`, přihlášení, dostupnost sandboxu, přístup gitu) nebo `factory harness check`, `just` není na PATH, nebo je neúplný roster.

## Režimy

**local**: vytvoří bare repo `remote.git` a klon `repo` v dočasném adresáři. Agenty nahrazuje falešný harness (`fake.py`, `fake_scripts.py`), který zapisuje připravené změny a vrací připravené obálky. Falešný tester pokaždé naplánuje jedinou kontrolu `just test` a falešný test-reviewer každý plán schválí. Skutečné adaptéry claude, codex a pi jsou zablokované a při zavolání vyhodí chybu. Kódové kroky (`just test`, commity, diff, rebase) běží doopravdy. Tenhle režim pouští test `tests/validation/test_validation_local.py`.

**github**: spouští ho engineer ručně, nikdy test. Potřebuje:
- `HAIFA_SANDBOX_REPO` v `.env` ve tvaru `owner/name`, https nebo ssh URL;
- přihlášené `gh` (jinou binárku lze nastavit přes `AIFACTORY_GH`);
- harnessy rosteru na PATH (šablona: `claude`, `codex` a `pi`).

Skript naklonuje sandbox a z jeho výchozí větve založí novou base větev `haifa-validate/<YYYYMMDD-HHMMSS>`, do které commitne šablonu. `main` sandboxu se nemění. S `--force-with-lease` pushuje jen `task resolve`, a to větev `factory/*`. B1 běží i na githubu s falešným harnessem: hlídač zápisů je kód a model k ověření nepotřebuje.

**azure**: spouští ho engineer ručně, nikdy test. Potřebuje:
- `HAIFA_AZURE_SANDBOX_REPO` v `.env` nebo v prostředí ve tvaru `https://<org>.visualstudio.com/<projekt>/_git/<repo>`, `https://dev.azure.com/<org>/<projekt>/_git/<repo>` (klonovací URL i s `org@`) nebo `<org>/<projekt>/<repo>`;
- `az` s rozšířením `azure-devops` (`az extension add --name azure-devops`), přihlášené přes `az login --allow-no-subscriptions`, nebo token v `AZURE_DEVOPS_EXT_PAT`. Jinou binárku lze nastavit přes `AIFACTORY_AZ` (stejně jako provider);
- harnessy rosteru na PATH a `just`.

Preflight ověří `az --version`, rozšíření, přihlášení (`az account show`, s `AZURE_DEVOPS_EXT_PAT` se přeskočí), sandbox (`az repos show`) a že git sandbox přečte (`git ls-remote`).

Git se k Azure DevOps přihlašuje přes HTTPS credential helper, který při každém volání gitu vypíše čerstvý token z `az account get-access-token` (resource Azure DevOps), nebo `AZURE_DEVOPS_EXT_PAT`. Helper je v repo-lokální konfiguraci klonu, takže ho sdílejí i worktree, které vytváří HAIFA. Globální helpery (třeba keychain) se pro sandbox vypnou, token se nikam neukládá.

Skript naklonuje sandbox a z jeho výchozí větve založí base větev `haifa-validate/<YYYYMMDD-HHMMSS>`. Výchozí větev sandboxu se nemění. Do `.factory/config.yaml` sandboxu přidá sekci `azure` (organizace, projekt, repo). Merge PR mimo factory (R3) jde přes `az repos pr update --status completed --squash true` a validace čeká, až Azure PR dokončí. Zavření PR mimo factory jde přes `az repos pr update --status abandoned`.

## Azure E2E s povinným schválením (`just validate-azure-e2e`)

Samostatný scénář (`azure_e2e.py`), spouští ho operátor ručně, nikdy CI ani test. Ověřuje, že repo, do jehož `main` vede cesta jen přes PR s aspoň jedním schvalovatelem, projde s HAIFA bez člověka.

```
just validate-azure-e2e                         # asolcz.visualstudio.com, projekt NEO_HEF
just validate-azure-e2e --org URL --project P   # jiná organizace nebo projekt
```

Přepínače: `--name HAIFA-E2E-…` (výchozí `HAIFA-E2E-<datum>-<čas>-<hex>`; jméno musí začínat `HAIFA-E2E-`, `NEO_HEF` ani `HAIFA-Azure-Sandbox` nikdy), `--results-dir`, `--keep-workdir` (nechá lokální klon a logy, Azure repo se smaže vždy).

Předpoklady: `az` s rozšířením `azure-devops`, přihlášení (`az account show`, nebo `AZURE_DEVOPS_EXT_PAT`) a dostupný projekt. Bez nich skript skončí kódem 2 dřív, než na Azure cokoli změní. Modely ani `just` nepotřebuje: agenty nahrazuje falešný harness.

Kroky:
1. `az repos create` založí dočasné repo a do `main` se pushne počáteční commit.
2. Politika na `main`: minimálně 1 schvalovatel, autorův hlas se počítá (`creatorVoteCounts`), bez resetu po pushi. Přímý push do `main` musí Azure odmítnout (TF402455).
3. Klon v dočasném adresáři se přidá do HAIFA stejně jako `POST /api/repos` (`add_repo`) s `base_changes: pr` a `base_pr_merge: auto`. Instalace jde přes PR `factory-init/<n>`, který factory schválí vlastním hlasem a mergne. Lokální `main` ho obsahuje a shoduje se s remote.
4. Backlog (projekt `E2E`, workflow `build-review`, `auto_continue` a `auto_merge`, dva závislé tasky) jde přes `factory backlog commit` jako PR `factory-backlog/<n>`, automaticky schválený a mergnutý.
5. `factory task run E2E-S01-T01 --auto` nad falešným harnessem: každý task má PR, auto-merge hlásí `reviewed: true`, PR je na Azure `completed` s hlasem autora 10 a bez `bypassPolicy`. Druhý task spustil řetěz sám (`started_by: auto-continue`), řetěz skončí `exhausted`.
6. Lokální `main` = remote, oba tasky mají v remote base `status: done` a odkaz na PR pod `## Běhy`, `task_prs` je `merged` a hlavní checkout je čistý.

Úklid běží ve `finally`, i po chybě nebo Ctrl+C: odregistrování z dashboardu (vlastní HAIFA home běhu, dashboard operátora se nemění), smazání politiky, `az repos delete` dočasného repa (jen podle jeho id), vysypání z koše projektu (recycle bin) a smazání lokálního adresáře. Pak se repo i politika znovu vyhledají. Azure smazanou politiku dál vrací podle id s `isDeleted: true`, to se počítá jako smazaná. Co zůstane, je chyba úklidu a celý běh skončí `failed`.

Výsledek je `results/<datum>/azure-e2e-<čas>/azure-e2e.json`: `outcome` (`passed`/`failed`), každý krok s `ok`, popisem, URL PR, hlasy, SHA hlavy a merge commitu, dále úklid (`cleanup.ok` a jeho kroky) a všechna volání `az` a `factory`. Logy příkazů jsou v `logs/` (git je ignoruje). Kód návratu: 0 prošlo, 1 selhal krok nebo úklid, 2 preflight.

## Vynucená opravná kola

**test → fix (R10)**: `hidden.py` zapíše skrytý test do `<workdir>/hidden/test_hidden_slugify.py`, tedy mimo repo i worktree. Požadavek ze zadání nejde odvodit: prázdný slug je `x-empty`, tedy `slugify("!!!") == "x-empty"`. Každý příkaz `factory` dostane proměnnou `HAIFA_VALIDATE_HIDDEN=<workdir>/hidden`, ale ta slouží jen jako kanál do `validation.worker`. Worker ji hned odstraní z `os.environ`, takže ji agenti nezdědí, a obalí kódový krok `test` enginu (`aifactory.testing.executor.execute`, spouští kontroly z plánu testera). Jen na dobu tohoto kroku vloží skrytý test do `tests/test_hidden_slugify.py` worktree běhu, kde ho `just test` sandboxu najde sám, a potom ho smaže. Agent ho tak na disku nikdy nevidí a nemůže ho ani odstranit. Cesta je v `info/exclude` sandboxu (ne v `.gitignore`, který agent čte), takže se případný zbytek nikdy necommitne. Proto `test_1` vždy selže. Tester ho posoudí (`triage_1`, falešný tester odpoví `failure_cause: code`), proběhne `fix` a po něm nový plán kontrol (`test_plan_1`) s jeho kontrolou (`test_review_1`). Běhy, ve kterých ještě `slugify` neexistuje, skrytý test přeskočí. Hlavní checkout spouští jen viditelné testy. Kontrola `hidden_unseen_by_agents` ověří, že skrytý test žádný agent neviděl.

**review → revise (všechny běhy)**: reviewer v šabloně (`template/.factory/prompts/reviewer/{system,user}.md`) má pravidlo „Validation rule (haifa-validate)“. V prvním kole vždy zamítne a požaduje přidat řádek `# haifa-validate: revised` na konec prvního změněného souboru. Proběhne tedy `revise_1`, `replan_1` (tester podle review znovu zvolí kontroly), `test_review_1` (test-reviewer plán schválí), `retest_1` a `review_2`, které už schválí. Pravidlo je jen ve validační šabloně, ve výchozí konfiguraci produktu (`aifactory/src/`) není. Hlídá to test. Na githubu rozhoduje skutečný model: když pravidlo nedodrží a schválí hned napoprvé, scénář vyjde `inconclusive`, ne `failed`.

## Kolik to stojí na hostingu (github, azure)

Celá sada spustí 13 běhů `simple-sdlc`: R1, R10, 2× R2, R4, v R3 běh `truncate` a jeho vrácení a 5 běhů F2. K tomu jeden běh `resolve`. F2 nenechává otevřené PR ani worktree. Každý běh `simple-sdlc` volá agenty 10krát až 14krát: plan, build, test_plan, test_review, review, revise, replan, test_review, druhé review, document a v R10 ještě triage, fix, test_plan a test_review po opravě. Každý uložený plán testů kontroluje test-reviewer (`test_review`). Revize a druhé review jsou proti prototypu navíc. Úkoly mají řádově desítky řádků. Modely nastavuje `template/.factory/agents.yaml`: planner, tester a test-reviewer claude `sonnet`, builder codex `gpt-5.5`, reviewer pi, documenter claude `haiku`.

`--only R2,RESOLVE,R3,F2` spustí 2 běhy R2, jeden `resolve`, 3 běhy v R3 (předpoklady R10 a R1 a `truncate`) plus jeho vrácení a 5 běhů F2.

Úklid po běhu na GitHubu dělá engineer ručně:
- zavři zbylé otevřené PR (`M02-S01-T01` z R4 a případné sync PR `factory-sync/*` z R3) přes `gh pr close <n>`;
- smaž větve `factory/*` (včetně `factory/M03-*` a `factory/M04-*` z F2), `factory-sync/*` a `haifa-validate/*` vytvořené během, třeba `git push origin --delete haifa-validate/<stamp>`.

Úklid po běhu na Azure DevOps (s `--keep-workdir`, klon `<workdir>/repo` má credential helper):
- vypiš aktivní PR: `az repos pr list --org <org-url> --project <projekt> --repository <repo> --status active --detect false -o table`;
- PR z běhu (cíl `haifa-validate/<stamp>`, třeba sync PR `factory-sync/*` nebo `M02-S01-T01` z R4) opusť přes `az repos pr update --id <n> --org <org-url> --status abandoned`. PR do výchozí větve a PR, které nevytvořil tento běh, nech být;
- najdi větve běhu: `git -C <workdir>/repo ls-remote --heads origin 'factory/*' 'factory-sync/*' 'haifa-validate/*'` a smaž je: `git -C <workdir>/repo push origin --delete haifa-validate/<stamp> factory/<…> factory-sync/<…>`. Bez klonu jde i `az repos ref delete --name heads/<větev> --object-id <sha> --org <org-url> --project <projekt> --repository <repo>`;
- nakonec smaž pracovní adresář. Výchozí větev sandboxu má mít stejný commit jako před během.

## Výsledky

Výsledky se zapíšou do `results/<YYYY-MM-DD>/<remote>-<HHMMSS>/`:
- `R1.json` … `RESOLVE.json`, `B1.json`, `F2.json`: výsledek scénáře;
- `summary.json`: remote, sandbox, base, commit HAIFA, výsledky a všechny spuštěné příkazy;
- `trace/sssf.db`: kopie trace DB aifactory (`.factory/trace.db` sandboxu);
- `trace/sessions/<run_id>/`: prompty, `raw_output.jsonl` a stav harnessů z běhů, na které výsledky odkazují;
- `logs/`: stderr každého příkazu `factory`, a když běžel falešný harness, i jeho skript a záznam volání.

Lokální výsledky git ignoruje, výsledky z githubu a z azure se commitují.

JSON scénáře obsahuje tato pole:
- `outcome`: `passed` znamená, že prošly všechny checks. `failed` znamená, že některý check neprošel nebo scénář spadl (traceback je v `observations`). `inconclusive` znamená, že ověření nešlo provést, třeba když skutečný reviewer schválil hned v prvním kole.
- `checks`: jednotlivá ověření s detailem.
- `observations`: co jsme viděli, včetně omezení aifactory. Na výsledek nemají vliv.
- `evidence`: run-id, PR, commity a cesty do `trace/` relativně k adresáři výsledků.
- `measurements`: čísla, například `overlap_s` (R2), `repair_rounds` (R10), `review_rounds`, náklady a tokeny (R1, R10) nebo časy a velikosti worktree (R5).

## Scénáře

| | Ověřuje |
|---|---|
| R1 | `simple-sdlc.yaml` s plan na claude, build a revise na codexu a review na pi. Fáze jdou v pořadí `request → plan → commit_plan → build → test_plan → test_review → test_1 → review_1 → revise_1 → replan_1 → test_review_1 → retest_1 → review_2 → commit_build → changes → document → commit_docs`. Harness každé fáze se čte z `agent_start` v trace. `review_1` zamítne, `revise_1` proběhne a `review_2` schválí. Očekávané harnessy se berou z rosteru. |
| R10 | `slugify` neprojde skrytým testem, takže `test_1` selže a jeho výstup obsahuje `HiddenSlugifyTest`. Tester ho v `triage_1` přisoudí kódu. Opravné kolo `fix_1` běží na codexu ve stejné session a `test_2` projde. Běh má i vynucené kolo review. Na githubu se navíc ověří jeden Codex thread (`codex exec resume`). |
| R2 | Dva paralelní běhy (`clamp`, `lerp`) nad stejným řádkem `mathx.py`. Oba PR se otevřou, první se schválí a druhý skončí `conflict` (exit 2) bez změny base. |
| RESOLVE | `factory task resolve` na konfliktní PR z R2: `rebase` → `resolve` (builder) → `test_plan` (tester) → `test_review` (test-reviewer) → `test`, bez konfliktních značek. Pak `task approve` a oba PR z R2 jsou `merged` a oba úkoly `done` v base. V local režimu ještě `just test` v čistém checkoutu base. |
| R3 | Když R10 nebo R1 nejsou vybrané, R3 nejdřív sám spustí jejich úkoly a otevře jejich PR (neúspěšný běh je check `prerequisite_<task>`). Vazba na task jiného modulu blokuje běh (`unmet_dependencies`, exit 2). Pak přijde schválení ve factory (`status: done` a řádek pod `## Běhy` v base) a merge mimo factory. Následuje `backlog sync`, který otevře sync PR, a jeho merge. Dál vrácený PR (nový běh na stejné větvi) a zavřený PR: approve ho odmítne (`pr_not_open`, exit 2) a sync ho ignoruje. |
| R4 | Necommitnutá změna promptu i `agents.yaml` (`thinking: high` u planneru) se do běhu nedostane, protože konfigurace se čte z commitu v base. Běh na ni upozorní ve `warnings`. |
| R5 | Čas `git worktree add`, velikost a počet souborů worktree a velikost `.git`. |
| B1 | Falešný builder zapíše do hlavního checkoutu: nový soubor `B1-breach.md` a řádek do sledovaného `README.md`. Hlídač zápisy vrátí a fáze `build` selže (event `permission_breach`). Běh skončí `run_failed` (exit 1) a neotevře PR. Hlavní checkout zůstane jako předtím. Gitignorované soubory hlídač nevidí, proto B1 zapisuje jen do negitignorovaných. |
| F2 | Akceptace fáze F2 jen přes CLI. Scénář zapíše `index.md` modulů M03 (Unit conversions) a M04 (Statistics) a přes `factory task add` založí 5 tasků s vazbami: `M03-S01-T02` → `M03-S01-T01`, `M04-S01-T02` → `M04-S01-T01` a `M04-S01-T03` → `M03-S01-T01` + `M04-S01-T01` (vazba přes modul). `M03-S01-T01` a `M04-S01-T01` běží současně (`runs_overlapped`) a schválí se. `task run M04-S01-T02 --auto` spustí i `M04-S01-T03` a řetěz skončí `exhausted`. Pak běží `M03-S01-T02` a zbylé tři tasky se schválí přes `task approve`. Kontroly: 5 mergnutých PR, `status: done` a odkaz na PR pod `## Běhy` u všech 5 tasků v base, žádný zápis mimo worktree (stav hlavního checkoutu, event `permission_breach`, do base jen povolené cesty), žádný zbylý worktree, `backlog check` projde a v local režimu i `just test` v čistém checkoutu base. Na ostatních scénářích nezávisí. |
