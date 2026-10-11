# Dashboard

Dashboard spustíš příkazem `factory obs` a běží na `http://127.0.0.1:4700`. Jeden dashboard obsluhuje všechna repa zaregistrovaná na tomto počítači (registr `dashboard.yaml` v domovském adresáři HAIFA). Port změníš na stránce Tento počítač nebo přepínačem `--port`.

## Horní lišta

Zleva doprava:

- **Logo HAIFA:** návrat na úvodní stránku.
- **Chip aktualizací:** „Systém je aktuální“, nebo „Je k dispozici aktualizace“ (kliknutím ji nainstaluješ). Viz [Aktualizace a vydání](#/guide/aktualizace).
- **Chip kontroly:** „Systém v pořádku“ (kliknutím zopakuješ kontrolu), nebo **Nalezeny problémy**, který otevře stránku **Problémy a řešení**.
- **Chip knihovny:** „Knihovna OK“, nebo „Založit knihovnu“.
- **Harnessy:** lišta limitů předplatného (pětihodinové a týdenní okno, kolik procent zbývá). Kliknutím otevřeš nastavení harnessů tohoto počítače.
- **Příručka:** ikona knihy otevře tuto příručku.
- **Motiv:** přepínač světlého a tmavého motivu.
- **Přepínač rep:** název otevřeného repa a verze HAIFA. Menu nabízí **Přehled**, **Tento počítač**, **Knihovna**, seznam rep (se stavem a počty běžících, čekajících na review a selhaných tasků) a **Přidat repozitář…**.

Limity ukazují poslední hodnoty, které harness sám vrátil při běhu (Claude ve výstupu běhu, Codex ve svém logu). Dashboard se na ně nikam neptá; pi limity nehlásí.

## Pruhy upozornění

- **Kód HAIFA se od spuštění dashboardu změnil:** po aktualizaci nebo změně balíčku jsou zápisy vypnuté, dokud neklikneš na **Restartovat dashboard**.
- **Konfigurace v `.factory/` má necommitnuté změny:** běhy používají konfiguraci z base, dokud změny necommitneš tlačítkem **Commitnout konfiguraci**.
- **Backlog má necommitnuté změny:** plovoucí pruh dole na stránce repa se seznamem souborů a tlačítkem **Commitnout backlog**.

## Přehled

Úvodní stránka se všemi repy. Souhrnná tlačítka **Běží**, **Čeká na review**, **Selhalo** a **Problémy** filtrují karty rep. Karta repa ukazuje běžící tasky (workflow, fáze, pokus, čas, náklady), pull requesty čekající na review, selhané běhy, stav konfigurace a poslední aktivitu. Repa bez aktivity jsou souhrnně „v klidu“.

**Odebrat repozitář** není jen odregistrování: z repa smaže `.factory/` a řádky HAIFA v `.gitignore`, commitne to do base a odešle, a smaže lokální data běhů (trace DB, worktree). Backlog, specifikace a dokumentace v repu zůstanou. Repo, jehož složka zmizela, jen odebereš z dashboardu tlačítkem **Odebrat z dashboardu**.

## Tento počítač

Kontrola počítače rozdělená do skupin HAIFA, Nástroje, Harnessy, Hosting, Knihovna a Prostředí; každé zjištění má radu s tlačítkem **Kopírovat**. Dále kontrolní seznam **Začínáme** (kapitola [První spuštění](#/guide/prvni-spusteni)), sekce knihovny (stav, remote, **Stáhnout**, **Odeslat**, nebo založení a naklonování) a nastavení dashboardu: **Port** (platí po restartu) a cesty k registru a domovskému adresáři.

## Problémy a řešení

Souhrn všeho, co brání práci, na jednom místě: problémy počítače, harnessů, knihovny a jednotlivých rep. Každý problém má akci, například **Opravit na tomto počítači**, **Nastavit a testovat harnessy**, **Commitnout konfiguraci** nebo **Nainstalovat factory**. **Zkontrolovat znovu** kontrolu zopakuje.

## Knihovna

Položky sdílené knihovny (agenti, workflow, skilly, rozšíření pi), jejich verze a repa s vlastní kopií. Viz kapitola [Knihovna](#/guide/knihovna).

## Obrazovky repa

Po otevření repa jsou nahoře záložky:

- **Backlog:** projekty, stepy a tasky ve stromu nebo kanbanu, detail tasku, spouštění běhů. Kapitola [Backlog a tasky](#/guide/backlog).
- **Běhy:** běžící a dokončené běhy, řetězy auto-continue, náklady a detail běhu s fázemi. Kapitola [Běhy](#/guide/behy).
- **Review:** pull requesty ke schválení. Kapitola [Review a merge](#/guide/review).
- **Factory:** stav instalace HAIFA v repu, nálezy kontroly, roster agentů a položky repa. Kapitola [Konfigurace repa](#/guide/konfigurace-repa).
- **Nastavení:** sdílené nastavení repa (`config.yaml`) a lokální nastavení (`local.yaml`). Kapitola [Konfigurace repa](#/guide/konfigurace-repa).

Adresa v prohlížeči vždy odpovídá obrazovce (například `#/r/<repo>/runs/<běh>`), takže odkazy na task, běh nebo pull request můžeš sdílet nebo si je uložit.

## Přístup ze sítě

Dashboard naslouchá jen na `127.0.0.1`. `factory obs --host 0.0.0.0` (nebo proměnná `HAIFA_DASH_HOST`) ho zpřístupní celé síti, a to **bez přihlášení**: kdokoli v síti pak může spouštět běhy. Používej to jen v důvěryhodné síti.
