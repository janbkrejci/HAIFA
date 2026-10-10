Přidej do `just proto-validate` volbu `--roster DIR`, která pro daný běh nahradí `.factory/sssf.config.yaml` a `.factory/workflows/simple-sdlc.yaml` ze šablony sandboxu soubory `DIR/sssf.config.yaml` a `DIR/workflows/simple-sdlc.yaml`. Scénáře R1 a R10 hlásí `inconclusive` místo `failed`, když použitý roster nemá harness, který ověřují (R1: claude, codex i pi v jednom workflow; R10: build a fix na codexu).

Where: `prototype/validation/`, `prototype/tests/`, recept `proto-validate` v `justfile`.

Done means:
- `just proto-validate --remote github --roster DIR` použije config a workflow z `DIR`. Bez `--roster` se chování nemění.
- Nový test v lokálním režimu s rosterem bez codexu (claude + pi): R1 a R10 jsou `inconclusive`, ostatní scénáře `passed`.
- `inconclusive` nezpůsobí nenulový exit kód, `failed` ano.
- `tests/test_validation_local.py` projde beze změny.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změna výchozí šablony sandboxu, přidání konkrétního rosteru (přidá engineer).

Pevná omezení:
- `vendor/` se neupravuje.
