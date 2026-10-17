---
id: DEMO-S01-T01
title: Počet znaků
status: todo
depends_on: []
---

## Zadání
Přidat do `textstats.py` funkci `char_count(text: str, *, spaces: bool = True) -> int`.
Vrací počet znaků textu `text`. Se `spaces=False` nepočítá bílé znaky (mezery, tabulátory,
konce řádků).

Funkci přidat do `__all__` a napsat jí docstring.

Hotovo znamená:
- Testy v `tests/test_textstats.py`: prázdný text, text s mezerami a konci řádků v obou
  režimech.
- `python -m unittest discover -s tests -t .` projde.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
