# Aktualizace a řešení problémů

## Aktualizace

Dashboard kontroluje vydání každou půlhodinu. Ikona **Je k dispozici aktualizace** ověří, nainstaluje aktualizaci a restartuje dashboard. **Aktualizace čeká na tasky**: po doběhnutí klikni znovu.

CLI (soubor/`https`):

```bash
factory upgrade --dry-run haifa-<verze>.zip
factory upgrade haifa-<verze>.zip
```

`factory upgrade` ověří `SHA256SUMS`, nainstaluje novější verzi, obnoví knihovnu (`factory library seed --all`, [Knihovna a tým](#/guide/knihovna-a-tym/seminko)). Dashboard restartuj; na Windows předem zastav (`dashboard_running`).

Vydání: GitHub Actions / `just bundle`.

## Řešení problémů

Modrý čip **System info**: volné místo disku stroje s factory a paměť v GB, bez cest; nezjištěné hodnoty „nedostupné“. Obnova každou minutu, bez oranžového varování. Potvrzením **Uklidit disk** odstraníš osiřelé návrhy, hotové worktrees a větve sloučených PR všech rep. Tooltip zobrazí výsledek či chybu; obnoví hodnoty.

Problémy hledá `factory check` (jen čte):

```bash
factory check            # počítač a knihovna, v repu i repo
factory check --offline  # bez dotazů na hosting a přihlášení
factory check --json     # strojově čitelný výstup
```

Nálezy: `error` blokuje, `warning` varuje, `info` informuje; `fix` radí. Najdeš je v **Knihovna** (počítač, knihovna), **Factory** (repo), **Problémy a řešení**.

## Časté situace

**Změna `.factory/` nebo backlogu se v běhu neprojevila.** Běhy čtou base. Commitni: **Necommitnutá konfigurace**, **Necommitnutý backlog** (`factory config commit`, `factory backlog commit`).

**Task nejde spustit.** Nastav workflow; ověř závislosti a určení pro člověka.

**Harness chybí nebo není přihlášený.** Přihlas (`claude`, `codex login`, `pi auth login`), spusť **Test** v **Harnessy tohoto počítače**, případně `factory config roster set`.

**Běh selhal nebo se zasekl.** Prohlédni události. Zastav běh, pak **Pokračovat** (`factory task retry ID`).

**PR zůstal po schválení otevřený.** Oprav CI, konflikt či závislost v detailu PR; schval znovu.

**Knihovna je pozadu nebo se rozešla s remote.** `factory library pull`; `library_diverged` vyřeš v knihovně.

K hlášení: `factory check --json`, `factory --version`.
