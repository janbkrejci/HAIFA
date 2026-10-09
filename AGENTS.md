# HAIFA development

Python source: `aifactory/src/aifactory/`. Tests: `aifactory/tests/`. Vue frontend: `aifactory/web/`.

Use Python 3.11+, uv, Bun and just. Run `just check` and `just e2e` for implementation changes; `just web-build` updates the shipped static frontend. Keep tests independent of live models and services. `vendor/sssf` is a read-only third-party snapshot used by regression tests. Preserve THIRD_PARTY_NOTICES.

Never commit credentials, runtime databases, agent transcripts or local machine configuration.
