# vendor/sssf

Snapshot skillu sssf jako reference pro HAIFA. Jen ke čtení, agenti ho nesmí měnit (`protected_files`).

- Zdroj: `../sssf`, adresář `.claude/skills/sssf/`
- Commit: `aa8b55c` (observer: copy session ID from the card in one click)
- Vytvořeno: 2026-09-26 přes `git archive`, jen sledované soubory (bez `node_modules`)

Obnovení na novější verzi: `git -C ../sssf archive <commit> .claude/skills/sssf | tar -x -C vendor/sssf --strip-components=3` a úprava tohoto souboru.
