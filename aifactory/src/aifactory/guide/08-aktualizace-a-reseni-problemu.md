# Aktualizace a řešení problémů

## Aktualizace

Dashboard jednou za půl hodiny zjistí poslední vydání. Klik na **Je k dispozici aktualizace** balíček stáhne, ověří, nainstaluje a dashboard restartuje. Dokud běží task, chip ukazuje **Aktualizace čeká na tasky**; až doběhnou, klikni znovu.

Z příkazové řádky (soubor nebo `https` URL):

```bash
factory upgrade --dry-run haifa-<verze>.zip
factory upgrade haifa-<verze>.zip
```

`factory upgrade` ověří `SHA256SUMS`, starší ani stejnou verzi neinstaluje a pak obnoví knihovnu (`factory library seed --all`, viz [Knihovna a tým](#/guide/knihovna-a-tym/seminko)). Běžící dashboard restartuj. Na Windows `factory upgrade` při běžícím dashboardu odmítne (`dashboard_running`).

Vydání vzniká v GitHub Actions z každého commitu do `main`; ručně ho vytvoří `just bundle`.

## Řešení problémů

Problémy hledá `factory check` (jen čte):

```bash
factory check            # počítač a knihovna, v repu i repo
factory check --offline  # bez dotazů na hosting a přihlášení
factory check --json     # strojově čitelný výstup
```

Každý nález má kód, závažnost a radu `fix`, co udělat. `error` blokuje práci, `warning` je pravděpodobně potřeba opravit, `info` jen informuje. V dashboardu jsou na stránce **Knihovna** (počítač, knihovna), na záložce **Factory** (repo) a na stránce **Problémy a řešení**.

## Časté situace

**Změna `.factory/` nebo backlogu se v běhu neprojevila.** Běhy čtou base. Commitni ji chipem **Necommitnutá konfigurace** nebo **Necommitnutý backlog** (`factory config commit`, `factory backlog commit`).

**Task nejde spustit.** Nemá workflow (nastav ho v tasku, stepu nebo projektu), čeká na závislost, nebo je pro člověka.

**Harness chybí nebo není přihlášený.** Nainstaluj a přihlas ho (`claude`, `codex login`, `pi auth login`), pak v dialogu **Harnessy tohoto počítače** spusť **Test**. Nebo přepni agenty repa na jiný harness (`factory config roster set`).

**Běh selhal nebo se zasekl.** V detailu běhu sleduj události fáze; běh můžeš zastavit a pak **Navázat** (`factory task retry ID`).

**PR zůstal po schválení otevřený.** Detail PR ukáže důvod: červená nebo nedoběhnutá CI (`checks_failing`, `checks_pending`, `ci_fix_failed`), konflikt, nebo nesplněná závislost. Oprav a schval znovu.

**Knihovna je pozadu nebo se rozešla s remote.** `factory library pull`; při `library_diverged` vyřeš rozdíl přímo v adresáři knihovny.

Když nic nepomůže, přilož k hlášení výstup `factory check --json` a `factory --version`.
