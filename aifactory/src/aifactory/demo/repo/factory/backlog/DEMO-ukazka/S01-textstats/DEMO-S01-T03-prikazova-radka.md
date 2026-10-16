---
id: DEMO-S01-T03
title: Příkazová řádka
status: todo
depends_on: [DEMO-S01-T02]
---

## Zadání
Přidat do `textstats.py` funkci `main(argv: list[str] | None = None) -> int` a na konec
souboru `if __name__ == "__main__": raise SystemExit(main())`, aby šlo spustit
`python -m textstats SOUBOR`.

Chování:
1. Argumenty čte modulem `argparse`: povinná cesta `SOUBOR` a volitelné `--top N`
   (výchozí 3).
2. Soubor přečte v kódování UTF-8 a vypíše čtyři řádky. Pro soubor s textem
   `"Hello world.\nHello again, world!\n"` a výchozí `--top`:
   ```
   lines: 2
   words: 5
   chars: 33
   top: hello 2, world 2, again 1
   ```
   `chars` je `char_count` se `spaces=True`, `top` je `top_words` s `--top`, dvojice
   oddělené čárkou a mezerou. Bez slov je řádek `top: -`.
3. Vrátí 0. Neexistující soubor vypíše chybu na stderr a vrátí 1.

Hotovo znamená:
- Testy v `tests/test_textstats.py` volají `main` s dočasným souborem (`tempfile`)
  a ověří výstup (`contextlib.redirect_stdout`), `--top` a neexistující soubor.
- `python -m unittest discover -s tests -t .` projde.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
