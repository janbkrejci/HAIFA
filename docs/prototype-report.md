# HAIFA — zpráva z prototypu (F1) pro bránu G1

2026-09-27 · podklad pro schválení prototypu (G1) · navazuje na [product brief](product-brief.md)

Zpráva uvádí jen to, co je ve výsledcích validace nebo v trace DB. Co v nich není, je označené **CHYBÍ**. Úpravy rozhodnutí jsou jen návrhy. Brief se touto zprávou nemění.

## Zdroje

| Zdroj | Cesta | Obsah |
| --- | --- | --- |
| Běh validace s `--remote github` | [`prototype/validation/results/2026-09-27/github-164507/`](../prototype/validation/results/2026-09-27/github-164507/) | jediný běh s `--remote github` ve výsledcích (a zároveň jediný běh vůbec) |
| Souhrn běhu | [`summary.json`](../prototype/validation/results/2026-09-27/github-164507/summary.json) | 15 příkazů CLI, exit kódy, harness po krocích, výsledky scénářů |
| Výsledky scénářů | [`R1.json`](../prototype/validation/results/2026-09-27/github-164507/R1.json), [`R2.json`](../prototype/validation/results/2026-09-27/github-164507/R2.json), [`R3.json`](../prototype/validation/results/2026-09-27/github-164507/R3.json), [`R4.json`](../prototype/validation/results/2026-09-27/github-164507/R4.json), [`R5.json`](../prototype/validation/results/2026-09-27/github-164507/R5.json), [`R10.json`](../prototype/validation/results/2026-09-27/github-164507/R10.json) | kontroly, pozorování, důkazy, měření |
| Trace validačního běhu | [`trace/sssf.db`](../prototype/validation/results/2026-09-27/github-164507/trace/sssf.db), [`trace/sessions/<run-id>/`](../prototype/validation/results/2026-09-27/github-164507/trace/sessions/) | tabulky `task_runs`, `task_prs`, `sessions`, `phases`, `gate_results`, `envelopes`, `agent_sessions`; prompty a události agentů |
| Trace vývoje prototypu | `adws/adw_data/sssf.db` | 15 sessions sssf, kterými prototyp vznikl (26.–27. 9. 2026) |

**Parametry běhu** (ze `summary.json`):

- sandbox repo `janbkrejci/haifa-sandbox`, base `haifa-validate/20260927-164507`, commit HAIFA `cd84af7`.
- Začátek 14:45:03 UTC, konec 15:11:36 UTC, tedy 26 min 33 s.
- Roster `pi-haiku`. Harness po krocích: plan `claude`, build `pi`, fix `pi`, review `pi`, revise `pi`, document `claude`. Harness `codex` v rosteru není.
- Modely podle `agent_sessions`: planner a documenter `claude` / `haiku`, builder a reviewer `pi` / `nousresearch/stealth/space-bunny-alpha`.
- Výsledky scénářů: R1 `inconclusive`, R10 `inconclusive`, R2 `passed`, R3 `passed`, R4 `passed`, R5 `passed`.

**Běhy úkolů v trace** (tabulky `task_runs` a `sessions`, workflow `simple-sdlc` u všech):

| run-id | Task | Scénář | PR | Stav PR v trace | Doba sessions | Tokeny | Náklady |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `01a37500` | M02-S01-T02 | R1, R3 | [#1](https://github.com/janbkrejci/haifa-sandbox/pull/1) | merged (mimo HAIFA, squash) | 261,5 s | 507 524 | $0,1230 |
| `11efaa43` | M01-S02-T01 | R10, R3 | [#2](https://github.com/janbkrejci/haifa-sandbox/pull/2) | merged | 224,6 s | 530 869 | $0,1340 |
| `24796040` | M01-S01-T01 | R2 | [#4](https://github.com/janbkrejci/haifa-sandbox/pull/4) | merged | 276,3 s | 418 216 | $0,0802 |
| `479a5ba0` | M01-S01-T02 | R2 | [#3](https://github.com/janbkrejci/haifa-sandbox/pull/3) | open (konflikt) | 197,1 s | 338 243 | $0,0874 |
| `13b81e7c` | M01-S02-T02 | R3 | [#5](https://github.com/janbkrejci/haifa-sandbox/pull/5) | open (ve skutečnosti zavřený, viz R3) | 186,2 s | 397 916 | $0,0961 |
| `d90502f3` | M01-S02-T02 (vráceno s poznámkou) | R3 | [#5](https://github.com/janbkrejci/haifa-sandbox/pull/5) | dtto | 232,9 s | 582 485 | $0,1123 |
| `00607ef9` | M02-S01-T01 | R4 | [#6](https://github.com/janbkrejci/haifa-sandbox/pull/6) | open | 220,8 s | 662 042 | $0,1365 |
| **celkem** | | | 6 PR | | ⌀ 228 s | 3 437 295 | **$0,7694** |

Všech 7 běhů prošlo 10 fázemi: `request → plan → commit_plan → build → test_1 → review_1 → commit_build → changes → document → commit_docs`. Test prošel napoprvé a reviewer schválil v prvním kole (`ReviewOutput.approved = true`) ve všech sedmi bězích. **Opravných kol (fix, revise) bylo 0.** Jediná opakování byla gate retry fáze `document`, a to ve 4 ze 7 běhů (viz Zjištění Z1).

## Výsledky rizik

Výsledek se vztahuje k riziku:

- **potvrzeno**: riziko se v prototypu projevilo.
- **vyvráceno**: riziko se neprojevilo a návrh ho zvládl.
- **částečně**: ověřena jen část rizika nebo jen část zmírnění.
- **CHYBÍ**: scénář nedal výsledek.

Stav z validátoru (`passed` nebo `inconclusive`) je uveden zvlášť.

### R1 — YAML workflow nevyjádří logiku dnešních ADW

**Výsledek: částečně** (validátor: `inconclusive`). Riziko je na šťastné cestě vyvrácené. Smyčky a podmínky neproběhly, takže u nich chybí důkaz.

- **Důkaz:** [`R1.json`](../prototype/validation/results/2026-09-27/github-164507/R1.json), run `01a37500`, PR [#1](https://github.com/janbkrejci/haifa-sandbox/pull/1), trace `trace/sessions/01a37500/`.
- **Měření:** 10 fází ve stejném pořadí jako Python `adw_simple_sdlc.py` na šťastné cestě (kontrola `phase_order` ok, `all_phases_ok` ok). Běh trval 262,1 s, spotřeboval 507 524 tokenů a stál $0,1230. Opravných kol bylo 0. Tokeny po fázích: plan 131 508, build 99 725, review_1 112 360, document 163 931.
- **Co se neověřilo:**
  - Smyčka `repeat` test → fix ani review → revise neproběhla. Žádný ze 7 běhů neměl fázi `fix`, `revise`, `test_2` ani `review_2`.
  - Podmínka `when` na větvi po revizi se neuplatnila.
  - Workflow se třemi harnessy (claude, codex, pi) nešlo spustit, protože roster nemá codex (pozorování v R1.json).
- **Známý rozdíl proti Pythonu** (pozorování v R1.json): když reviewer zamítne i v posledním kole, YAML verze ještě spustí `revise_2`. Výsledek se tím nemění.
- **Srovnání trace se starým během:** R1.json porovnává s popisem fází Python verze, ne se skutečnou trace běhu `adw_simple_sdlc.py` nad sandboxem. **CHYBÍ** trace Python běhu nad stejným úkolem.

### R2 — Paralelní běhy mění stejné soubory a PR kolidují

**Výsledek: potvrzeno** (validátor: `passed`). Paralelní běh funguje a konflikt se odhalí. PR ale kolidují a řeší se ručně, protože zmírnění `resolve` neexistuje.

- **Důkaz:** [`R2.json`](../prototype/validation/results/2026-09-27/github-164507/R2.json), runy `24796040` a `479a5ba0`, PR [#4](https://github.com/janbkrejci/haifa-sandbox/pull/4) (merged, commit `3cd51e1`) a [#3](https://github.com/janbkrejci/haifa-sandbox/pull/3) (open). Log `logs/06-task-approve.log` je prázdný, exit kód a hláška jsou v `summary.json`.
- **Měření:**
  - Běhy se překrývaly 198,0 s. Doba běhu 277,3 s (M01-S01-T01) a 198,0 s (M01-S01-T02). Náklady $0,0802 + $0,0874. Opravných kol bylo 0.
  - Každý běh měl vlastní worktree (`.factory/worktrees/24796040`, `.factory/worktrees/479a5ba0`). Oba změnily sdílený `mathx.py`.
  - První PR se mergnul a `status: done` je v base. Schválení druhého skončilo `exit 1: merge_failed: GraphQL: Pull Request has merge conflicts`. Base zůstala na `3cd51e1`.
- **Pozorování:**
  - GitHub ještě nespočítal mergeability, proto approve hlásí `merge_failed` místo `conflict`.
  - Workflow `resolve` neexistuje. Druhý PR zůstal otevřený a řešil by se ručně (rebase nebo vrácení úkolu).
- **Souvislost se zjištěním Z1:** agent na harnessu Claude zapisoval mimo worktree do hlavního checkoutu. Tyto zápisy kontrola `writes` přes git diff worktree nevidí. Izolace paralelních běhů tedy platí jen pro zápisy uvnitř worktree.

### R3 — Stav `done` přes merge PR nesedí s realitou

**Výsledek: vyvráceno** (validátor: `passed`) pro všechny čtyři cesty PR. Ve výsledcích jsou tři výhrady, viz níže.

- **Důkaz:** [`R3.json`](../prototype/validation/results/2026-09-27/github-164507/R3.json).
  - Runy `11efaa43`, `01a37500`, `13b81e7c`, `d90502f3`.
  - PR [#2](https://github.com/janbkrejci/haifa-sandbox/pull/2) (schválení v HAIFA, merge `569d707`), [#1](https://github.com/janbkrejci/haifa-sandbox/pull/1) (merge mimo HAIFA: `gh pr merge 1 --squash`), [#5](https://github.com/janbkrejci/haifa-sandbox/pull/5) (vráceno, pak zavřeno mimo HAIFA: `gh pr close 5`).
  - Commity `569d707`, `9959dfe`.
- **Měření:**

  | Cesta | Commity přidané do base | Stav tasku v base |
  | --- | --- | --- |
  | Schválení v HAIFA | 1 | `done`, PR uvedený pod `## Běhy` |
  | Merge mimo HAIFA + `backlog sync` | 2 | `todo` před sync, `done` po sync (sync aktualizoval `M02-S01-T02`) |
  | Vrácení s poznámkou | 0 | `todo`; nový běh `13b81e7c → d90502f3` na téže větvi, head PR `ac78006 → 6074fa0`, stále PR 5 |
  | Zavření mimo HAIFA | 0 | `todo`; approve odmítnut (`pr_not_open`), sync zavřený PR ignoruje |

  Vazby: `task run M02-S01-T01` skončil `exit 1: unmet_dependencies … M01-S02-T01 (not_done)`. Po schválení závislosti prošel (run `00607ef9`). Doba scénáře 522,3 s. Náklady běhů scénáře: $0,1340 + $0,0961 + $0,1123 (běh `01a37500` je započten u R1). Opravných kol 0.
- **Výhrady z pozorování:**
  1. `task_prs.state` zavřeného PR 5 zůstal v trace `open`. HAIFA stav `closed` sama nezapisuje.
  2. `require_review: false`, protože GitHub nedovolí schválit vlastní PR. Odeslání approve review se tedy **neověřilo**.
  3. Po merge na GitHubu HAIFA neposune lokální base v hlavním checkoutu. Validace ji dotahuje sama (fetch + ff), jinak by další běh začal ze staré base.
- Logy příkazů `approve`, `show` a `sync` (`logs/05`, `08`, `09`, `10`, `13`, `14`) jsou prázdné (0 B). Výsledky těchto příkazů jsou jen v kontrolách R3.json a v `summary.json`.

### R4 — Běh nevidí necommitnutou změnu promptu z dashboardu

**Výsledek: potvrzeno** (validátor: `passed`). Běh opravdu nevidí necommitnutou změnu promptu. To je chování podle návrhu, zmírnění ale v prototypu chybí. Navíc se ukázala nekonzistence: změna v jiném konfiguračním souboru se naopak projevila.

- **Důkaz:** [`R4.json`](../prototype/validation/results/2026-09-27/github-164507/R4.json), run `00607ef9`, PR [#6](https://github.com/janbkrejci/haifa-sandbox/pull/6), prompt `trace/sessions/00607ef9/planner/prompts/user.md` (obsahuje sentinel `<!-- haifa-validate: committed prompt -->`, marker necommitnuté změny chybí).
- **Měření:**
  - Běh 220,8 s (sessions), $0,1365, 662 042 tokenů, opravných kol 0.
  - Necommitnutá změna `thinking` planneru v `.factory/sssf.config.yaml` se projevila: `planner_thinking = "high"`.
- **Pozorování:**
  - Konfigurace sssf se čte z pracovního stromu hlavního checkoutu, prompty z base.
  - Varování před spuštěním při necommitnutých změnách (D4) prototyp nemá.

### R5 — Worktree na běh je drahý

**Výsledek: částečně** (validátor: `passed`). Na malém sandboxu je worktree levný. Náklad pro .NET build a `node_modules` se neměřil a **CHYBÍ**.

- **Důkaz:** [`R5.json`](../prototype/validation/results/2026-09-27/github-164507/R5.json). Scénář měří samostatné worktree bez běhu agenta, run-id ani PR nemá. Velikosti worktree skutečných běhů `00607ef9`, `479a5ba0` a `d90502f3` jsou v `measurements.run_worktrees`.
- **Měření:**
  - Čas vytvoření worktree ze 3 vzorků: medián 0,0697 s, maximum 0,1223 s.
  - Worktree má 35 390 B a 37 souborů. `.git` repa má 114 550 B.
  - Worktree skutečných běhů: 40 442 až 60 689 B.
  - Úklid vzorků prošel u všech tří.
- **Pozorování:**
  - Čísla jsou dolní mez.
  - Úklid po merge dělá `approve`. Zavřené a neschválené běhy nechávají worktree, na konci běhu to byly 3.

### R10 — Codex se chová jinak než Claude Code a pi

**Výsledek: CHYBÍ** (validátor: `inconclusive`). Codex se v běhu nespustil a opravné kolo neproběhlo. Hlavní otázku rizika, tedy ztrátu kontextu v opravném kole, výsledky nezodpovídají.

- **Důkaz:** [`R10.json`](../prototype/validation/results/2026-09-27/github-164507/R10.json), run `11efaa43`, PR [#2](https://github.com/janbkrejci/haifa-sandbox/pull/2).
- **Měření:**
  - `repair_rounds = 0` (pozorování: „model prošel testy napoprvé, opravné kolo neproběhlo“).
  - Běh 225,3 s, 530 869 tokenů, $0,1340. Builder spotřeboval 46 680 tokenů.
- **Co výsledky ukazují jinak:**
  - Volba harnessu po krocích funguje pro dvojici claude + pi v jednom workflow. V `agent_sessions` všech 7 běhů mají planner a documenter `claude`, builder a reviewer `pi`.
  - Adaptér Codexu v prototypu existuje. Podle trace vývoje (session `bdd44bbe`) spouští `codex exec --json`, opravná kola posílá přes `codex exec resume` a má kontraktové testy s falešným procesem. Skutečný běh Codexu ve výsledcích **CHYBÍ**. V trace vývoje běžel jen harness `claude_code` / `claude-opus-5-5` (38 agentních sessions).
  - Předpoklad z briefu, že „omezení zápisů funguje nezávisle na harnessu, protože kontroluje git diff“, výsledky **vyvracejí** pro zápisy mimo worktree (zjištění Z1).

## Zjištění mimo scénáře

**Z1 — Agenti na harnessu Claude zapisují do hlavního checkoutu místo worktree.**

Zdroj: trace `gate_results`, `events.jsonl`, R4.json `tree_dirty`.

- Fáze `document`: v runech `01a37500`, `11efaa43`, `479a5ba0` a `d90502f3` první pokus neprošel gate `artifacts_exist` („declared artifact does not exist“), tedy ve 4 ze 7 běhů. Documenter zapsal `app_docs/<adw_id>_….md` do `…/repo/app_docs/` hlavního checkoutu, ne do `…/repo/.factory/worktrees/<run-id>/`.
- Při opakování gate přijala absolutní cestu do hlavního checkoutu v runech `01a37500`, `11efaa43` a `479a5ba0`. Fáze `commit_docs` pak skončila `committed: false`, takže **dokumentace v PR chybí, přestože běh skončil `success`**. Jen `d90502f3` zapsal při opakování do worktree.
- Fáze `plan` v `d90502f3`: planner zkopíroval spec do `…/repo/specs/d90502f3_truncate.md` v hlavním checkoutu. Builder (pi) ji pak ve worktree nenašel (`ENOENT … worktrees/d90502f3/specs/d90502f3_truncate.md`).
- R4 `tree_dirty` potvrzuje necommitnuté soubory v hlavním checkoutu: `app_docs/01a37500_…`, `11efaa43_…`, `479a5ba0_…`, `d90502f3_…` a `specs/d90502f3_truncate.md`.
- Pravděpodobná příčina podle promptů v trace: `context_handoff_dir` je absolutní cesta do hlavního checkoutu (`…/repo/.factory/data/sessions/<run-id>/context_handoff`) a prompt říká „copy into the repo under `specs/`“. Agent na Claude odvodil kořen repa z této cesty. Agenti na pi pracovali ve worktree (cwd worktree). Příčina je odvozená z trace, experimentem ověřená není.

**Z2 — Náklady vývoje prototypu.**

Zdroj: `adws/adw_data/sssf.db`.

- 14 dokončených sessions stálo $48,82 a spotřebovalo 49 830 933 tokenů, vše na `claude_code` / `claude-opus-5-5`.
- Nejdražší bylo zrychlení testů (`e1f8b8ce`): $11,24, 3 pokusy, z toho 2× `build: fail`.
- Review stránka (`e273bee4`) potřebovala také 3 pokusy.
- Souběh SQLite při paralelních bězích (`database is locked`) se objevil ve vývoji a opravil ho přechod na WAL (`f09e5c20`).
- Session `1c2e5607` uvádí, že režim `github` validace nebyl při vývoji spuštěn. Běh `github-164507` je jeho první a jediný výsledek.

## Rozhodnutí D1–D13

| # | Rozhodnutí | Verdikt | Důvod z výsledků |
| --- | --- | --- | --- |
| D1 | Nové repo `~/Documents/HAIFA` | **platí beze změny** | Prototyp i všech 15 sessions vývoje běželo v tomto repu. Nic ve výsledcích proti. |
| D2 | Balíček přes `uv tool install`, v repu jen `.factory/` | **platí beze změny**, ověření **CHYBÍ** | Prototyp engine vendoruje (`vendor/`, session `ce59401f`). Distribuce balíčkem se v F1 neověřovala. |
| D3 | Python backend dashboardu | **platí beze změny**, ověření **CHYBÍ** | Review stránka `haifa-proto serve` je Starlette a volá tytéž funkce jako CLI (`review.approve_task`, `review.return_task`, session `e273bee4`). Ve validačním běhu se nepoužila. |
| D4 | Změny konfigurace uložit a tlačítkem commitnout do `base` | **navržená úprava** | R4: prompt se čte z base, `.factory/sssf.config.yaml` z pracovního stromu, takže necommitnutý `thinking: high` se projevil. Návrh: (a) běh čte veškerou konfiguraci (prompty, agenti, workflow, nastavení enginu) ze stejného commitu base; (b) varování na necommitnutou konfiguraci dává i `task run` v CLI (v `--json` jako pole), nejen dashboard. Varování dnes chybí úplně. |
| D5 | Strom modul → step → task, soubor na task, `depends_on` | **platí beze změny** | Backlog 2 moduly / 3 stepy / 6 tasků se načetl. Vazba zablokovala `M02-S01-T01` (`unmet_dependencies`) a po schválení závislosti běh prošel (R3, run `00607ef9`). |
| D6 | Trvalý stav v hlavičce, `done` jako commit do PR před merge | **navržená úprava (upřesnění)** | R3: schválení přidá do base 1 commit a `done` je v base. Cesta merge mimo HAIFA + `backlog sync` ale přidá 2 commity, tedy sync zapisuje `done` mimo PR. Na base s branch protection to neprojde (neověřeno). Stav `closed` se do trace nezapisuje. Návrh: rozhodnout, zda `backlog sync` zapisuje přímo do base, nebo přes PR; sync má aktualizovat i `task_prs.state` (closed/merged); core před během a po merge dotáhne base z remote (R3 výhrada 3). |
| D7 | YAML s `repeat`, `when`, `accept` | **platí beze změny**, ověření smyček **CHYBÍ** | R1: šťastná cesta odpovídá Python verzi. `repeat` a `when` neproběhly ani jednou (0 opravných kol v 7 bězích). Známý rozdíl: navíc `revise_2` po posledním zamítnutí. Doporučení: v F2 rozhodnout sémantiku `until` (kontrola jen po celém těle, nebo i mezi kroky) a smyčky ověřit scénářem, který opravné kolo vynutí. |
| D8 | `GitProvider`: GitHub, Azure DevOps, lokální | **navržená úprava (rozšíření rozhraní)**, Azure DevOps **CHYBÍ** | R2: GitHub ještě nespočítal mergeability a approve vrátil `merge_failed` místo `conflict`. Návrh: rozhraní vrací stav mergeability včetně „neznámý“ a approve počká nebo zopakuje dotaz. Provider umí `local` a `github` (session `1ecab8c6`). Azure DevOps se neimplementoval ani neověřil. |
| D9 | Nastavitelná merge strategie, výchozí squash | **platí beze změny** | R3: schválení v HAIFA přidalo do base 1 commit. Squash merge mimo HAIFA sync zpracoval správně. |
| D10 | Ruční spouštění + auto-continue | **platí beze změny**, ověření **CHYBÍ** | Auto-continue (`task run --auto`, `queue.py`) je podle session `5eedb417` implementované a testované s falešným harnessem. Validační běh ho nespouštěl. |
| D11 | Schválit = approve review v hostingu + merge | **navržená úprava** | R3: `require_review: false`, protože GitHub nedovolí autorovi schválit vlastní PR. „Dnes self-approval“ tedy na GitHubu approve review odeslat neumí. Návrh: když je schvalovatel autorem PR, HAIFA approve review přeskočí a merguje (branch protection s 0 povinnými approvals, nebo PR otevírá jiný účet či bot). Skutečné approve review jiným uživatelem se ověří v F2. |
| D12 | `factory --skill`, `--json` u všech příkazů | **platí beze změny**, `--skill` **CHYBÍ** | Všech 15 příkazů validace běželo s `--json` a vrátilo strojově čitelné chyby (`unmet_dependencies`, `merge_failed`, `pr_not_open`). `--skill` se nevalidoval. Logy JSON výstupů approve, show a sync jsou prázdné. |
| D13 | Tři adaptéry, harness výslovně u agenta, přepis po krocích | **platí beze změny**, ověření Codexu **CHYBÍ** | claude + pi v jednom workflow fungují (7 běhů, `agent_sessions`). Codex nebyl v rosteru (R1, R10). Z1 ukazuje, že harnessy se liší v práci s cestami. Brief to ale pokrývá rizikem R10, rozhodnutí se měnit nemusí. Doplnit kontraktový test „agent zapisuje jen ve worktree“ pro všechny adaptéry. |

## Rozdíly mezi briefem a prototypem

Jen to, co je doložené ve výsledcích nebo v trace:

1. **Název a příkazy.** CLI je `haifa-proto` (balíček `haifa_proto`), ne `factory`. Příkazy: `task run|show|approve|return`, `backlog check|list|sync`, `workflow check`, `harness check`, `serve`. Chybí `task add|edit|list|link` a `factory --skill` (trace vývoje).
2. **Engine je vendorovaný** (`vendor/`), ne samostatný balíček. Pro F1 se to čekalo.
3. **Konfigurace enginu** je v `.factory/sssf.config.yaml` (R4), ne v `.factory/agents.yaml`. Registr rolí je v `roles.yaml` (session `68b41af8`).
4. **Výstupy se pojmenovávají podle `adw_id`, ne podle úkolu.** Soubory jsou `specs/<adw_id>_<slug>.md` a `app_docs/<adw_id>_<slug>.md` (např. `app_docs/13b81e7c_truncate.md`). Brief chce `<task-id>/…` a `adw_id` jen v trace.
5. **Session runtime je v hlavním checkoutu** (`.factory/data/sessions/<run-id>/`), jak brief říká. Důsledkem jsou ale zápisy agentů mimo worktree (Z1), s nimiž brief nepočítá.
6. **Kontrola `writes` nezachytí zápis mimo worktree** (Z1). Brief v R10 tvrdí, že omezení zápisů je díky git diffu nezávislé na harnessu.
7. **Gate `artifacts_exist` přijme artefakt mimo worktree.** Běh pak skončí `success`, i když dokumentace v PR chybí (Z1, 3 ze 7 běhů).
8. **Schválení neposílá approve review** (`require_review: false`, R3). Brief předpokládá approve review jménem uživatele i u self-approval.
9. **Po merge se neposune lokální base** (R3). Brief to neřeší, validace to dělá sama.
10. **Zavřený PR se v trace nezapíše jako `closed`** (R3, `task_prs` PR 5 = `open`).
11. **`backlog sync` zapisuje `done` přímo do base** (2 commity na cestě merge mimo HAIFA + sync, R3). Brief říká, že kód i stav přijdou v jednom PR, sync tuto cestu výslovně nepopisuje.
12. **Konflikt se hlásí jako `merge_failed`, dokud GitHub nespočítá mergeability** (R2). Workflow `resolve` neexistuje, rebase ani `resolve` se nenabízí.
13. **Varování před spuštěním při necommitnuté konfiguraci chybí** (R4).
14. **Konfigurace se čte ze dvou míst**: prompty z base, `sssf.config.yaml` z pracovního stromu (R4). Brief předpokládá, že běh vychází z commitu v base.
15. **Úklid worktree jen po schválení.** Zavřené a neschválené běhy worktree nechávají, na konci běhu 3 (R5). Brief úklid neschválených běhů neřeší.
16. **YAML `simple-sdlc` spustí po posledním zamítnutí navíc `revise_2`** (R1).
17. **Git provider**: jen `local` a `github`, Azure DevOps chybí (trace vývoje).
18. **Dashboard** je jedna stránka (`serve`) se seznamem otevřených PR a tlačítky Schválit a Vrátit (trace vývoje). Odpovídá rozsahu F1, validací neprošla.

## Doporučení pro F2

**Převzít** (ověřeno výsledky nebo testy v trace vývoje):

- Načtení a validaci backlogu včetně dědění z `index.md` a kontroly `depends_on` (R3 `dependency_blocks`).
- Interpret YAML workflow s registrem rolí a přepisem harness/model/thinking po krocích (R1, 7 běhů claude + pi).
- Běh ve worktree s větví `factory/<task-id>-<n>`, tabulky `task_runs` a `task_prs` a zámek plus WAL pro paralelní běhy (R2, `f09e5c20`).
- Tok `task approve`, `task return`, `backlog sync` a `GitProvider` s jedinou třídou `GhCli` (R3: všechny 4 cesty PR prošly).
- Stabilní chybové kódy v `--json` (`unmet_dependencies`, `merge_failed`, `pr_not_open`, `already_running`).
- Validační scénáře `just proto-validate --remote local|github --roster DIR` jako end-to-end test F2. Umí vrátit `inconclusive` místo falešného `passed`.
- Adaptér Codexu a kontraktové testy harnessů jako výchozí bod. Skutečný běh Codexu se ale ověří až v F2.

**Přepsat:**

- **Model cest běhu (Z1).** `context_handoff_dir` a veškeré cesty v promptech vztáhnout k worktree. Gate `artifacts_exist` má přijímat jen artefakty uvnitř worktree nebo session adresáře. Kontrola `writes` má hlásit i změny v hlavním checkoutu během běhu. Běh, jehož `commit_docs` nic necommitne, nemá skončit `success` bez varování.
- **Čtení konfigurace z base** pro všechny soubory `.factory/` a varování na necommitnutou konfiguraci v CLI i dashboardu (R4, D4).
- **Zápis stavu PR**: `closed` do `task_prs`, dotažení base po merge a způsob zápisu `done` při sync (R3, D6).
- **`GitProvider`**: stav mergeability „neznámý“, odlišení `conflict` od `merge_failed`, provider Azure DevOps (R2, D8).
- **Schválení** podle navržené úpravy D11.
- **Pojmenování výstupů** podle task-id místo `adw_id` (rozdíl 4).
- **Úklid worktree** i pro zavřené a opuštěné běhy (R5).

**Zahodit:**

- Vendorovanou kopii enginu a název `haifa-proto`. Nahradí je balíček `aifactory` a CLI `factory` podle D2.
- Dotahování base uvnitř validačního skriptu (fetch + ff). Má ho dělat core, ne test (R3).

**Ověřit v F2, protože výsledek z F1 chybí:**

- Workflow se třemi harnessy včetně Codexu (R1, R10, D13).
- Opravné kolo test → fix a review → revise se ztrátou nebo zachováním kontextu (R1, R10).
- Náklad worktree na .NET nebo `node_modules` projektu (R5).
- Auto-continue (D10), approve review jiným uživatelem (D11), Azure DevOps (D8), `factory --skill` (D12), dashboard nad Python backendem (D3).
- Srovnání trace YAML běhu se skutečnou trace Python `adw_simple_sdlc.py` nad stejným úkolem (R1).

## Chybějící výsledky (souhrn)

| Co | Proč chybí |
| --- | --- |
| R10 celé, Codex v R1 | roster `pi-haiku` nemá harness `codex` |
| Opravná kola (fix, revise) | ve všech 7 bězích prošel test i review napoprvé |
| Trace Python `adw_simple_sdlc.py` nad sandboxem | scénář R1 ji nespouští, porovnává s popisem fází |
| Worktree .NET / `node_modules` | sandbox je malý Python projekt |
| Approve review v hostingu | GitHub nedovolí schválit vlastní PR, `require_review: false` |
| Azure DevOps | provider neimplementován |
| Auto-continue, dashboard, `--skill`, distribuce balíčkem | nejsou součástí validačních scénářů |
| Výstupy příkazů approve, show a sync | logy `05`, `06`, `08`, `09`, `10`, `13`, `14` mají 0 B |
| Běh s `--remote local` | ve `results/` není, existuje jen `github-164507` |
