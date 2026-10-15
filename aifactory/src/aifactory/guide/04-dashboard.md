# Dashboard

Dashboard spustíš příkazem `factory obs` a běží na `http://127.0.0.1:4700`. Jeden dashboard obsluhuje všechna repa zaregistrovaná na tomto počítači (registr `dashboard.yaml` v domovském adresáři HAIFA). Port změníš na stránce Tento počítač nebo přepínačem `--port`.

## Horní lišta

Zleva doprava:

- **Logo HAIFA:** návrat na úvodní stránku.
- **Chip aktualizací:** „Systém je aktuální“, nebo „Je k dispozici aktualizace“ (kliknutím ji nainstaluješ). Viz [Aktualizace a vydání](#/guide/aktualizace).
- **Chip kontroly:** „Systém v pořádku“ (kliknutím zopakuješ kontrolu), nebo **Nalezeny problémy**, který otevře stránku **Problémy a řešení**.
- **Chip knihovny:** „Knihovna OK“, nebo „Založit knihovnu“. Oba vedou do sekce **Knihovna** na stránce **Tento počítač** (`#/setup/library`).
- **Harnessy:** lišta limitů předplatného (pětihodinové a týdenní okno, kolik procent zbývá). Kliknutím otevřeš nastavení harnessů tohoto počítače.
- **Příručka:** ikona knihy otevře tuto příručku.
- **Motiv:** přepínač světlého a tmavého motivu.
- **Přepínač rep:** název otevřeného repa a verze HAIFA. Menu nabízí **Přehled**, **Tento počítač** a seznam rep (se stavem a počty běžících, čekajících na review a selhaných tasků).

Limity ukazují poslední hodnoty, které harness sám vrátil při běhu (Claude ve výstupu běhu, Codex ve svém logu). Dashboard se na ně nikam neptá; pi limity nehlásí.

## Pruhy upozornění

- **Kód HAIFA se od spuštění dashboardu změnil:** po aktualizaci nebo změně balíčku jsou zápisy vypnuté, dokud neklikneš na **Restartovat dashboard**.
- **Konfigurace v `.factory/` má necommitnuté změny:** běhy používají konfiguraci z base, dokud změny necommitneš tlačítkem **Commitnout konfiguraci**.
- **Backlog má necommitnuté změny:** červený čip **Necommitnutý backlog** v horní liště stránky repa. Kliknutím otevřeš seznam souborů a tlačítko **Commitnout backlog**.

## Přehled

Úvodní stránka se všemi repy. Souhrnná tlačítka **Běží**, **Čeká na review**, **Selhalo** a **Problémy** filtrují karty rep. Karta repa ukazuje běžící tasky (workflow, fáze, pokus, čas, náklady), pull requesty čekající na review, selhané běhy, stav konfigurace a poslední aktivitu. Repa bez aktivity jsou souhrnně „v klidu“. Pod seznamem rep je odkaz **Přidat repozitář**.

**Odebrat repozitář** je v menu ⋮ vpravo nahoře na kartě repa (nebo na konci řádku repa v klidu). Repo jen odpojí od dashboardu; `.factory/`, backlog, specifikace i dokumentace v repu zůstanou. Repo, jehož složka zmizela, jen odebereš z dashboardu tlačítkem **Odebrat z dashboardu**.

## Tento počítač

Vše o tomto počítači na jedné stránce:

- **Kontrola počítače:** verdikt a nálezy ve skupinách HAIFA, Nástroje, Harnessy, Hosting a Prostředí. Ukazuje jen nálezy, které vyžadují akci; každý má radu s tlačítkem **Kopírovat**. Skupina bez nálezů se nezobrazuje. **Znovu zkontrolovat** kontrolu zopakuje.
- **Knihovna** (`#/setup/library`): nálezy knihovny, založení nebo naklonování knihovny, synchronizace s remote (**Stáhnout**, **Odeslat jako PR**, otevřené pull requesty), **Obnovit výchozí agenty a workflows**, **Import…** a prohlížeč položek. Viz kapitola [Knihovna](#/guide/knihovna).
- **Dashboard:** **Port** (platí po restartu) a cesty k registru a domovskému adresáři.

Dřívější adresa stránky Knihovna (`#/library`) vede do sekce Knihovna.

## Problémy a řešení

Souhrn všeho, co brání práci, na jednom místě: problémy počítače, harnessů, knihovny a jednotlivých rep. Každý problém má akci, například **Opravit na tomto počítači**, **Nastavit a testovat harnessy**, **Commitnout konfiguraci** nebo **Nainstalovat factory**. **Zkontrolovat znovu** kontrolu zopakuje.

## Obrazovky repa

Po otevření repa jsou nahoře záložky:

- **Backlog:** projekty, stepy a tasky ve stromu nebo kanbanu, detail tasku, spouštění běhů. Kapitola [Backlog a tasky](#/guide/backlog).
- **Běhy:** běžící a dokončené běhy, řetězy auto-continue, náklady a detail běhu s fázemi. Kapitola [Běhy](#/guide/behy).
- **Review:** pull requesty ke schválení. Kapitola [Review a merge](#/guide/review).
- **Factory:** vše o factory repa: stav instalace, nálezy kontroly, roster agentů, **Nastavení repozitáře** (sdílené `config.yaml` a lokální `local.yaml`) a položky repa. Kapitola [Konfigurace repa](#/guide/konfigurace-repa). Dřívější záložka Nastavení (`#/r/<repo>/settings`) vede na sekci Nastavení repozitáře (`#/r/<repo>/factory/settings`).

Adresa v prohlížeči vždy odpovídá obrazovce (například `#/r/<repo>/runs/<běh>`), takže odkazy na task, běh nebo pull request můžeš sdílet nebo si je uložit.

## Přístup ze sítě

Dashboard naslouchá jen na `127.0.0.1`. `factory obs --host 0.0.0.0` (nebo proměnná `HAIFA_DASH_HOST`) ho zpřístupní celé síti, a to **bez přihlášení**: kdokoli v síti pak může spouštět běhy. Používej to jen v důvěryhodné síti.
