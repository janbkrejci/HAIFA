Přenes YAML verze stávajících ADW do výchozích workflow balíčku: `plan`, `plan-build`, `plan-build-test`, `simple-sdlc`, `document` a `scout`.

Where: `aifactory/src/aifactory/defaults/workflows/`, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/defaults/workflows/`.

Done means:
- Všech šest workflow projde `factory workflow check`.
- Každé workflow proběhne s falešným harnessem a vyprodukuje stejné pořadí fází jako Python ADW stejného jména, se sémantikou smyček z 2.7.
- `simple-sdlc` po posledním zamítnutí review už nespouští `revise`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: workflow `resolve` (2.14), typ workflow `script`.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
