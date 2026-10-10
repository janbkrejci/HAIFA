Přenes interpret YAML workflow do `aifactory` podle sekce „Workflow jako data“ v `docs/product-brief.md` a změň sémantiku `until`: podmínka se vyhodnocuje po každém kroku těla `repeat` a smyčka končí hned, jak platí.

Where: `aifactory/src/aifactory/workflow/`, `factory workflow check`, `aifactory/tests/`. Zdroj: `prototype/src/haifa_proto/workflow.py`, `roles.py`, `defaults/roles.yaml`.

Done means:
- Konstrukce krok, `repeat` s `max` a `until`, `when`, `accept`. Podmínky čtou jen pole typovaných envelopes. Registr rolí z `.factory/roles.yaml`.
- `until` se vyhodnocuje po každém kroku těla. Příklad `repeat: {max: 2, until: review.approved}` s tělem `[review, revise]`: když review v posledním kole zamítne, `revise` se už nespustí a smyčka skončí. Když test projde, `fix` se nespustí.
- Nový kódový krok `command` s argv z konfigurace (např. `dotnet test`) a výsledkem `passed` podle exit kódu.
- `factory workflow check <soubor> [--json]` validuje workflow proti registru rolí a agentů.
- Testy s falešným harnessem pokryjí obě smyčky včetně případu, kdy `max` dojde, a `when` na kroku.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: YAML verze stávajících ADW (2.8), běh ve worktree (2.9), krok `pr` (2.12).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Podmínky nespouští volný Python.
