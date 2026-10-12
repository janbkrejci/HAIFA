# Rozhodnutí

Platná rozhodnutí, jejichž důvod z kódu nevyčteš. Historie (product brief, zpráva z prototypu, návrhy) je v gitu do commitu `f7492b0`.

## Běh tasku

- **Zápisy mimo worktree:** hlídá je kód, ne prompt. Zápis mimo worktree nebo mimo povolené cesty (`writes`) se vrátí a fáze selže. Necommitnutá práce v hlavním checkoutu se před každým voláním agenta uloží a po něm obnoví.
- **Výstupy tasku:** spec a dokumentace tasku leží pod `docs_root` ve struktuře projekt/step a jmenují se `<task-id>-<slug>.md`. Agent s neprázdným `writes` je smí zapsat i mimo své `writes`, agent s `writes: []` ne.
- **Konfigurace z base:** běh čte sdílenou konfiguraci (`.factory/` kromě `local.yaml`) z commitu v `base`, ne z pracovního stromu. Necommitnutá konfigurace dává varování v CLI i dashboardu.
- **Prázdný commit:** krok commit bez změn běh neshodí.
- **Smyčky:** `until` se vyhodnocuje po každém kroku těla `repeat` a smyčka hned končí. Po posledním zamítnutí review se `revise` nespouští.
- **Testy:** kontroly volí agent tester pro každý běh, krok `test` spustí všechny i po prvním selhání a selhání jde nejdřív k triáži testerem (chyba plánu, nebo kódu). Builder spouští jen testovací soubory své změny.
- **Konflikty PR:** řeší je workflow `resolve` (rebase, a jen při konfliktu agent, který smí měnit jen konfliktní soubory).
- **Auto-continue:** bez `--auto` řetěz pokračuje jen po tasku, který má `auto_continue` zapnuté (vlastní nebo zděděné), a spouští jen tasky, které ho mají zapnuté. `--auto` platí pro celý řetěz.

## Konfigurace a knihovna

- **Dědičnost z knihovny:** agenti, workflow, skilly a rozšíření se hledají nejdřív v `.factory/` repa, potom v knihovně (`$HAIFA_HOME/library`, bez ní seed). Kopie v repu má přednost. Nic se mezi knihovnou a repem nesynchronizuje, „Přesunout do knihovny“ přesune kopii z repa do knihovny. Běh zapíše do trace commit knihovny, ze kterého četl, a skilly z knihovny jen nakopíruje do worktree.
- **Instrukce a skilly repa:** agenti používají CLAUDE.md, AGENTS.md a skilly repa tak, jak je jejich harness načte při spuštění v repu. Osobní a globální konfigurace operátora se do běhu nedostane, kde to harness umí, jinak to hlásí `factory check`. `*_SAFE_MODE=1` vrátí úplnou izolaci.
- **Skilly v repu:** zdroj je `.claude/skills/<jméno>/`. `.agents/skills/<jméno>/` je jeho kopie pro codex a pi, bez symlinků (na Windows bez `core.symlinks` nefungují). Kopii udržuje `factory skills sync` a rozdíl hlásí `factory check`.
- **Harness explicitně:** harness je u agenta vždy zapsaný, nikdy se neodvozuje z názvu modelu.
- **Změny base:** jak factory mění base, je nastavení repa v `config.yaml`, ne volba jednotlivého příkazu. `base_changes: direct` commituje a pushuje do base. `base_changes: pr` posílá každou změnu (instalace, konfigurace, položky knihovny, backlog, odebrání) jako pull request a platí to i pro instalaci, která nastavení zapisuje. `base_pr_merge: auto` vlastní PR factory hned mergne a posune lokální base. Na GitHubu, kde autor nemůže schválit vlastní PR, merguje přes `--admin`, na Azure DevOps ho autor sám schválí. Když merge selže, PR zůstane otevřený s varováním. Stažení base snese necommitnuté změny, které stahovaný commit přináší beze změny (backlog čekající na PR).

## Dashboard a distribuce

- **Více repozitářů:** jeden `factory obs` obsluhuje repozitáře z registru `dashboard.yaml` v domově HAIFA. Port je jen v registru. `.factory/`, backlog a trace DB zůstávají v repu.
- **Limity harnessů:** dashboard ukazuje poslední hodnoty, které harness sám vrátil při běhu (Claude ve stream-json, Codex v session logu). Žádné vlastní dotazy na API ani app-server.
- **Distribuce:** GitHub Actions po zeleném CI na `main` vydá release `haifa-<verze>.zip` s verzí `<major>.<minor>.<číslo běhu>`. Commit, který mění jen backlog (`factory/backlog/`) nebo `.factory/`, CI ani release nespouští.
- **HAIFA staví HAIFA:** vývoj běží přes `factory` nad tímto repem, backlog projektu `HAIFA` je ve `factory/backlog/`.
