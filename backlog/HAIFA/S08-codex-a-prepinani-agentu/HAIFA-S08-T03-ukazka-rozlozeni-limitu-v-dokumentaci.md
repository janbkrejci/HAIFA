---
id: HAIFA-S08-T03
title: Ukázka rozložení limitů v dokumentaci
status: done
workflow: build-test-review
depends_on: [HAIFA-S08-T01]
writes: [app_docs/]
auto_merge: false
---

## Zadání
Add the missing UI review screenshot for the completed Codex dashboard change. Copy the operator's existing PNG C:/Users/jan.krejci/AppData/Local/Temp/haifa-codex-stacked-71d8cf53.png byte-for-byte to app_docs/images/HAIFA-S08-T01-limits.png. It is the verified Claude-above-Codex topbar at1366px, showing SAMPLE limit values (not live account usage). Append a concise relative Markdown image and caption clearly stating sample data to app_docs/HAIFA-S08-T01-codex-roster-a-zive-limity.md. Preserve all existing guide contents and implementation. Do not edit AGENTS.md, code, workflows, config, or protected paths, do not modify or regenerate the image, and do not run nested factory tasks. This is documentation-only; git diff --check is the appropriate check, no implementation-mirroring tests or frontend build. Claim only the image and the existing guide. The operator will include the public image in UI PR63's description after merge.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/65 · náklady $0.00
