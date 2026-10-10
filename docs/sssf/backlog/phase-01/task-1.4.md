Implementuj interpret YAML workflow podle sekce „Workflow jako data“ v `docs/product-brief.md` nad enginem z `vendor/sssf/templates/adws/adw_modules/`, včetně volby harnessu, modelu a thinking u každého kroku.

Where: `prototype/src/haifa_proto/workflow.py`, `prototype/src/haifa_proto/roles.py`, výchozí soubory `prototype/src/haifa_proto/defaults/roles.yaml` a `prototype/src/haifa_proto/defaults/workflows/*.yaml`, testy v `prototype/tests/`.

Done means:
- Registr rolí v YAML: jméno kroku → agent, typ výstupu, gates, popis fáze. Typy výstupů a gates se hledají podle jména v `adw_modules.data_types` a `adw_modules.gates`. Obsahově odpovídá `vendor/sssf/templates/adws/adw_modules/roles.py`.
- Konstrukce: krok (role nebo kódový krok `test`, `commit`, `changes`, `command` s argv), `repeat` s `max` a `until`, `when`, `accept`. Krok smí přepsat `harness` (`claude`, `codex`, `pi`), `model` a `thinking`. Bez přepisu platí hodnoty agenta.
- Podmínky čtou jen pole envelopes a výsledků kódových kroků (`test.passed`, `review.approved`, `revise.ran`). Vyhodnocovač podporuje `and`, `or`, `not` a porovnání. Žádný `eval`.
- Workflow `simple-sdlc.yaml` vyjadřuje `vendor/sssf/templates/adws/adw_simple_sdlc.py`. Test s falešným harnessem ověří pro tři scénáře stejné pořadí fází, jaké popisuje docstring `Phases:` té Python verze: vše projde napoprvé, testy selžou jednou a oprava je spraví, review jednou zamítne a revize projde.
- Test s workflow, kde plan běží na `claude`, build na `codex` a review na `pi`, ověří, že každý krok dostal svůj harness a model a že envelope prošel mezi harnessy beze změny.
- Neplatný workflow (neznámá role, neznámý harness, `until` na neexistující pole, `repeat` bez `max`) skončí chybou při načtení, ne za běhu.
- `haifa-proto workflow check <soubor>` validuje workflow, `--json` vrací výsledek.

Out of scope: worktree, PR, backlog, web, grafický editor.

Pevná omezení:
- `vendor/` se neupravuje. Engine se importuje a rozšiřuje v `prototype/`.
- Každá fáze má popis, který neopakuje jen její jméno (pravidlo 7 v `vendor/sssf/SKILL.md`).
- Testy nevolají model.
