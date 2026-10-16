---
id: DEMO-S01-T02
title: Nejčastější slova
status: todo
depends_on: [DEMO-S01-T01]
---

## Zadání
Přidat do `textstats.py` funkci `top_words(text: str, n: int = 3) -> list[tuple[str, int]]`.
Vrací nejvýš `n` nejčastějších slov textu jako dvojice `(slovo, počet)`.

Pravidla:
- Slova bere z existující funkce `words` (malá písmena, bez interpunkce).
- Řazení podle počtu sestupně, při shodě podle slova abecedně.
- `n` menší než 1 vyvolá `ValueError`. Prázdný text vrátí prázdný seznam.

Funkci přidat do `__all__` a napsat jí docstring.

Hotovo znamená:
- Testy v `tests/test_textstats.py` pokrývají řazení, shodu počtů, `n` větší než počet slov,
  prázdný text a `ValueError`.
- `python -m unittest discover -s tests -t .` projde.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
