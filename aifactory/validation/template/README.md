# HAIFA validation sandbox

A tiny standard-library Python package that `just validate` (aifactory,
task 2.17) creates for every validation run. The backlog in
`backlog/` has 2 projects, 3 steps and 7 small tasks; each one is a few dozen
lines, so a run with real models stays cheap.

- `just test` runs the suite. Tests of a function a task has not added yet are
  skipped, so the base is always green.
- `.factory/` holds the HAIFA configuration, the agent roster and the
  `simple-sdlc` workflow with explicit harnesses (plan on claude, build and
  fix on codex, review on pi).

Generated; do not edit by hand in the sandbox repo.
