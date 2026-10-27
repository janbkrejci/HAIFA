# Aktualizace a řešení problémů

## Aktualizace

Dashboard kontroluje vydání každou půlhodinu. Ikona s tooltipem **Je k dispozici aktualizace** stáhne, ověří, nainstaluje aktualizaci a restartuje dashboard. Tooltip **Aktualizace čeká na tasky**: po doběhnutí klikni znovu.

Z příkazové řádky (soubor nebo `https` URL):

```bash
factory upgrade --dry-run haifa-<verze>.zip
factory upgrade haifa-<verze>.zip
```

`factory upgrade` ověří `SHA256SUMS`, instaluje pouze novější verzi a obnoví knihovnu (`factory library seed --all`, [Knihovna a tým](#/guide/knihovna-a-tym/seminko)). Dashboard restartuj; na Windows ho předem zastav (`dashboard_running`).

Vydání: GitHub Actions po commitu do `main`, ručně `just bundle`.

## Řešení problémů

Problémy hledá `factory check` (jen čte):

```bash
factory check            # počítač a knihovna, v repu i repo
factory check --offline  # bez dotazů na hosting a přihlášení
factory check --json     # strojově čitelný výstup
```

Nález obsahuje kód, závažnost a radu `fix`: `error` blokuje, `warning` vyžaduje pozornost, `info` informuje. Nálezy: **Knihovna** (počítač, knihovna), **Factory** (repo), **Problémy a řešení**.

## Časté situace

**Změna `.factory/` nebo backlogu se v běhu neprojevila.** Běhy čtou base. Commitni ji ikonou s tooltipem **Necommitnutá konfigurace** nebo **Necommitnutý backlog** (`factory config commit`, `factory backlog commit`).

**Task nejde spustit.** Nemá workflow (nastav ho v tasku, stepu nebo projektu), čeká na závislost, nebo je pro člověka.

**Harness chybí nebo není přihlášený.** Nainstaluj, přihlas (`claude`, `codex login`, `pi auth login`), spusť **Test** v **Harnessy tohoto počítače**, nebo přepni roster (`factory config roster set`).

**Běh selhal nebo se zasekl.** Prohlédni kartu selhání a události fáze. Zastav běh, pak **Pokračovat** (`factory task retry ID`).

**PR zůstal po schválení otevřený.** Detail PR: CI (`checks_failing`, `checks_pending`, `ci_fix_failed`), konflikt či závislost. Oprav, schval znovu.

**Knihovna je pozadu nebo se rozešla s remote.** `factory library pull`; při `library_diverged` vyřeš rozdíl přímo v adresáři knihovny.

K hlášení přilož `factory check --json` a `factory --version`.
