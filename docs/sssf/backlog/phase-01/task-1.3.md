Přidej do prototypu harness Codex a výslovnou volbu harnessu u agenta podle rozhodnutí D13 v `docs/product-brief.md`: tři adaptéry se stejným rozhraním (Claude Code, Codex, pi), harness zapsaný výslovně, ne odvozený ze jména modelu.

Where: `prototype/src/haifa_proto/harness/` (registr a adaptér `codex.py`), testy v `prototype/tests/`.

Done means:
- Adaptér Codexu má stejné rozhraní jako `vendor/sssf/templates/adws/adw_modules/agent_cc.py`: `run(request, on_event, on_wait, on_spawn, on_exit) -> AgentResult`, `resolve_model`, `context_window`, `ToolCallTracker`. Spouští `codex exec --json` s `-m` a `-C <request.cwd>`, systémový prompt předává tak, jak ho Codex CLI přijímá, a opravná kola (neplatný JSON, porušené gates) posílá do téže session přes `codex exec resume`.
- `ToolCallTracker` převádí JSONL události Codexu na stejné záznamy `tool_call`, jaké vytváří tracker Claude Code, a `AgentResult` nese text poslední odpovědi, tokeny a náklady, pokud je Codex hlásí.
- Registr harnessů `claude`, `codex`, `pi` mapuje na moduly adaptérů a za běhu je zapíše do `agents.INTERFACES`. Prototyp rozšiřuje typy konfigurace agenta (`coding_agent` dnes povoluje jen `pi` a `claude_code`) ve vlastním kódu.
- Kontraktový test běží nad všemi třemi adaptéry s falešným procesem místo skutečného CLI: nahraný JSONL výstup → očekávaný `AgentResult` a záznamy `tool_call`. U Codexu i pro opravné kolo.
- `haifa-proto harness check` vypíše pro každý harness, jestli je CLI na PATH a jakou má verzi (`codex --version`, `claude --version`, `pi --version`).

Out of scope: workflow interpret, volba harnessu u kroku (úkol 1.4), běh ve worktree.

Pevná omezení:
- `vendor/` se neupravuje. Rozšíření se registrují za běhu.
- Testy nespouštějí skutečné CLI ani model.
- Omezení zápisů (`writes:`) zůstává na `permissions.py`, které kontroluje git diff nezávisle na harnessu. Adaptér nesmí zápisy povolovat ani obcházet.
