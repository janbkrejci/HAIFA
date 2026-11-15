# What is GIRO

Goal in. Release out.

GIRO is a local dashboard and the `giro` tool, which runs coding agents (Claude Code, Codex, pi) on backlog tasks in your Git repositories. **Search the guide** searches all chapters, with or without diacritics.

## How GIRO works <!-- section:jak-haifa-funguje -->

1. The **Backlog** is a tree of markdown files in the repository (`factory/backlog/<project>/<step>/<task>.md`) containing task descriptions and parameters.
2. A **Run** creates a worktree and branch for a task and executes its **workflow**: agent roles (planner, builder, tester, reviewer…) and code steps (tests, commit).
3. A **Pull request** is the result. Approve it, return it with a note, or let it merge automatically.
4. **Configuration** lives in `.factory/`. Runs read it from a commit on the **base** branch (usually `main`). Items absent from the repository are inherited from the shared **library**.

A **Harness** is the CLI that runs the model (`claude`, `codex`, `pi`). The **GIRO home directory** is `~/.config/giro` (override with `GIRO_HOME`).

## Security <!-- section:bezpecnost -->

- The dashboard listens on `127.0.0.1` only; `--host 0.0.0.0` exposes it to the network without authentication.
- Agents may change only the task's allowed paths in their worktree. GIRO reverts other writes. Runs do not change `.factory/`.
- Store keys in `$GIRO_HOME/env` (permissions `600`) or a local `.env`, never in Git.
- Your personal harness configuration is excluded from runs; `giro check` warns where a harness cannot ensure this.

## Command line <!-- section:prikazova-radka -->

Everything in the dashboard is also available through `giro`: use `giro --help` for an overview and `giro <command> --help` for details. Commands use the repository in the current directory; select another with `--repo PATH`. With `--json`, they return an `{ok, data, error, warnings}` envelope with error codes. `giro --skill` prints the agent guide. Common commands:

- `giro check`: check the machine, library and repository,
- `giro obs`: dashboard,
- `giro task list`, `giro task add STEP TITLE`: tasks,
- `giro task run ID`, `giro task retry ID`: start and resume runs,
- `giro task approve ID`, `giro task return ID --note TEXT`: approve and return tasks,
- `giro backlog commit`, `giro config commit`: commit the backlog and configuration to base.
