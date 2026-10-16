# Práce v týmu

HAIFA běží na počítači každého člena týmu. Sdílí se jen to, co je v gitu: konfigurace a backlog v repech a knihovna agentů a workflow ve vlastním Git repu. Nastavení počítače, registr rep dashboardu, trace databáze běhů a přístupové klíče zůstávají lokální.

## Nový člen týmu

1. Nainstaluj HAIFA podle kapitoly [Instalace](#/guide/instalace) a přihlas se do harnessů a hostingu.
2. Instalátor už naklonoval výchozí knihovnu HAIFA-LIBRARY. Používá-li tým jinou, naklonuj ji: `factory library clone <URL-týmové-knihovny>` (stávající lokální knihovnu nejdřív smaž), nebo nastav `HAIFA_LIBRARY_URL` před instalací.
3. Naklonuj repa, na kterých tým pracuje, a v každém spusť `factory check`. Stav repa je `installed`; vyřeš zjištění počítače (harnessy, přihlášení, CLI hostingu). `factory init` znovu nespouštěj.
4. Spusť `factory obs` a repa přidej na přehledu dashboardu (nebo `factory obs --repo ~/cesta/k/repu`).

V dashboardu lze knihovnu naklonovat i na stránce **Knihovna**.

## První v týmu: založení knihovny

Knihovnu založíš ze semínka, které je součástí HAIFA. S `--remote URL` ji rovnou nahraješ do prázdného Git repa, odkud si ji ostatní naklonují:

```bash
factory library init --name "Knihovna týmu" --remote <URL-prázdného-repa>
```

Podrobnosti o položkách a jejich verzích jsou v kapitole [Knihovna](#/guide/knihovna).

## Změny knihovny

Do knihovny přispívá každý, ale jen pull requestem do `main` knihovny. Import, `factory library seed`, **Přesunout do knihovny** i `factory library push` změnu commitnou lokálně a pošlou PR: kdo do repa knihovny nemá zápis, ze svého forku, správce z větve v repu. Na svém počítači změnu používáš hned; ostatní ji dostanou, až ji správce mergne a oni si knihovnu stáhnou (`factory library pull`). HAIFA PR knihovny nikdy nemerguje ani neschvaluje sama.

Správce knihovny nastaví na `main` ruleset s povinným pull requestem a svým schválením a zakáže přímý push i force push (kapitola [Knihovna](#/guide/knihovna)). Otevřené PR, které jsi poslal, ukáže stránka **Knihovna** v dashboardu.

## Přidání repa, které HAIFA ještě nepoužívá

V kořeni repa zkontroluj stav a prohlédni si plán instalace. Náhled ukáže soubory, které vzniknou (`.factory/config.yaml`, adresář backlogu, řádky `.gitignore`), a otisk (digest); commit potvrdí přesně tento plán:

```bash
cd ~/cesta/k/repu
factory check
factory init --dry-run
factory init --commit --expect <digest>
```

`factory init --commit` udělá jeden commit do base a odešle ho. Když remote přímý push do base odmítne (chráněná větev), použij `factory init --commit --pr --expect <digest>`: konfigurace pak přijde pull requestem. Agenty a workflow `factory init` nekopíruje, repo je dědí z knihovny.

Totéž udělá dashboard: na přehledu **Přidat repozitář**, vyber složku repa a potvrď instalaci. Pro chráněnou base zaškrtni **Změny base přes pull request** (kapitola [Konfigurace repa](#/guide/konfigurace-repa)).

## Sdílené a lokální nastavení agentů

Harnessy a modely agentů repa jsou v `.factory/agents.yaml`, který je v gitu a platí pro celý tým. Celý roster přepneš předvolbou:

```bash
factory config roster set claude --dry-run
factory config roster set codex
factory config commit
```

Jednotlivému agentovi nastavíš harness, model a přemýšlení i v dashboardu: záložka **Factory**, sekce **Nastavení agentů**, tlačítka **Upravit** a **Vrátit na zděděné**.

Změna je nejdřív jen v pracovním stromu. Běhy ji uvidí až po `factory config commit`, který ji commitne do base a odešle. Kdo nemá daný harness, uvidí v `factory check` chybu `harness_missing`.

Které harnessy a modely smí dashboard na tvém počítači používat, nastavíš lokálně v dialogu harnessů (kapitola [Počítač a harnessy](#/guide/pocitac)).

## Souběžná práce

- Backlog je v gitu. Úpravy z dashboardu i CLI se commitují do base; kolegové je dostanou přes `git pull` (nebo stažením base v dashboardu).
- Dva lidé by neměli spouštět stejný task současně. Běh a jeho stav zná jen počítač, na kterém běží (trace DB je lokální); otevřený pull request ale vidí všichni a task s ním je na Backlogu ve stavu **Čeká na review** (se zapnutým auto-merge **Čeká na automerge PR**). Sdílený přehled běhů dává volitelný sdílený databázový server (kapitola [Počítač a harnessy](#/guide/pocitac/sdilena-databaze)).
- Pull requesty jsou na společném hostingu; schválit a mergnout je může kdokoli s právy k repu.

## Agent jako člen týmu

HAIFA může ovládat i agent (Claude Code, Codex, pi). Návod v angličtině mu dá `factory --skill`; výstup ulož jako jeho `SKILL.md` a po každé aktualizaci HAIFA ho vygeneruj znovu. Všechny příkazy s `--json` vracejí jednotnou obálku s kódy chyb, kterou agent umí zpracovat.
