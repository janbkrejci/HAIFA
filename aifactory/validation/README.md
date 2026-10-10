# Validační scénáře aifactory (`just validate`)

Skript připraví testovací repo se šablonou backlogu (`template/`) a spustí scénáře nad CLI `factory`. Ověřují rizika R1 až R5 a R10 z `docs/product-brief.md`, řešení konfliktu přes `task resolve` (RESOLVE) hlídač zápisů do hlavního checkoutu (B1) a akceptační scénář fáze F2 (F2). Každý běh úkolu má vynucené opravné kolo review → revise. R10 má navíc vynucené kolo test → fix.

```
just validate --remote local     # bez sítě a bez modelů, zdarma
just validate --remote github    # sandbox z HAIFA_SANDBOX_REPO, skutečné harnessy
```

Další přepínače:
- `--only R1,RESOLVE`: jen vybrané scénáře. Pořadí je vždy R1, R10, R2, RESOLVE, R3, R4, R5, B1, F2. Když scénáři chybí předpoklad z dřívějšího scénáře, vyjde `inconclusive` (třeba RESOLVE bez konfliktu z R2).
- `--workdir PATH`: pracovní adresář. Výchozí je nový dočasný adresář.
- `--keep-workdir`: pracovní adresář se na konci nesmaže. Bez tohoto přepínače se smaže, ale jen pokud ho skript sám vytvořil.
- `--results-dir PATH`: kam se zapíšou výsledky (výchozí `aifactory/validation/results`).
- `--r5-samples N`: počet měřených worktree (výchozí 3).
- `--roster DIR`: pro daný běh nahradí `.factory/agents.yaml` a `.factory/workflows/simple-sdlc.yaml` ze šablony sandboxu soubory `DIR/agents.yaml` a `DIR/workflows/simple-sdlc.yaml`.
  - Relativní cesta se bere od kořene HAIFA.
  - Roster musí mít agenty `planner`, `builder`, `tester`, `reviewer` a `documenter`, jinak skript skončí kódem 2.
  - Prompty (`.factory/prompts/`) včetně pravidla reviewera zůstávají ze šablony.
  - Když roster nemá harness, který R1 nebo R10 ověřuje, scénář hlásí `inconclusive` místo `failed`. R1 potřebuje claude, codex i pi v jednom workflow, R10 build i fix na codexu. Skutečná chyba jiného checku zůstává `failed`.
  - Použitý roster a harness po krocích jsou v `summary.json` (`roster`, `harness_per_step`).
  - Příklad: `just validate --remote local --roster aifactory/validation/rosters/pi-haiku` (vše na pi, planner, tester a documenter na claude haiku).
  - Příklad: `just validate --remote github --roster aifactory/validation/rosters/claude-codex-pi` (planner, tester a documenter na claude, builder na codexu, reviewer na pi s modelem z OB5; ověří R1 i R10).

Kód návratu:
- 0: všechny scénáře skončily `passed` nebo `inconclusive`;
- 1: některý scénář skončil `failed`;
- 2: chyba přípravy. Chybí `HAIFA_SANDBOX_REPO`, selže `gh auth status` nebo `factory harness check`, `just` není na PATH, nebo je neúplný roster.

## Režimy

**local**: vytvoří bare repo `remote.git` a klon `repo` v dočasném adresáři. Agenty nahrazuje falešný harness (`fake.py`, `fake_scripts.py`), který zapisuje připravené změny a vrací připravené obálky. Falešný tester pokaždé naplánuje jedinou kontrolu `just test`. Skutečné adaptéry claude, codex a pi jsou zablokované a při zavolání vyhodí chybu. Kódové kroky (`just test`, commity, diff, rebase) běží doopravdy. Tenhle režim pouští test `tests/validation/test_validation_local.py`.

**github**: spouští ho engineer ručně, nikdy test. Potřebuje:
- `HAIFA_SANDBOX_REPO` v `.env` ve tvaru `owner/name`, https nebo ssh URL;
- přihlášené `gh` (jinou binárku lze nastavit přes `AIFACTORY_GH`);
- harnessy rosteru na PATH (šablona: `claude`, `codex` a `pi`).

Skript naklonuje sandbox a z jeho výchozí větve založí novou base větev `haifa-validate/<YYYYMMDD-HHMMSS>`, do které commitne šablonu. `main` sandboxu se nemění. S `--force-with-lease` pushuje jen `task resolve`, a to větev `factory/*`. B1 běží i na githubu s falešným harnessem: hlídač zápisů je kód a model k ověření nepotřebuje.

## Vynucená opravná kola

**test → fix (R10)**: `hidden.py` zapíše skrytý test do `<workdir>/hidden/test_hidden_slugify.py`, tedy mimo repo i worktree. Požadavek ze zadání nejde odvodit: prázdný slug je `x-empty`, tedy `slugify("!!!") == "x-empty"`. Každý příkaz `factory` dostane proměnnou `HAIFA_VALIDATE_HIDDEN=<workdir>/hidden`, ale ta slouží jen jako kanál do `validation.worker`. Worker ji hned odstraní z `os.environ`, takže ji agenti nezdědí, a obalí kódový krok `test` enginu (`aifactory.testing.executor.execute`, spouští kontroly z plánu testera). Jen na dobu tohoto kroku vloží skrytý test do `tests/test_hidden_slugify.py` worktree běhu, kde ho `just test` sandboxu najde sám, a potom ho smaže. Agent ho tak na disku nikdy nevidí a nemůže ho ani odstranit. Cesta je v `info/exclude` sandboxu (ne v `.gitignore`, který agent čte), takže se případný zbytek nikdy necommitne. Proto `test_1` vždy selže a proběhne `fix`. Běhy, ve kterých ještě `slugify` neexistuje, skrytý test přeskočí. Hlavní checkout spouští jen viditelné testy. Kontrola `hidden_unseen_by_agents` ověří, že skrytý test žádný agent neviděl.

**review → revise (všechny běhy)**: reviewer v šabloně (`template/.factory/prompts/reviewer/{system,user}.md`) má pravidlo „Validation rule (haifa-validate)“. V prvním kole vždy zamítne a požaduje přidat řádek `# haifa-validate: revised` na konec prvního změněného souboru. Proběhne tedy `revise_1` a `review_2`, které už schválí. Za revizí přijde `replan` (tester znovu zvolí kontroly) a `retest`. Pravidlo je jen ve validační šabloně, ve výchozí konfiguraci produktu (`aifactory/src/`) není. Hlídá to test. Na githubu rozhoduje skutečný model: když pravidlo nedodrží a schválí hned napoprvé, scénář vyjde `inconclusive`, ne `failed`.

## Kolik to stojí na githubu

Proběhne 13 běhů `simple-sdlc`: R1, R10, 2× R2, R4, v R3 běh `truncate` a jeho vrácení a 5 běhů F2. K tomu jeden běh `resolve`. F2 nenechává otevřené PR ani worktree. Každý běh `simple-sdlc` volá agenty 8krát až 9krát: plan, build, test_plan, review, revise, druhé review, replan, document a v R10 ještě fix. Revize a druhé review jsou proti prototypu navíc. Úkoly mají řádově desítky řádků. Modely nastavuje `template/.factory/agents.yaml`: planner a tester claude `sonnet`, builder codex `gpt-5.5`, reviewer pi, documenter claude `haiku`.

Úklid po běhu na GitHubu dělá engineer ručně:
- zavři zbylé otevřené PR (`M02-S01-T01` z R4 a případné sync PR `factory-sync/*` z R3) přes `gh pr close <n>`;
- smaž větve `factory/*` (včetně `factory/M03-*` a `factory/M04-*` z F2), `factory-sync/*` a `haifa-validate/*` vytvořené během, třeba `git push origin --delete haifa-validate/<stamp>`.

## Výsledky

Výsledky se zapíšou do `results/<YYYY-MM-DD>/<remote>-<HHMMSS>/`:
- `R1.json` … `RESOLVE.json`, `B1.json`, `F2.json`: výsledek scénáře;
- `summary.json`: remote, sandbox, base, commit HAIFA, výsledky a všechny spuštěné příkazy;
- `trace/sssf.db`: kopie trace DB aifactory (`.factory/trace.db` sandboxu);
- `trace/sessions/<run_id>/`: prompty, `raw_output.jsonl` a stav harnessů z běhů, na které výsledky odkazují;
- `logs/`: stderr každého příkazu `factory`, a když běžel falešný harness, i jeho skript a záznam volání.

Lokální výsledky git ignoruje, výsledky z githubu se commitují.

JSON scénáře obsahuje tato pole:
- `outcome`: `passed` znamená, že prošly všechny checks. `failed` znamená, že některý check neprošel nebo scénář spadl (traceback je v `observations`). `inconclusive` znamená, že ověření nešlo provést, třeba když skutečný reviewer schválil hned v prvním kole.
- `checks`: jednotlivá ověření s detailem.
- `observations`: co jsme viděli, včetně omezení aifactory. Na výsledek nemají vliv.
- `evidence`: run-id, PR, commity a cesty do `trace/` relativně k adresáři výsledků.
- `measurements`: čísla, například `overlap_s` (R2), `repair_rounds` (R10), `review_rounds`, náklady a tokeny (R1, R10) nebo časy a velikosti worktree (R5).

## Scénáře

| | Ověřuje |
|---|---|
| R1 | `simple-sdlc.yaml` s plan na claude, build a revise na codexu a review na pi. Fáze jdou v pořadí `request → plan → commit_plan → build → test_plan → test_1 → review_1 → revise_1 → review_2 → replan → retest → commit_build → changes → document → commit_docs`. Harness každé fáze se čte z `agent_start` v trace. `review_1` zamítne, `revise_1` proběhne a `review_2` schválí. Očekávané harnessy se berou z rosteru. |
| R10 | `slugify` neprojde skrytým testem, takže `test_1` selže a jeho výstup obsahuje `HiddenSlugifyTest`. Opravné kolo `fix_1` běží na codexu ve stejné session a `test_2` projde. Běh má i vynucené kolo review. Na githubu se navíc ověří jeden Codex thread (`codex exec resume`). |
| R2 | Dva paralelní běhy (`clamp`, `lerp`) nad stejným řádkem `mathx.py`. Oba PR se otevřou, první se schválí a druhý skončí `conflict` (exit 2) bez změny base. |
| RESOLVE | `factory task resolve` na konfliktní PR z R2: `rebase` → `resolve` (builder) → `test_plan` (tester) → `test`, bez konfliktních značek. Pak `task approve` a oba PR z R2 jsou `merged` a oba úkoly `done` v base. V local režimu ještě `just test` v čistém checkoutu base. |
| R3 | Vazba na task jiného modulu blokuje běh (`unmet_dependencies`, exit 2). Pak přijde schválení ve factory (`status: done` a řádek pod `## Běhy` v base) a merge mimo factory. Následuje `backlog sync`, který otevře sync PR, a jeho merge. Dál vrácený PR (nový běh na stejné větvi) a zavřený PR: approve ho odmítne (`pr_not_open`, exit 2) a sync ho ignoruje. |
| R4 | Necommitnutá změna promptu i `agents.yaml` (`thinking: high` u planneru) se do běhu nedostane, protože konfigurace se čte z commitu v base. Běh na ni upozorní ve `warnings`. |
| R5 | Čas `git worktree add`, velikost a počet souborů worktree a velikost `.git`. |
| B1 | Falešný builder zapíše do hlavního checkoutu: nový soubor `B1-breach.md` a řádek do sledovaného `README.md`. Hlídač zápisy vrátí a fáze `build` selže (event `permission_breach`). Běh skončí `run_failed` (exit 1) a neotevře PR. Hlavní checkout zůstane jako předtím. Gitignorované soubory hlídač nevidí, proto B1 zapisuje jen do negitignorovaných. |
| F2 | Akceptace fáze F2 jen přes CLI. Scénář zapíše `index.md` modulů M03 (Unit conversions) a M04 (Statistics) a přes `factory task add` založí 5 tasků s vazbami: `M03-S01-T02` → `M03-S01-T01`, `M04-S01-T02` → `M04-S01-T01` a `M04-S01-T03` → `M03-S01-T01` + `M04-S01-T01` (vazba přes modul). `M03-S01-T01` a `M04-S01-T01` běží současně (`runs_overlapped`) a schválí se. `task run M04-S01-T02 --auto` spustí i `M04-S01-T03` a řetěz skončí `exhausted`. Pak běží `M03-S01-T02` a zbylé tři tasky se schválí přes `task approve`. Kontroly: 5 mergnutých PR, `status: done` a odkaz na PR pod `## Běhy` u všech 5 tasků v base, žádný zápis mimo worktree (stav hlavního checkoutu, event `permission_breach`, do base jen povolené cesty), žádný zbylý worktree, `backlog check` projde a v local režimu i `just test` v čistém checkoutu base. Na ostatních scénářích nezávisí. |
