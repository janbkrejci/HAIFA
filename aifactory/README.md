# GIRO — Goal in. Release out.

GIRO je lokální dashboard a CLI `giro`, které pouští kódovací agenty (Claude Code, Codex, pi) na úkoly z backlogu v tvých Git repech. Každý task běží ve vlastním worktree a větvi, projde workflow agentů (plán, implementace, testy, review) a skončí pull requestem.

## Instalace

GIRO bundle získáš od správce týmu; cílové repo `janbkrejci/GIRO` se stane veřejným zdrojem až po cutoveru T06. Dosud aktivní HAIFA releases poskytují starý HAIFA bundle. Přechod vede přes poslední HAIFA s alertem, viz instalační příručka. `factory` a `HAIFA_*` jsou kompatibilní aliasy; technické cesty a distribuce `aifactory` zůstávají.

```bash
unzip giro-<verze>.zip
cd giro-<verze>
./install.sh
giro check
giro obs
```

Úplný postup včetně prerekvizit pro macOS, Linux a Windows je v `INSTALL.md` v distribučním balíčku.

## Příručka

Uživatelská a administrační příručka je součástí dashboardu: spusť `giro obs` a klikni na ikonu knihy v horní liště. Kapitoly pokrývají první spuštění, backlog a tasky, běhy, review, konfiguraci repa, agenty a workflow, knihovnu, nastavení počítače, práci v týmu, aktualizace, příkazovou řádku a řešení problémů.

Zdroj příručky jsou markdown soubory v `src/aifactory/guide/`; instalační kapitola je zároveň `INSTALL.md` balíčku.

Agent (Claude Code, Codex, pi) dostane postupy v angličtině z `giro --skill`; výstup ulož jako jeho `SKILL.md` a po každé aktualizaci GIRO ho vygeneruj znovu.

## AI průvodce s Codexem

Průvodce podporuje Codex CLI 0.167.2 s modelem z jeho vestavěného katalogu. Dostává pouze datovou bránu pro čtení, bez shellu a souborových nástrojů. Jiné verze CLI se pro průvodce odmítnou, dokud neprojdou ověřením izolace. Claude zůstává podporovaný; pi používá dostupný Claude.

Codex průvodce má vlastní adresář `$GIRO_HOME/assistant/codex`, aby nenačítal osobní instrukce a skilly. Souborové přihlášení sdílí symlinkem na původní `auth.json`; tokeny se nekopírují. Na Windows je pro vytvoření symlinku potřeba Developer Mode. Alternativou je samostatné přihlášení: spusť `codex login` s proměnnou `CODEX_HOME` nastavenou jen pro tento příkaz na adresář průvodce. To potřebuje i uživatel systémové klíčenky. Do adresáře průvodce nepřidávej `AGENTS.md` ani `AGENTS.override.md`.

Běžné giro tasky dál používají původní prostředí Codexu, repo instrukce, skilly, shell a souborové nástroje. Omezení průvodce se na ně nepřenášejí.

## Licence

GIRO je pod licencí MIT. Licence převzatých částí jsou v `THIRD_PARTY_NOTICES`.
