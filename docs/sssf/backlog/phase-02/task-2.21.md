Oprav dvě chyby, které ukázala validace proti GitHubu (`just validate --remote github`, běh `github-160918`):

1. Scénář R10: skrytý test se v `test_1` vůbec nespustil. Výstup `test_1` neobsahuje `HiddenSlugifyTest`, `test_1` prošel a opravné kolo `fix` nenastalo, takže R10 skončil `inconclusive`.
2. Workflow `resolve`: rebase a agent `resolve` doběhly, ale testy po vyřešení konfliktu selhaly a běh skončil `accept not met`. Workflow nemá smyčku test → fix.

Where: `aifactory/validation/` (scénář R10 a jeho sandbox), `aifactory/src/aifactory/defaults/workflows/resolve.yaml`, role v `defaults/roles.yaml`, `aifactory/tests/`.

Done means:
- Skrytý test R10 je v sandboxu tam, kde ho `just test` sandboxu opravdu spustí, a agent ho před `test_1` nevidí ani neodstraní. Test v lokálním režimu ověří, že výstup `test_1` obsahuje jméno skrytého testu a že `test_1` selže.
- `resolve.yaml` má po kroku `resolve` smyčku `repeat: {max: 3, until: test.passed}` s kroky `test` a `fix`, stejně jako `simple-sdlc`. Test s falešným harnessem: resolve rozbije test, fix ho opraví a běh projde.
- `just validate --remote local` projde bez `failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna modelů v rosterech, spolehlivost JSON výstupu modelu na pi.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
