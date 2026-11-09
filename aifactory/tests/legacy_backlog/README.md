# Frozen compatibility reader

These modules come from pre-S11 commit `9c10094` (the previous shared-backlog implementation).
Only internal `aifactory.backlog` imports are renamed to `legacy_backlog` and import groups
are formatted. Configuration and YAML helpers remain the package's unchanged public helpers.
The independent loader, model, inheritance resolver and frontmatter parser deliberately
remain frozen, so testing the current reader against itself cannot hide a format break.
`tests/backlog/test_legacy_transition.py` loads the preserved backlog through this reader
after normal editing, completion (the operation used by approve/sync), add and follow-up.
