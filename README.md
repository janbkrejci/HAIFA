# HAIFA — Helios AI Factory

HAIFA je lokální dashboard a CLI `factory` pro agentní úkoly ve více Git repozitářích. Každý task z backlogu v markdownu běží ve vlastním worktree a větvi přes workflow agentů (Claude Code, Codex nebo pi) a končí pull requestem, který schválíš nebo se mergne sám.

## Instalace

Stáhni `haifa-<verze>.zip` z [posledního vydání](https://github.com/janbkrejci/HAIFA/releases/latest) a postupuj podle kapitoly [Instalace](aifactory/src/aifactory/guide/02-instalace.md) příručky. Najdeš v ní prerekvizity, instalaci na macOS, Linux i Windows, aktualizaci a odinstalaci. Stejný návod je v balíčku jako `INSTALL.md`.

## První spuštění

```bash
factory check
factory obs
```

`factory obs` otevře dashboard na <http://127.0.0.1:4700>. Dál tě provede příručka v dashboardu (ikona knihy v horní liště), kapitola **První běh**.

## Vývoj

Navíc potřebuješ [Bun](https://bun.com/docs/installation) a [just](https://github.com/casey/just#installation) (`uv tool install rust-just`). Na Windows používej Git Bash na PATH.

```bash
uv sync --project aifactory
just web-build      # frontend do aifactory/src/aifactory/web/static
just dash           # dashboard ze zdrojů
just web-dev        # Vite na :4701 proti běžícímu `just dash`
just check          # frontend, backendové testy bez browseru, mypy, ruff
just e2e            # browserové testy (just e2e-install stáhne Chromium)
just bundle         # aifactory/dist/haifa-<verze>.zip
```

Při vývoji spouštěj jen dotčené testy, např. `just pytest tests/web/test_web_fs.py`.
Pytest vypisuje 20 nejpomalejších kroků. Počet workerů můžeš omezit pomocí `-n 2`
nebo testy spustit sériově přes `-n0`. Na Windows je výchozí počet jeden worker na
logické CPU, nejvýše osm. Úplná kontrola je `just check` a `just e2e`;
browserové testy se tak spustí jen jednou.

Struktura kódu a konvence jsou v [CLAUDE.md](CLAUDE.md), platná rozhodnutí v [docs/decisions.md](docs/decisions.md). Návod pro agenty, kteří HAIFA ovládají, vypíše `factory --skill`.

[GitHub Actions](.github/workflows/ci.yml) na každém commitu do `main` spustí testy, typovou kontrolu a lint, ověří instalaci na Windows a vydá release `haifa-<major>.<minor>.<číslo běhu>.zip`. Commity jen backlogu nebo `.factory/` CI přeskakuje, pull requesty se jen testují.

## Licence

HAIFA je pod licencí [MIT](LICENSE). Licence převzatých částí jsou v [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
