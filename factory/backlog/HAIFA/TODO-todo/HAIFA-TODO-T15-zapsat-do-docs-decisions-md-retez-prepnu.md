---
id: HAIFA-TODO-T15
title: Zapsat do docs/decisions.md řetěz přepnutí harnessu projektu (quota_switch) a jeho přednost
status: done
workflow: build-review
depends_on: []
related: [HAIFA-S08-T04]
writes: [docs/decisions.md]
---

## Zadání
Update the decision in docs/decisions.md. Explain the project keys quota_switch (an ordered chain of backup harnesses) and quota_switch_back (return when the limit is back), which are project-only, inherited by tasks and default to off. Precedence: a non-empty project chain wins; without one the existing fallback applies (local.yaml, then the agent's fallback in agents.yaml, then defaults.fallback), tried once. Quota state is per machine in trace.db (harness_quota, project_harness); retry_at comes from the reset time in the message, else +60 min. The return happens only when a new run starts, never mid-run, one step at a time. Switches show in retries[].harness_switch, in task_runs.harness_start for the start of a run, in run detail and in the PR body. Take the wording from factory/docs/HAIFA/S08-codex-a-prepinani-agentu/HAIFA-S08-T04-nastaveni-projektu-automaticke-prepnuti.md.

### Původ

Vznikl při běhu `1a2e0e06` tasku `HAIFA-S08-T04` (Nastavení projektu: automatické přepnutí harnessu při vyčerpání kvóty (řetěz a návrat)), v kroku `plan` (agent planner).
Důvod: HAIFA-S08-T04 replaces the decision 'Záložní harness při vyčerpané kvótě' in docs/decisions.md (repo root, line ~18). That file is outside the task's allowed paths (aifactory/, justfile, spec, doc).

<!-- factory: follow-up-of=HAIFA-S08-T04 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/98 · náklady $0.44
