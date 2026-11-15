# Updates and troubleshooting

## Updates <!-- section:aktualizace -->

The dashboard checks releases every half hour. The **Update available** icon verifies and installs the update and restarts the dashboard. **Update waiting for tasks**: click again when tasks finish.

CLI (file/`https`):

```bash
giro upgrade --dry-run giro-<version>.zip
giro upgrade giro-<version>.zip
```

`giro upgrade` verifies `SHA256SUMS`, installs a newer version and refreshes the library (`giro library seed`, [Library and team](#/guide/knihovna-a-tym/seminko)). Restart the dashboard; on Windows, stop it first (`dashboard_running`).

Build a release with `just bundle`.

## Troubleshooting <!-- section:reseni-problemu -->

The blue **System info** chip shows free disk space and memory in GB, refreshed every minute. **Clean up disk** removes orphaned proposals, completed worktrees and branches of merged PRs across repositories; the tooltip shows the result.

Find problems with `giro check` (read-only):

```bash
giro check            # machine and library; also repository when inside one
giro check --offline  # skip hosting and sign-in queries
giro check --json     # machine-readable output
```

Findings: `error` blocks, `warning` warns, `info` informs; `fix` gives advice. Find them in **Library** (machine, library), **GIRO** (repository) and **Problems and solutions**.

## Common situations <!-- section:caste-situace -->

**A `.factory/` or backlog change did not affect a run.** Runs read base. Commit using **Uncommitted configuration**, **Uncommitted backlog** (`giro config commit`, `giro backlog commit`).

**A task cannot start.** Set a workflow; check dependencies and human assignment.

**A harness is missing or signed out.** Sign in (`claude`, `codex login`, `pi auth login`), run **Test** in **Harnesses on this machine**, or use `giro config roster set`.

**A run failed or stalled.** Inspect events. Stop the run, then **Continue** (`giro task retry ID`).

**A PR stayed open after approval.** Fix CI, conflicts or dependencies in PR details; approve again.

**The library is behind or diverged from remote.** Use `giro library pull`; resolve `library_diverged` in the library.

Include `giro check --json` and `giro --version` when reporting problems.

## Importing legacy automation choices <!-- section:prevzeti-starych-voleb-automatizace -->

After installation, restart any running dashboard (`giro obs`). Older machines use front matter; upgraded machines use local choices in GIRO_HOME: without a saved choice, automations are off and the harness is inherited from the machine.

Inspect and import legacy choices with:

```sh
giro config local legacy --repo PATH --json
giro config local import --repo PATH --json
```

The preview shows values and origins through project, step and task. Uniform values can be imported directly; conflicts require repository-wide choices, for example `--auto-merge off --auto-continue on --harness codex`. Model/thinking are not imported; the harness uses local settings. Existing local choices are overwritten only with explicit `--overwrite`. Import is atomic, idempotent and writes only to GIRO_HOME; another GIRO_HOME has separate choices, while worktrees share them.

Reads, upgrades and Git pulls do not change local choices. Preserve legacy fields for older machines; editing, approval and sync retain them. Transition needs no commit or minimum-version barrier; field removal is a separate step. Legacy `backlog auto-continue`, `backlog auto-merge` and `task edit --auto-merge` return deprecation errors; use `giro config local set --auto-continue on|off` or `--auto-merge on|off`.
