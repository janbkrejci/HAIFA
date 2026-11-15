# What is HAIFA

HAIFA (Helios AI Factory) is a local dashboard and the `factory` tool, which runs coding agents (Claude Code, Codex, pi) on backlog tasks in your Git repositories. **Search the guide** searches all chapters, with or without diacritics.

## How HAIFA works <!-- section:jak-haifa-funguje -->

1. The **Backlog** is a tree of markdown files in the repository (`factory/backlog/<project>/<step>/<task>.md`) containing task descriptions and parameters.
2. A **Run** creates a worktree and branch for a task and executes its **workflow**: agent roles (planner, builder, tester, reviewer…) and code steps (tests, commit).
3. A **Pull request** is the result. Approve it, return it with a note, or let it merge automatically.
4. **Configuration** lives in `.factory/`. Runs read it from a commit on the **base** branch (usually `main`). Items absent from the repository are inherited from the shared **library**.

A **Harness** is the CLI that runs the model (`claude`, `codex`, `pi`). The **HAIFA home directory** is `~/.config/haifa` (override with `HAIFA_HOME`).

## Security <!-- section:bezpecnost -->

- The dashboard listens on `127.0.0.1` only; `--host 0.0.0.0` exposes it to the network without authentication.
- Agents may change only the task's allowed paths in their worktree. HAIFA reverts other writes. Runs do not change `.factory/`.
- Store keys in `$HAIFA_HOME/env` (permissions `600`) or a local `.env`, never in Git.
- Your personal harness configuration is excluded from runs; `factory check` warns where a harness cannot ensure this.

## Command line <!-- section:prikazova-radka -->

Everything in the dashboard is also available through `factory`: use `factory --help` for an overview and `factory <command> --help` for details. Commands use the repository in the current directory; select another with `--repo PATH`. With `--json`, they return an `{ok, data, error, warnings}` envelope with error codes. `factory --skill` prints the agent guide. Common commands:

- `factory check`: check the machine, library and repository,
- `factory obs`: dashboard,
- `factory task list`, `factory task add STEP TITLE`: tasks,
- `factory task run ID`, `factory task retry ID`: start and resume runs,
- `factory task approve ID`, `factory task return ID --note TEXT`: approve and return tasks,
- `factory backlog commit`, `factory config commit`: commit the backlog and configuration to base.
