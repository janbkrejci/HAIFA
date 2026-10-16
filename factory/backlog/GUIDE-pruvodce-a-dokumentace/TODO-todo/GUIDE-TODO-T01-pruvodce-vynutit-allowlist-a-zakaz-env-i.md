---
id: GUIDE-TODO-T01
title: "Průvodce: vynutit allowlist a zákaz .env i pro harness codex a pi"
status: todo
depends_on: []
related: [GUIDE-S02-T01]
---

## Zadání
In web/assistant.py, either refuse the codex and pi harnesses for the guide (with a clear harness_unavailable error and a fallback to claude), or add a real command limit for them. For codex, consider a sandbox rule that blocks reading .env files of the repos and the HAIFA home. Add a test with a fake harness for each harness.

### Původ

Vznikl při běhu `740183f7` tasku `GUIDE-S02-T01` (Backend AI průvodce: read-only konverzace nad všemi repy), v kroku `review` (agent reviewer).
Důvod: Review of GUIDE-S02-T01: only claude is limited to the ./guide command (dontAsk + allowedTools). codex runs in the read-only sandbox, which allows any read (e.g. cat <repo>/.env). pi has no limit at all and can even run factory task run. The user sees redacted output, but the agent itself can read the secret.

<!-- factory: follow-up-of=GUIDE-S02-T01 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
