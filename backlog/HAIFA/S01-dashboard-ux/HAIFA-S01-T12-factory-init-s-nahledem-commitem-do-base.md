---
id: HAIFA-S01-T12
title: "factory init s náhledem, commitem do base a vazbami po agentech"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S01-T11, HAIFA-S04-T01]
---

## Zadání
Rozšiř `factory init` z HAIFA-S04-T01 o náhled plánu a o instalaci jedním commitem do base, kterou dashboard použije u repa bez factory. Bez nových voleb zůstává chování HAIFA-S04-T01: soubory se zapíší do pracovního stromu, existující se přeskočí a nic se necommituje.

Where: `aifactory/src/aifactory/cli.py`, init z HAIFA-S04-T01, položky, knihovna a manifest z L1, L2 a L4 v `aifactory/src/aifactory/library/`, zveřejnění commitu z M7, `aifactory/src/aifactory/config/` (`settings.py`, `loader.py`, `source.py`, `status.py`), `aifactory/src/aifactory/run/gitops.py`, `aifactory/src/aifactory/harness/check.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/`.

Done means:
- `factory init --dry-run --json` vrátí plán (soubory s obsahem včetně manifestu, blokátory, varování, `digest`), zjištěné hodnoty `detected` a nabídku `available`. `detected`: base z `refs/remotes/<remote>/HEAD`, jinak aktuální větev, provider z URL remote (github.com v https, ssh i scp tvaru dá `github`, dev.azure.com, ssh.dev.azure.com a *.visualstudio.com dají `azure` s organizací, projektem a repem, bez remote `local`) a nainstalované harness CLI. `available`: agenti a workflow z knihovny (bez knihovny ze semínka) s výchozími vazbami.
- `factory init --commit [--pr] [--expect DIGEST] [-m TEXT] --json` provede tentýž plán jedním commitem cestou z M7. Do pracovního stromu před úspěšným push nic nezapíše.
- Nové volby `--provider azure` s `--azure-org`, `--azure-project` a `--azure-repo`, `--backlog-dir`, `--specs-dir` a `--docs-dir`. `$specs_dir/` a `$docs_dir/` ve `writes` se nahradí zvolenými adresáři. `--agents`, `--bind` a `--workflows` z HAIFA-S04-T01 platí v obou režimech (vazby po agentech podle D24).
- Vazba na harness, jehož CLI na stroji chybí, dá varování `harness_missing` a neblokuje.
- Plán se ověří: konfigurace z base doplněná o plánované soubory projde `load_config` a preflight každého zapsaného workflow.
- Blokátory: manifest v base (`already_installed`, poradí `factory update`), konfigurace sssf nebo `.factory/` bez manifestu (`existing_config`, poradí `factory onboard`), konfigurace jen v pracovním stromu (`config_not_committed`, poradí `factory config commit`), plánovaná cesta v pracovním stromu s jiným obsahem (`dirty_paths`) a blokátory z M7.
- U `--commit`: má-li `.gitignore` necommitnuté změny, řádky runtime factory jdou do `info/exclude` a plán to ukáže. Adresář backlogu dostane `.gitkeep`, jen když neexistuje. Adresář backlogu, specs nebo docs s cizím obsahem dá varování.
- `factory --skill` v postupu instalace ukáže `factory check`, náhled, digest a commit s `--expect` a při `push_failed` zopakování s `--pr` po souhlasu uživatele. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s holým remote: náhled nic nezapíše, commit a push, odmítnutý push nezmění repo, PR přes falešný `gh`, `plan_changed`, `dirty_paths`, špinavý `.gitignore`, azure z URL, tabulkové testy parseru URL, builder na codexu a ostatní agenti na claude, `existing_config` u fixtury sssf, po instalaci `factory check` bez chyb a `factory config items` se všemi položkami `synced`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: aktualizace (M9), onboarding existující konfigurace (O2, O4), instalace nástrojů (`gh`, `az`, harnessy), dashboard.

Pevná omezení:
- `init` bez `--commit` nic necommituje a bez `--force` nic nepřepíše.
- `init` nezapisuje do knihovny ani do `$HAIFA_HOME`.
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/59 · náklady $8.92
