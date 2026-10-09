---
id: HAIFA-S05-T15
title: Semínko knihovny podle .factory/prompts
status: cancelled
depends_on: []
---

## Zadání
`tests/library/test_library_seed.py` vyžaduje, aby semínko knihovny `aifactory/src/aifactory/seed/agents/<agent>/` bylo bajtově stejné jako `.factory/prompts/<agent>/` a aby verze položky semínka odpovídala kopii v repu. Commit fb4f8ad (PR #22) změnil `.factory/prompts/builder/system.md` a `.factory/prompts/reviewer/system.md` (zákaz spouštět celou testovací sadu), ale semínko ne. `main` od té doby padá na 4 testech (`test_seed_prompts_equal_haifa[system-builder]`, `[system-reviewer]`, `test_seed_version_equals_haifa_repo_copy[builder]`, `[reviewer]`) a každý běh to opravuje ve své větvi.

Where: `aifactory/src/aifactory/seed/agents/builder/`, `aifactory/src/aifactory/seed/agents/reviewer/`.

Done means:
- Semínko builderu a revieweru je bajtově stejné jako `.factory/prompts/builder/` a `.factory/prompts/reviewer/` v base.
- Verze položek builder a reviewer v semínku odpovídá kopii v repu.
- `tests/library/test_library_seed.py` projde celý.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: změny `.factory/` a změny testů.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
