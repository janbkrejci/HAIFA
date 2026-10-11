# HAIFA-S07-T04: Návod pro tým a postupy ve `factory --skill`

- `aifactory/README.md`: český návod pro kolegy (předpoklady, instalace z bundlu,
  `factory check`, knihovna, přidání repa a převzetí repa s commitnutou `.factory/`,
  aktualizace přes `factory upgrade` a `factory library seed`, vydání, tabulka kódů
  kontroly stroje a knihovny s opravou). `pyproject.toml` ho uvádí jako `readme`.
- `factory --skill` má nové postupy *Set up a machine*, *Take over a repo with committed
  `.factory/`*, *Manage items* a shrnutí upgradu v *Upgrade*; odkazují na existující
  sekce Check, Library, Commit configuration a Items of the repo, nic neduplikují.
  Popis ve front matter skillu už nevylučuje nastavení stroje ani upgrady.
- `factory config add` v CLI neexistuje (a test skillu ho zakazuje), proto ho návod ani
  skill neuvádějí; položku jen pro repo agent zapíše přímo do `.factory/`.
- Testy v `aifactory/tests/test_skill.py`: README obsahuje každý kód z
  `check/machine_rules.py` a `check/library_rules.py`, každý `factory …` v kódu README
  i skillu existuje v parseru, skill obsahuje nové postupy, `pyproject.toml` má `readme`.
