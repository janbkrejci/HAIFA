Implementuj obrazovku Review: PR mých modulů a PR čekající na mé review, diff, výsledky gates a testů, verdikt revieweru, Schválit, Vrátit s poznámkou a Vyřešit konflikt (tabulka „Dashboard“ a kroky 5 a 6 v sekci „Běh úkolu“ v `docs/product-brief.md`).

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Done means:
- Seznam otevřených PR tasků s vlastníkem modulu, stavem mergeability a náklady. Filtr „moje moduly“ podle vlastníka v `index.md`.
- Detail PR: popis, diff po souborech, výsledky gates a testů, verdikt revieweru a odkaz na běh.
- Schválit, Vrátit s poznámkou a Vyřešit konflikt volají tytéž funkce core jako `factory task approve|return|resolve`. Při `conflict` UI nabídne Vyřešit.
- UI ukazuje, že schválení zatím neposílá approve review v hostingu (otevřený bod OB3).
- Testy API s providerem `local` a unit testy komponent.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: approve review jménem uživatele (OB3).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.
