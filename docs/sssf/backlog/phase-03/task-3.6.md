Implementuj obrazovku Nastavení podle odstavce „Nastavení projektu“ v sekci „Dashboard“ v `docs/product-brief.md` a ukaž necommitnuté změny konfigurace (D4).

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Done means:
- Formulář pro sdílené nastavení v `.factory/config.yaml` (pracovní adresář agentů, adresář backlogu, specs a dokumentace, worktree, `base`, git provider, merge strategie, výchozí testovací příkaz, chráněné soubory) a lokální v `.factory/local.yaml` (port, cesta k trace DB).
- Uložení validuje hodnoty a zapisuje soubor. Neplatná hodnota se neuloží a UI ukáže chybu u pole.
- Pruh s varováním na všech obrazovkách, když má `.factory/` necommitnuté změny proti `base` (stejná funkce jako `factory config status`), se seznamem souborů.
- Testy API nad dočasným repem a unit testy formuláře.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: commit konfigurace tlačítkem a editory agentů, promptů a workflow (F4).

Pevná omezení:
- `.factory/local.yaml` se nikdy necommituje.
- `vendor/` a `prototype/` se nemění.
