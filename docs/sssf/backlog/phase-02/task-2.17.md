Přenes validační scénáře do `aifactory` a vynuť v nich opravná kola, aby smyčky test → fix a review → revise opravdu proběhly.

Where: `aifactory/validation/`, `aifactory/tests/`, recept `just validate` v `justfile`. Zdroj: `prototype/validation/`.

Done means:
- `just validate --remote local|github [--roster DIR]` spustí scénáře R1–R5 a R10 nad CLI `factory` se stejnými výstupy jako prototyp (`summary.json`, `R*.json`, logy, trace). Roster bez harnessu, který scénář ověřuje, dává `inconclusive`.
- Opravné kolo test → fix: scénář má skrytý test s požadavkem, který ze zadání nejde odvodit (např. výsledek začíná prefixem `x-`), takže `test_1` vždy selže a proběhne `fix`.
- Opravné kolo review → revise: validační roster má reviewera s pravidlem „v prvním kole vždy zamítni a požaduj konkrétní změnu“, takže vždy proběhne `revise` a druhé review.
- Nový scénář B1: agent zapíše soubor do hlavního checkoutu, zápis se vrátí a fáze selže.
- Nový scénář resolve: konflikt dvou PR se vyřeší přes `task resolve` a oba PR se mergnou.
- `just validate --remote local` projde bez `failed` a test ho spouští.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: akceptační scénář F2 (2.18).

Pevná omezení:
- Pravidla vynucující opravná kola jsou jen ve validačním rosteru a scénářích, ne ve výchozí konfiguraci produktu.
- `vendor/` a `prototype/` se nemění.
