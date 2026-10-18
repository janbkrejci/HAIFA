---
id: HAIFA-TODO-T16
title: "Update docs/decisions.md: the CI gate also waits for Azure DevOps"
status: done
workflow: build-review
depends_on: []
related: [HAIFA-TODO-T02]
writes: [docs/decisions.md]
---

## Zadání
In docs/decisions.md, in the item 'Approve a auto-merge čekají na CI', add in Czech: on Azure DevOps the checks are the evaluations of the PR's Build and Status policies (`az repos pr policy list`). Without them, the latest run of each pipeline at the PR's head (`az pipelines runs list --branch`) counts. Reviewer and other non-CI policies do not count. ci-fix gets the issues and log tail of the failed build tasks (build timeline/logs via `az devops invoke`).

### Původ

Vznikl při běhu `6e09fbda` tasku `HAIFA-TODO-T02` (Read CI checks on Azure DevOps (AzureProvider.checks / check_logs)), v kroku `build` (agent builder).
Důvod: In HAIFA-TODO-T02 AzureProvider started reporting checks (reports_checks=True), so approve and auto-merge with git_provider azure now wait for Azure Pipelines and policies, and ci-fix gets the build logs. docs/decisions.md (the 'Approve a auto-merge čekají na CI' item) describes only GitHub, and docs/ was outside this task's allowed paths.

<!-- factory: follow-up-of=HAIFA-TODO-T02 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/110 · náklady $0.30
