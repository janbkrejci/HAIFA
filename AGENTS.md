# HAIFA development

Python source: `aifactory/src/aifactory/`. Tests: `aifactory/tests/`. Vue frontend: `aifactory/web/`.

Use Python 3.11+, uv, Bun and just. `just web-build` updates the shipped static frontend. Keep tests independent of live models and services. Preserve THIRD_PARTY_NOTICES.

Before a task or follow-up runs, list any required paths outside its inherited `writes` (such as `docs/decisions.md` or `aifactory/web/src/`) in its own `writes`.

The whole suite takes about 30 minutes on Windows. CI runs it on every pull request (`.github/workflows/ci.yml`) and auto-merge waits for it. A factory task run checks only what the change can affect, inside its test step's time limit:

- `just lint` and `just typecheck`, always.
- `just pytest <files or directories>` with the tests of the changed packages and of their direct callers. `aifactory/tests/<package>/` mirrors `aifactory/src/aifactory/<package>/`. Never the whole suite.
- `just web-test` when `aifactory/web/` changed, and `just pytest tests/e2e/<file> -n0` only for the browser test of a changed screen.

Measured on the Windows factory machine (set check timeouts with margin): `just lint` 1 s, `just typecheck` 10 s, `just web-test` 90 s (bun install, vue-tsc, vitest), one browser test file 60–200 s, `just pytest` of one test directory 1–5 min.

Outside a factory run, `just check` and `just e2e` are the full gate.

Never commit credentials, runtime databases, agent transcripts or local machine configuration.
