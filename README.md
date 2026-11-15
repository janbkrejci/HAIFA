# GIRO — Goal in. Release out.

GIRO je lokální dashboard a CLI `giro` pro agentní úkoly ve více Git repozitářích. Každý task z backlogu v markdownu běží ve vlastním worktree a větvi přes workflow agentů (Claude Code, Codex nebo pi) a končí pull requestem, který schválíš nebo se mergne sám.

## Instalace

GIRO bundle `giro-<verze>.zip` získáš od správce týmu. Cílové repo `janbkrejci/GIRO` bude veřejným instalačním zdrojem až po ověřeném cutoveru T06; dosud aktivní [vydání HAIFA](https://github.com/janbkrejci/HAIFA/releases/latest) obsahují `haifa-<verze>.zip`. Ze starší HAIFA nejprve přejdi na poslední HAIFA s alertem „HAIFA se přejmenovává na GIRO“, pak použij jeho přechodovou akci. Instalaci, zálohy, návrat a odinstalaci popisuje [příručka](aifactory/src/aifactory/guide/02-instalace.md); je také v bundlu jako `INSTALL.md`.

`factory` a `HAIFA_*` zůstávají kompatibilní aliasy; `.factory/`, `factory/`, distribuce `aifactory` a HAIFA-LIBRARY zachovávají technickou identitu. [Kontrakt přechodu](docs/rebranding/giro.md) vysvětluje výjimky.

## První spuštění

```bash
giro check
giro obs
```

`giro obs` otevře dashboard na <http://127.0.0.1:4700>. Dál tě provede příručka v dashboardu (ikona knihy v horní liště), kapitola **První běh**.

## Vývoj

Navíc potřebuješ [Bun](https://bun.com/docs/installation) a [just](https://github.com/casey/just#installation) (`uv tool install rust-just`). Na Windows používej Git Bash na PATH.

```bash
uv sync --project aifactory
just web-build      # frontend do aifactory/src/aifactory/web/static
just dash           # dashboard ze zdrojů
just web-dev        # Vite na :4701 proti běžícímu `just dash`
just check          # frontend, backendové testy bez browseru, mypy, ruff
just e2e            # browserové testy (just e2e-install stáhne Chromium)
just bundle         # aifactory/dist/giro-<verze>.zip
```

Při vývoji spouštěj jen dotčené testy, např. `just pytest tests/web/test_web_fs.py`.
Pytest vypisuje 20 nejpomalejších kroků. Počet workerů můžeš omezit pomocí `-n 2`
nebo testy spustit sériově přes `-n0`. Na Windows je výchozí počet jeden worker na
logické CPU, nejvýše osm. Úplná kontrola je `just check` a `just e2e`;
browserové testy se tak spustí jen jednou.

Struktura kódu a konvence jsou v [CLAUDE.md](CLAUDE.md), platná rozhodnutí v [docs/decisions.md](docs/decisions.md). Návod pro agenty, kteří GIRO ovládají, vypíše `giro --skill`.

[GIRO release workflow](.github/workflows/giro-release.yml) vydává pouze z nového veřejného repo s explicitním `GIRO_RELEASE_ENABLED=true`. [Přechodový HAIFA workflow](.github/workflows/ci.yml) publikuje pouze schválený uchovaný zdroj poslední HAIFA. Rebrandingový main starého repo nic nevydává. CI nenahrazuje lokální testy, lint, typovou kontrolu ani kontrolu Windows; před mergem spusť `just check` a `just e2e`.

## Licence

GIRO je pod licencí [MIT](LICENSE). Licence převzatých částí jsou v [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
