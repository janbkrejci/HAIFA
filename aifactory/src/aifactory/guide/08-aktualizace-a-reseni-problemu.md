# Aktualizace a řešení problémů

## Aktualizace

Dashboard kontroluje vydání každou půlhodinu. Ikona **Je k dispozici aktualizace** ověří, nainstaluje aktualizaci a restartuje dashboard. **Aktualizace čeká na tasky**: po doběhnutí klikni znovu.

CLI (soubor/`https`):

```bash
factory upgrade --dry-run haifa-<verze>.zip
factory upgrade haifa-<verze>.zip
```

`factory upgrade` ověří `SHA256SUMS`, nainstaluje novější verzi, obnoví knihovnu (`factory library seed --all`, [Knihovna a tým](#/guide/knihovna-a-tym/seminko)). Dashboard restartuj; na Windows předem zastav (`dashboard_running`).

Vydání: `just bundle`.

## Řešení problémů

Modrý čip **System info**: volné místo disku a paměť v GB, obnova každou minutu. **Uklidit disk** odstraní osiřelé návrhy, hotové worktrees a větve sloučených PR všech rep; výsledek ukáže tooltip.

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

## Převzetí starých voleb automatizace

Po instalaci restartuj již spuštěný dashboard (`factory obs`). Neupgradovaný počítač
používá frontmattery, upgradovaný místní volby v HAIFA_HOME: automatizace jsou bez záznamu
vypnuté, harness dědí z počítače.

Staré volby si můžeš prohlédnout příkazem:

```sh
factory config local legacy --repo PATH --json
factory config local import --repo PATH --json
```

Náhled ukáže hodnoty a původ přes projekt, step a task. Shodné hodnoty převezmeš přímo;
rozpory vyžadují výběr pro celé repo, například
`--auto-merge off --auto-continue on --harness codex`. Model/thinking se nepřenášejí; harness použije místní nastavení.
Existující místní volby přepíše pouze výslovné `--overwrite`. Import je atomický,
idempotentní a píše jen do HAIFA_HOME; jiný HAIFA_HOME má vlastní volby, worktrees je sdílí.

Čtení, upgrade ani git pull místní volby nemění. Legacy pole zachovej pro neupgradované
počítače; editace, schválení a sync je ponechají. Přechod nevyžaduje commit ani min-version
bariéru; odstranění polí je samostatný krok. Staré `backlog auto-continue`,
`backlog auto-merge` a `task edit --auto-merge` vracejí deprekační chybu; použij
`factory config local set --auto-continue on|off` nebo `--auto-merge on|off`.
