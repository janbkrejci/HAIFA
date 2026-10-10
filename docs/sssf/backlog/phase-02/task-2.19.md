Sjednoť názvy výstupů v promptech agentů s pojmenováním podle tasku z úkolu 2.9. Validace proti GitHubu selhala ve všech scénářích s agentem, protože prompt planneru v šabloně sandboxu (`aifactory/validation/template/.factory/prompts/planner/user.md`) říká „zapiš spec jako `specs/<adw_id>_<slug>.md`“. Hlídač zápisů povoluje jen `specs/<task-id>-<slug>.md`, takže běh skončí `run_failed: planner changed paths outside its task run`.

Where: `aifactory/src/aifactory/run/`, prompty agentů v `aifactory/` (výchozí konfigurace i `aifactory/validation/template/.factory/prompts/`), falešný harness validace, `aifactory/tests/`.

Done means:
- Běh předá agentům přesné cesty výstupů tasku jako proměnné promptu (např. `{{spec_path}}` a `{{doc_path}}`). Prompty planneru a documenteru je používají a název si agent nevymýšlí.
- Žádný prompt v `aifactory/` neobsahuje pojmenování podle `adw_id` (`<adw_id>_`). Hlídá to test.
- Falešný harness validace čte cestu výstupu z vykresleného promptu, ne z vlastního pravidla, takže `just validate --remote local` odhalí nesoulad promptu a hlídače.
- Test: prompt s pojmenováním podle `adw_id` v lokální validaci selže s `run_failed`, prompt s `{{spec_path}}` projde.
- `just validate --remote local` projde bez `failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna hlídače zápisů, změna pojmenování z úkolu 2.9.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.
