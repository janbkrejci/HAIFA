Přidej auto-continue a bezpečné paralelní běhy podle rozhodnutí D10 a Q9 v `docs/product-brief.md`: po úspěšném běhu se spustí další připravený task. Když další task čeká na nemergnutý PR, přeskočí se a spustí se task, který spustit jde.

Where: `prototype/src/haifa_proto/run.py`, případně `prototype/src/haifa_proto/queue.py`, CLI, testy v `prototype/tests/`.

Done means:
- Auto-continue zapíná `auto_continue: true` v `index.md` modulu nebo stepu, nebo `haifa-proto task run <task-id> --auto`.
- Po úspěšném běhu (PR vytvořen) se vybere další task ve stejném stepu, pak ve stejném modulu, v pořadí backlogu. Task, jehož závislost je jen v otevřeném PR, se přeskočí. Když už nic spustit nejde, řetěz skončí s výpisem, na co čeká.
- Selhání běhu řetěz zastaví.
- Dva procesy `task run` na různé tasky běží současně bez kolize. Dva procesy na týž task: jeden skončí chybou. Zámek je v trace DB (transakce), ne v souboru.
- Testy s falešným harnessem a providerem `local`: tři nezávislé tasky proběhnou v pořadí; závislý task se přeskočí a spustí se až po `task approve`; selhání zastaví řetěz; dva souběžné běhy různých tasků projdou; souběžný start téhož tasku jeden odmítne.

Out of scope: plánovač napříč moduly, limit paralelity, web.

Pevná omezení:
- Auto-continue nikdy sám neschvaluje ani nemerguje.
- Testy nevolají model.
- `vendor/` se neupravuje.
