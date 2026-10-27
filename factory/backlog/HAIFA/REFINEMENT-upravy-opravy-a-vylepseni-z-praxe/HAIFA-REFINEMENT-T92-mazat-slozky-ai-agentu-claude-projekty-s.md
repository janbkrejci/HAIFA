---
id: HAIFA-REFINEMENT-T92
title: "Mazat složky AI agentů (Claude projekty, sessions) se smazaným vláknem, během, advice a worktree"
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T90]
writes: [aifactory/src/aifactory/harness/agent_dirs.py, aifactory/src/aifactory/providers/git.py, aifactory/src/aifactory/workflow/adaptive.py, aifactory/src/aifactory/web/assistant.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/review/flow.py, docs/decisions.md, aifactory/tests/harness/test_agent_dirs.py, aifactory/tests/web/test_web_assistant.py, aifactory/tests/web/test_web_runs.py, aifactory/tests/workflow/test_workflow_advice.py]
---

## Zadání
## Problém

Claude Code ukládá transkript každého sezení do `~/.claude/projects/<zakódovaná cwd>/` (nebo `$CLAUDE_CONFIG_DIR/projects`). Kódování nahradí každý znak mimo `[A-Za-z0-9]` znakem `-`. Po HAIFA tam zůstávají stovky složek pro `.factory/worktrees/<run-id>`, `%TEMP%/factory-advice-*/repo` (advisor, návrh workflow, Nový záměr) a pracovní adresář průvodce `<home>/assistant/threads/<id>/work`. Na jednom stroji to jsou 3 GB. HAIFA maže jen vlastní adresáře: `ThreadStore.delete` v `web/assistant.py` smaže složku vlákna, `advice_dir` v `workflow/adaptive.py` dočasný adresář a `delete_run`/`delete_archived` v `web/runs.py` jen řádky v DB. Složka `.factory/data/sessions/<run-id>` smazaného běhu přitom zůstává.

## Co udělat

1. Nový modul `aifactory/src/aifactory/harness/agent_dirs.py`:
   - `claude_project_dirs(cwd)`: kandidátní složky v `projects` pro danou cwd. Zakódovat cestu tak, jak byla předaná, i její `resolve()`. Na Windows se liší krátké 8.3 jméno (`JAN~1.KRE`) a dlouhé (`jan.krejci`), obě varianty jsou na disku vidět.
   - `remove_agent_dirs(cwd)`: smaže tyto složky best-effort (`remove_tree` z `workflow/adaptive.py` nebo jeho sdílená kopie), nikdy nevyhodí výjimku.
   - `sweep_orphans(prefixes, alive)`: smaže složky v `projects`, jejichž jméno začíná zakódovaným prefixem (worktrees_dir repa, `<tempdir>/factory-advice-`, `<home>/assistant/threads`) a nepatří žádné existující cestě. Nesmí smazat nic mimo tyto prefixy, ani složky uživatelových vlastních projektů.
2. Volání:
   - `providers/git.py` `remove_worktree`: po úspěšném odstranění worktree smazat jeho Claude složku.
   - `workflow/adaptive.py`: `advice_dir` při ukončení a `cleanup_orphans` pro osiřelé adresáře smažou i Claude složku `<tmp>/repo` a `<tmp>`. `cleanup_orphans` (běží při startu dashboardu) navíc zavolá sweep pro prefix `factory-advice-`.
   - `web/assistant.py` `ThreadStore.delete`: smazat i Claude složku pracovního adresáře vlákna.
   - `web/runs.py` `delete_run`/`delete_archived`: smazat i `.factory/data/sessions/<run-id>` (cesta přes `session_dir_of` z `run/task.py`) a Claude složku worktree běhu, pokud worktree už neexistuje.
   - `review/flow.py` `_clean`: zavolat sweep pro prefix `<main>/<worktrees_dir>`, aby se uklidily i staré složky z doby před tímto taskem.
3. Rozhodnutí (co se maže a kdy) zapsat do `docs/decisions.md`.

## Mimo rozsah

Codex ukládá rollouty do `~/.codex/sessions` podle data, ne podle cwd, a pi používá `--session-dir` ve složkách HAIFA. Ty se tu neřeší. Nemazat nic, co patří běžícímu běhu nebo vláknu, které právě odpovídá.

Hotovo znamená:
- Testy v `aifactory/tests/harness/test_agent_dirs.py` ověří kódování cesty (včetně Windows cesty s `~` a tečkou), respektování `CLAUDE_CONFIG_DIR` a to, že sweep nesmaže složku mimo prefixy ani složku existující cesty.
- Test ve `test_web_assistant.py` ukazuje, že smazání vlákna smaže i jeho Claude složku.
- Test ve `test_web_runs.py` ukazuje, že smazání archivovaného běhu smaže `.factory/data/sessions/<run-id>`.
- Test ve `test_workflow_advice.py` ukazuje, že po advice nezůstane Claude složka jeho `repo`.
- Odstranění worktree (approve, `task clean`) smaže jeho Claude složku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/181 · náklady $0.00
