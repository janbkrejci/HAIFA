# Library and team

Only Git is shared: repository configuration and backlogs, and the library in its own repository. Machine settings, trace DB and keys stay local.

## Library <!-- section:knihovna -->

The library is a Git repository at `$HAIFA_HOME/library` with `agents/`, `workflows/`, `skills/` and `extensions/` directories. A repository looks up items in its own `.factory/`, then the library, then the HAIFA seed.

The **Library** page (library chip) has **Library contents**, **Machine check** and **Dashboard** (port) sections. Library contents offers **Synchronization** (**Pull**, **Send as PR**, open PRs), **Restore default agents and workflows**, **Import…**, and an item browser with version history and **Repositories with their own copy**: **Diff**, **Move repository copy to library** and **Delete repository copy**. Moving and deleting copies are available only here (CLI: `factory config move`, `factory config remove`).

## Changes through pull requests only <!-- section:zmeny-jen-pres-pull-request -->

Nothing is pushed directly to the library's `main`. HAIFA commits every write locally (`factory library push`, `factory library seed`, import, moving a copy) and sends a PR: administrators use a branch in the library repository, others their fork. HAIFA never merges or approves library PRs. Changes apply locally immediately; after merge, pull them (`factory library pull`). Check status with `factory library status --fetch`.

Administrators should configure a ruleset on `main`: require PRs with Code Owners approval and forbid force push.

## Seed <!-- section:seminko -->

The seed contains default agents, pi extensions and the `factory` skill. Installation and updates run `factory library seed --all`, replacing seed items in the library; customizations therefore belong in the repository's `.factory/`. Manual `factory library seed` preserves modified items (use `--take` to replace them). Require a newer HAIFA with `min_factory_version` in `library.yaml`.

## New team member <!-- section:novy-clen-tymu -->

1. Install HAIFA; the installer clones the default library (select another with `factory library clone <URL>`).
2. Clone team repositories and run `factory check` in each. State `installed` is sufficient; do not run `factory init`.
3. Add the repositories in the dashboard.

The first team member creates the library: `factory library init --name "Team library" --remote <empty-repository-URL>`. Install HAIFA in a repository that lacks it with `factory init --dry-run`, then `factory init --commit --expect <digest>`.

## Concurrent work <!-- section:soubezna-prace -->

Run state is known only to the machine running it; everyone sees open PRs. A shared database server (`just shared-db`, address in `HAIFA_DATABASE_URL`) provides a shared overview without authentication, for trusted networks only.
