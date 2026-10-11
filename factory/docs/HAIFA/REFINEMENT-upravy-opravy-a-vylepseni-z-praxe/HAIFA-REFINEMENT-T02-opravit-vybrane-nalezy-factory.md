# HAIFA-REFINEMENT-T02: Opravit vybrané nálezy Factory

## Výsledek `factory check` (main @ fb7b9d8)

`0 error(s), 1 warning(s), 2 info`, exit 0.

## Vybrané nálezy

### 1. sssf_leftover (repo, info): neopraveno, mimo oprávnění běhu

Nález stále platí: `adws/ is still committed next to .factory/ in main; runs ignore it`.

Překážka: `adws/` je v `protected_files` v `.factory/config.yaml` a není mezi
povolenými cestami běhu (`aifactory/`, `justfile`, spec a tento dokument).
Smazání v běhu by hlídač vrátil a fáze by selhala. CLAUDE.md navíc vede `adws/`
jako zálohu (sssf factory) pro případ, že HAIFA nepůjde použít.

Postup pro operátora:

1. Ověř, že v repu už nikdo nespouští sssf (`adws/`) a záloha není potřeba.
2. Na hlavním checkoutu mimo běh: `git rm -r adws/` a commit samostatně,
   např. `Remove sssf leftover adws/`.
3. Odeber `adws/` z `protected_files` v `.factory/config.yaml` a řádek `adws/`
   z tabulky dokumentů a sekce Ochrana v `CLAUDE.md` (chráněné soubory, mění operátor).
4. Spusť `just factory check`; nález `sssf_leftover` zmizí.
