# Nastavení repozitáře a projektů

Na stránce **Nastavení** jsou tři oddělené části:

- **Lokální necommitované nastavení** v `.factory/local.yaml` platí jen na vašem
  stroji. Soubor zůstává mimo Git.
- **Sdílené nastavení repozitáře** v `.factory/config.yaml` určuje výchozí cesty
  a ostatní stávající parametry repozitáře.
- **Sdílené nastavení projektu** zapisuje tři cesty do `index.md` vybraného
  projektu (nejvyšší úroveň backlogu). Přepínač obsahuje projekty aktuálního
  repozitáře a u každé cesty ukazuje vlastní nebo zděděnou hodnotu s původem.

Například dva projekty mohou mít `workdir: packages/server` a
`workdir: packages/client`, vlastní `specs_dir: output/server/specs` a
`specs_dir: output/client/specs` a obdobně vlastní `docs_dir`.
**Obnovit dědění** vyprázdní pole; **Uložit projekt** odstraní klíč z hlavičky,
takže opět platí hodnota repozitáře. Úprava projektu nemění ostatní projekty.

Všechny tři cesty jsou relativní ke kořeni repozitáře. Pracovní adresář agentů
je podadresář izolovaného worktree; význam `specs_dir`, `docs_dir`, `writes`
a relativních cest artefaktů se nemění. Git a testovací příkazy workflow
běží dál od kořene repozitáře. Pracovní adresář musí existovat ve sdíleném
commitu. Výstupní adresáře mohou být vytvořeny při běhu. Absolutní cesty,
`..`, Windows drive/backslash syntaxe a adresáře unikající přes symlink se
odmítnou. Běhy nepovolují symlinkové komponenty těchto adresářů.

Sdílené soubory je nutné **commitovat do base větve**: běhy čtou konfiguraci
a backlog z base commitu, nikoli necommitované změny formuláře. Uložení samo
commit nevytváří. Existující přetížení výstupů na stepu a tasku mají dál
přednost před projektem. `workdir` se přetěžuje pouze na projektu.
