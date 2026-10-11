---
id: HAIFA-S08-T02
title: Limity smíšeného rosteru bez překryvu v horní liště
status: cancelled
depends_on: [HAIFA-S08-T01]
writes: [aifactory/web/, aifactory/src/aifactory/web/static/]
auto_merge: false
---

## Zadání
Finish the requested mixed-harness dashboard support by fixing limits overflow in the topbar. Manual browser verification of HAIFA-S08-T01 shows that the two provider containers remain on a single row after their parent flex container shrinks. At viewport 1366, Codex 1w is x=1313 width=99 while the theme toggle starts x=1310: controls overlap and limits extend outside the viewport. The nav itself does not overlap the parent box, so checking only parent bounding boxes misses it.

Where: aifactory/web/src/components/LimitsBar.vue (and App.vue only if necessary), related frontend tests, generated web/static assets.

Done means:
- Both Claude and Codex 5h/1w labels, percentages, progress bars, stale/unavailable states and header controls remain readable without overlapping at 1600, 1366 and 1280px desktop widths. Retain the existing small-screen behavior below 1180px; do not redesign navigation.
- Prefer a small CSS fix that wraps providers inside the available flex width and allows a provider's windows to wrap on narrower desktops. Keep all contents inside the container; avoid hiding a configured provider or clipping percentages. Preserve existing single-provider appearance where it fits.
- Verify in headless Playwright using installed Chromium (plain chromium.launch; Chrome channel is absent here). Intercept /api/limits with two-provider fixtures (including stale/unavailable) and check actual window/header-control boxes, not just the parent box. Capture screenshots for the review if useful.
- Rebuild frontend assets and run the relevant frontend checks; normal factory test phase uses just check-scoped. No backend/roster/seed/configuration changes, no unrelated tasks, no vendor/prototype/adws/.factory changes.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
