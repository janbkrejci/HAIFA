# Repository configuration, agents and workflows

Configuration lives in the repository's `.factory/`: `config.yaml`, `agents.yaml` (agent roster), optional `roles.yaml`, `workflows/` and `prompts/<agent>/`. `local.yaml` (trace DB, `database_url`), `trace.db` and `worktrees/` stay outside Git. Missing items are inherited from the library.

**Runs read shared configuration from a commit on base.** Commit changes using the **Uncommitted configuration** icon or `factory config commit` (`--pr` for protected base). `factory config show` shows run configuration.

## config.yaml <!-- section:config-yaml -->

| Key | Default | Meaning |
| --- | --- | --- |
| `base`, `remote` | `main`, `origin` | Target branch and remote. |
| `git_provider` | `local` | `local`, `github` (`gh`), `azure` (`az`, `azure` section). |
| `merge_strategy` | `squash` | `squash` or `merge`. |
| `github_approver` | — | Another `gh` account that submits an approval review. |
| `base_changes` | `direct` | `pr`: factory sends every base change as a pull request. |
| `base_pr_merge` | `manual` | `auto`: factory immediately approves and merges these PRs. |
| `docs_root` | `factory` | Root for `backlog/`, `specs/`, `docs/`. |
| `protected_files` | `[".factory/"]` | Paths agents cannot change. |
| `max_parallel_runs` | `1` | Slots for concurrent tasks. |
| `stacked_prs` | `false` | Stack PRs on dependency PRs. |
| `test_timeout`, `test_slots` | 600, `0` | Test timeout; `0` allows unlimited concurrent tests on the machine, a positive value enables a shared queue. |

Other keys: `levels`, `workdir`, `worktrees_dir`, `generated`.

## Factory tab <!-- section:zalozka-factory -->

- **Repository status**, **Install factory**, **Pull configuration from base**, and **Next steps** after installation.
- **Check summary** and repository findings; an agent can **Resolve selected findings**.
- **Repository settings:** **Shared repository settings** (including **Base changes**, **Factory pull request merging**, **Stacked pull requests**) and **Local uncommitted settings** (trace DB). **Save** writes to the working tree.
- **Agent settings:** agents' harness, model and thinking, **inherited** or **overridden**; **Edit** and **Reset to inherited**.
- **Lessons**: **Find lessons** (`factory learn scan`) groups repeated run feedback; **From all repositories** (`--all`) includes all repositories. Lessons are saved in the relevant repository (factory lessons in HAIFA); the message links to that repository's Lessons section.

## Agents and harnesses <!-- section:agenti-a-harness -->

Default agents: planner, scout, builder, tester, test-reviewer, reviewer, documenter. An agent has `harness` (always explicit), `model`, `thinking` and `writes`. Switch the whole roster with `factory config roster set claude` (or `codex`).

Harness and model precedence, lowest to highest: repository roster, machine defaults (**Harnesses on this machine** dialog), task (or its step and project), choice for one run, workflow step override.

## Workflows <!-- section:workflow -->

| Workflow | Purpose |
| --- | --- |
| `build`, `build-test` | Implement without tests, or until tests pass. |
| `build-review` | Implement and review (documentation). |
| `build-test-review` | Implement, test, review; precise tasks. |
| `plan`, `plan-build`, `plan-build-test` | Plan, optionally implement and test. |
| `plan-build-test-quality` | Also lint, types and tests for the whole repository. |
| `simple-sdlc` | Plan through documentation; large or vague tasks. |
| `scout`, `quality`, `document`, `heal` | Explore, check repository, document, repair suite. |
| `resolve`, `resolve-reviewed` | Resolve PR conflicts with base. |
| `ci-fix` | Repair failing CI in the same PR. |

For a small precise change use `build-test-review`; for a large one use `simple-sdlc` or start with `plan`. **Suggest workflow** can help. Custom workflows: [Workflow author appendix](#/guide/autori-workflow).
