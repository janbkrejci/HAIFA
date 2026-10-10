# Rozhodnutí po schválení briefu

Brief ([product-brief.md](product-brief.md)) obsahuje rozhodnutí D1 až D13. Tady jsou rozhodnutí přijatá později, při branách a během vývoje. Když se rozhodnutí a brief rozcházejí, platí rozhodnutí. Brief mění jen engineer.

## Brány

| Brána | Datum | Podklad |
|---|---|---|
| G1 prototyp | 2026-09-27 | [prototype-report.md](prototype-report.md). Pokračuje se do F2, R10 (Codex) a Codex v R1 se ověří, až bude kredit na codex. |
| F2 core a CLI | 2026-09-29 | `aifactory/validation/results/2026-09-29/github-075535`: F2 a R2–R5 `passed`, R1 a R10 `inconclusive` (chybí codex). |
| F3 dashboard | 2026-09-30 | Ruční průchod dashboardem na sandboxu: založení, vazba, spuštění, sledování, schválení a merge bez terminálu. PR #38 a #39 v `janbkrejci/haifa-sandbox`, příprava `aifactory/validation/results/2026-09-30/github-071816`. |

## Rozhodnutí

- **Zápisy mimo worktree (Z1):** hlídá je kód. Zápis mimo worktree a mimo povolené cesty se vrátí a fáze selže. Necommitnutá práce v hlavním checkoutu se před každým voláním agenta uloží a po něm obnoví.
- **Prázdný commit (B1):** krok commit bez změn běh neshodí.
- **Opravná kola:** validace je vynucuje, aby smyčky `repeat` a `when` proběhly.
- **Konfigurace běhu (D4):** běh čte veškerou konfiguraci z commitu v `base`. Necommitnutá konfigurace dává varování v CLI i dashboardu.
- **Smyčky (D7):** `until` se vyhodnocuje po každém kroku těla `repeat` a smyčka končí hned. Po posledním zamítnutí review se `revise` nespouští.
- **`backlog sync` (D6):** `done` se zapisuje přes PR, ne přímo do `base`.
- **Konflikty PR (D8):** workflow `resolve` je povinný. Azure DevOps se bude používat, provider je zatím ověřený jen proti falešnému `az`.
- **Schválení vlastního PR (D11):** zatím se approve review v hostingu neposílá a PR se rovnou merguje. Approve review jménem uživatele nebo přes bota se dodělá později.
- **Pojmenování výstupů:** specs a app_docs se jmenují podle tasku (`<task-id>-<slug>.md`), ne podle `adw_id`.
- **Vlastník modulu (2026-10-01):** institut vlastníka se ruší. Pole `owner` v `index.md` se ignoruje a dashboard podle něj nefiltruje. Brief ho ještě zmiňuje v sekci Cíl a rozsah, v tabulce Dashboard a v D11.
- **Úrovně backlogu (2026-10-01):** úroveň module se přejmenuje na project, step a task zůstávají. Název phase by kolidoval s fázemi běhu. Kódy úrovní jsou libovolné a krátké (např. `M01`), každá úroveň má navíc krátký název a všude, kde se ukazuje kód, je název v tooltipu.
- **Výchozí sbalení (2026-10-02):** sbalené začíná vše, co se čte: sekce Review, soubory diffu, sekce panelu fáze a strom backlogu (projekty zůstávají vidět). Akce v Review (Schválit, varování o konfliktu) jsou vždy vidět. Strom si v prohlížeči pamatuje rozbalení a filtr stavu rozbalí větve se shodou.
- **Výstupy po projektech (2026-10-02):** projekt smí mít vlastní adresáře pro spec a dokumentaci. Agent smí zapsat dva výstupní soubory svého tasku i mimo své `writes`, pokud jeho `writes` není prázdné. Ostatní zápisy mimo `writes` se dál vracejí.
- **Instalace do repa (2026-10-02):** factory se do stávajícího repa instaluje příkazem `factory init`. `factory --skill` popisuje postup kolem něj a dashboard pro více repozitářů ho používá při přidání repa.
- **HAIFA staví HAIFA (2026-10-01):** další vývoj běží přes `factory` nad repem HAIFA. Backlog je `backlog/` (projekt `HAIFA`), všichni agenti běží na claude opus, PR schvaluje orchestrátor po kontrole (review schválilo, `just check` prošel, diff odpovídá zadání). Vývoj přes sssf je archivovaný v `docs/sssf/`, sssf factory v `adws/` zůstává jako záloha.
- **Dashboard pro více repozitářů (2026-10-02):** jeden `factory obs` obsluhuje repozitáře z registru v domově (`~/.config/haifa/dashboard.yaml`, `HAIFA_HOME`). Port dashboardu je jen v registru, `.factory/local.yaml` port nemá. `.factory/`, backlog a trace DB zůstávají v repu. Návrh: `docs/design/multi-repo-dashboard.md` (D14–D28).
- **Přijatá doporučení návrhu (2026-10-02):** D15 běhy z dashboardu jako samostatné procesy `factory task`, D16 kontrola sama a aktualizace až po potvrzeném náhledu, D17 doručení do base a PR při odmítnutém pushi nebo na přání, D18 commit bez checkoutu, D19 dočasná registrace v průvodci, D20 samostatný `factory update`, D21 napsaná cesta, prohlížeč pod domovem a nativní dialog, D23 obnova přehledu po 2 s, D25 procházení jen pod domovem, D27 token zatím ne, D28 frontendové úkoly po jednom po T15.
- **Konfigurace jako hybrid (2026-10-02):** centrální knihovna v domově (agenti s prompty a výchozím harnessem a modelem, workflow, skilly, ideálně git repo pro tým) a v každém repu commitnutá kopie toho, co používá, s původem (položka a verze). Factory kopie spravuje: import, export, přehled použití a zastaralých verzí, hromadná aktualizace s náhledem. Běh čte commitnutou kopii z base (D4). Roster je vlastní pro každé repo.
- **Skilly (2026-10-02):** spravuje je HAIFA jako další typ položky knihovny, bez skills-manager-cli. Agenti factory musí umět používat skilly, které mají přiřazené.
- **Onboarding repa (2026-10-02):** při prvním přidání repa, které už má vlastní konfiguraci factory (sssf `adws/` nebo `.factory/` z doby před knihovnou), HAIFA tuto konfiguraci jednou vytěží do knihovny a do commitnuté `.factory/` repa a zapíše do repa, že onboarding proběhl. Na strojích kolegů se nic znovu nevytěžuje: jejich HAIFA repo pozná jako onboardované a převezme commitnutou konfiguraci a sdílenou knihovnu.
- **Distribuce týmu (2026-10-02):** kolega si HAIFA snadno stáhne a zprovozní (instalace nástroje `factory`, kontrola prerekvizit a přihlášení, sdílená knihovna, aktualizace HAIFA) a onboarduje svoje repa z dashboardu nebo CLI.
- **Knihovna, onboarding a distribuce (2026-10-02):** návrh `docs/design/library-onboarding-distribution.md`. Přijaté: D26 migrace konfigurace ve `factory update` s diffem a jen na `--migrate ID` (první: `levels` module → project), D29 skilly ve v1 rejstříkem v system promptu, claude dál `--safe-mode`, pi izolované, nativní načítání až po ověření CLI, D30 upravené agenti a workflow se při vytěžení uloží jako nové položky knihovny (`--keep-local` je nechá jen v repu), D32 repo s manifestem bere workflow jen z commitnuté `.factory/workflows/` (kromě interního `resolve`).
- **Distribuce z veřejného repa (2026-10-02):** nahrazeno rozhodnutím Distribuce bundlem (2026-10-03).
- **Instrukce a skilly repa (2026-10-03):** harnessy načítají CLAUDE.md, AGENTS.md a skilly repa nativně, každý svým mechanismem. Osobní a globální konfigurace operátora se do běhu nedostane, kde to harness umí, jinak to hlásí `factory check`. `*_SAFE_MODE=1` vrátí úplnou izolaci. Nahrazuje izolaci z D29 (úkol HAIFA-S05-T05).
- **Instrukce a skilly repa, zjednodušeno (2026-10-04):** agenti používají CLAUDE.md, AGENTS.md a skilly repa tak, jak je jejich harness načte při spuštění z CLI v repu. Osobní a globální konfigurace operátora se do běhu nedostane, kde to harness umí, jinak to hlásí `factory check`. Skilly se jednotlivým agentům v `.factory/` nepřiřazují (žádné `skills:`, `.factory/skills/` ani rejstřík skillů v promptu). Nahrazuje rozhodnutí Instrukce a skilly repa (2026-10-03) a v části o přiřazených skillech rozhodnutí Skilly (2026-10-02) (úkol HAIFA-S05-T05).
- **Skilly v repu (2026-10-04):** skill repa má zdroj v `.claude/skills/<jméno>/`, tam ho instaluje knihovna a tam se edituje. `.agents/skills/<jméno>/` je jeho kopie pro codex a pi na všech systémech, bez symlinků (ty na Windows bez `core.symlinks` nefungují). Kopii zapisuje factory při instalaci a aktualizaci skillu a `factory skills sync`, `factory check` hlásí rozdíl a chybějící kopii.
- **Testovací příkaz podle technologie (2026-10-03):** `factory init` a onboarding navrhnou `test_command` podle souborů repa (just, pytest, npm, dotnet, cargo, go, make), engineer ho potvrdí nebo přebije.
- **Samostatné kořeny backlogu (2026-10-03):** projekty v jednom repu můžou mít backlog v samostatných kořenech (`backlog_dirs`), id musí být jedinečná napříč kořeny. Specs a dokumentace po projektech řeší `specs_dir` a `docs_dir` v `index.md`.
- **Auto-continue po větvích (2026-10-04):** bez `--auto` rozhoduje `auto_continue` obou tasků. Řetěz pokračuje jen po tasku, který ho má zapnuté (vlastní nebo zděděné ze stepu či projektu), a spouští jen tasky, které ho mají zapnuté. Zapnutá větev tak nepřeteče do vypnuté a vypnutá se sama nespustí. `--auto` platí pro celý řetěz a pro všechny tasky.
## Otevřené body

Otevřené body OB1 až OB7 z fáze 02 jsou tasky v kroku `HAIFA-S90` backlogu.
