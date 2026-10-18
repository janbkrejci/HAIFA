# HAIFA-S90-T04: OB4 Azure DevOps proti skutečnému repu — plan

## Goal

1. Add `--remote azure` to `just validate` (`aifactory/validation/`), modelled on `--remote github`.
2. Run `just validate --remote azure --only R2,RESOLVE,R3,F2` against the sandbox
   `https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox`. Keep the results in
   `aifactory/validation/results/<date>/azure-<time>/`.
3. Fix every way real `az` behaves differently from the fake in `providers/azure.py`.
   Mirror each fix in `tests/providers/az_fake.py` and `tests/providers/test_providers_azure.py`.
4. Document the azure mode in `aifactory/validation/README.md`.

Allowed paths: `aifactory/src/aifactory/providers/azure.py`, `aifactory/tests/providers/`,
`aifactory/validation/` (including `template/`), `aifactory/tests/validation/`, `justfile`,
this spec, and the task doc
`factory/docs/HAIFA/S90-otevrene-body/HAIFA-S90-T04-ob4-azure-devops-proti-skutecnemu-repu.md`.
Do not touch `docs/decisions.md` or anything under `src/` other than `providers/azure.py`.
If a fix needs another file (`review/flow.py`, `config/settings.py`, …), record it as a
follow-up and do not edit that file.

## Facts verified by the planner (read-only, on this machine)

- `az` 2.91.0 with `azure-devops` 1.0.9 is logged in.
- `az repos show --org https://asolcz.visualstudio.com --project NEO_HEF --repository HAIFA-Azure-Sandbox --detect false -o json`
  works. It returns `defaultBranch: refs/heads/main`,
  `remoteUrl: https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox` and
  `webUrl` (same URL).
- **Git over HTTPS has no stored credentials.** `git ls-remote <remoteUrl>` fails with
  "could not read Username". SSH fails with "Host key verification failed". What works is a
  credential helper that hands git the `az` access token (the Azure DevOps resource id is
  `499b84ac-1321-427f-aa17-267ca6975798`). Basic auth with any username works:
  ```
  git -c credential.helper= -c 'credential.helper=!f() { test "$1" = get || exit 0; echo username=haifa; echo password=$(az account get-access-token --resource 499b84ac-1321-427f-aa17-267ca6975798 --query accessToken -o tsv); }; f' ls-remote https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox
  ```
  The token lasts about 1 hour. A helper fetches a fresh one for every git call, so a run of
  several hours still works. Do not put a fixed `http.extraHeader` in the config.
- The sandbox today has `main` and `factory/LAB-S01-T01-1`, plus PR 30090 (completed). They
  come from an earlier manual lifecycle check.
- Real `az repos pr show --id 30090` output, compared with `az_fake.pr_json`:
  - `repository.webUrl` is **null**. The fake sets `WEB_URL`. So `_pr_url` always falls back
    to `organization_url/<project>/_git/<repo>/pullrequest/<id>`.
  - `closedDate` / `creationDate` look like `2026-10-06T15:19:37.209982+00:00` (6 fraction
    digits and an offset). The fake uses `…4513593Z`.
  - `lastMergeCommit`, `lastMergeSourceCommit` and `lastMergeTargetCommit` are objects with
    `commitId` (as the fake has them). `mergeStatus` and `status` are lowercase strings.
    `mergeFailureMessage` and `mergeFailureType` exist and are null. `completionOptions` and
    `completionQueueTime` exist.
  - `url` is the REST url (`…/_apis/git/repositories/<guid>/pullRequests/<id>`), not a web URL.
- `az repos pr list … --status completed` also returns `repository.webUrl: null`.
- A missing PR gives exit 1 with stderr `ERROR: TF401180: The requested pull request was not found.`
- `az repos pr policy list --id 30090` returns a non-empty list (main has branch policies).
  The validation's base `haifa-validate/<stamp>` should have none. Check this live.

## Part A — `--remote azure` in the validation

### A1. `validation/sandbox.py`

- Extend the `Sandbox` dataclass with `azure: AzureRepo | None = None`, a new frozen
  dataclass `AzureRepo(organization_url: str, project: str, repository: str)` with a
  `web_url` property (`f"{organization_url}/{quote(project)}/_git/{quote(repository)}"`).
  Update the docstrings: `remote: str  # local | github | azure`. Update the module
  docstring so it also covers azure. Nothing outside the workdir is written except the
  sandbox's new base branch and the `factory/*` / `factory-sync/*` branches and PRs.
- `AZURE_SANDBOX_ENV = "HAIFA_AZURE_SANDBOX_REPO"`. `normalize_azure_repo(value) -> AzureRepo`
  raises `SetupError` when the value is empty or invalid. It accepts:
  - `https://<org>.visualstudio.com/<project>/_git/<repo>` → org url `https://<org>.visualstudio.com`;
  - `https://dev.azure.com/<org>/<project>/_git/<repo>` → org url `https://dev.azure.com/<org>`;
  - an optional `user@` prefix in either URL (Azure's clone URLs carry `org@`);
  - `<org>/<project>/<repo>` → `https://dev.azure.com/<org>`.
  `urllib.parse.unquote` project and repo (`%20`). The error message names
  `HAIFA_AZURE_SANDBOX_REPO` and the accepted forms. Do not touch `normalize_repo` (GitHub).
- `az_executable()` → `os.environ.get("AIFACTORY_AZ") or "az"`, the same variable the
  provider reads. `az(cwd, *args, check=True) -> str`, like `gh()`.
- `AZURE_DEVOPS_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"`. `azure_credential_helper()`
  returns the `!f() { … }; f` string above. If `$AZURE_DEVOPS_EXT_PAT` is set, the helper
  prints that instead of calling az. Implement this in the shell (`${AZURE_DEVOPS_EXT_PAT:-$(az …)}`),
  with az called through `az_executable()`, shell-quoted with `shlex.quote`. The token never
  lands in a file.
- `git_auth_args() -> list[str]` = `["-c", "credential.helper=", "-c", f"credential.helper={helper}"]`
  (the empty value resets the global osxkeychain helper, so the token is never stored there).
- `setup_azure(workdir, target: AzureRepo, when, roster) -> Sandbox`, a mirror of `setup_github`:
  1. `az repos show --org … --project … --repository … --detect false --output json --only-show-errors`
     → `remoteUrl` and `defaultBranch` (SetupError on failure).
  2. `git <auth args> clone -q <remoteUrl> <workdir>/repo`.
  3. In the clone: `git config credential.helper ""` then
     `git config --add credential.helper <helper>`. This is repo-local config, which every
     worktree HAIFA creates shares, so HAIFA's own push/fetch authenticate as well.
  4. Base `haifa-validate/<stamp>` from `origin/HEAD` (fallback: `HEAD`). Set
     `commit.gpgsign false`, run `_exclude_hidden`, then
     `materialize(repo, base, "azure", azure=target)`, `_apply_roster`, `commit_all` and
     `push -u origin base`. Also fetch `factory/*`, exactly as github does.
  5. Return `Sandbox("azure", repo, base, url, azure=target)`.
  The default branch of the sandbox is never pushed. Only `task resolve` force-pushes, and
  only a `factory/*` branch.
- `materialize(dest, base, provider, azure: AzureRepo | None = None)`: render the template
  with one more variable `$provider_settings`. It is empty for local and github. For azure it
  is the YAML block below, with values quoted through `json.dumps` (valid YAML scalars):
  ```
  azure:
    organization: "<organization_url>"
    project: "<project>"
    repository: "<repository>"
  ```

### A2. `validation/template/.factory/config.yaml.tmpl`

Append the line `$provider_settings` at the end. Keep the file ending in a newline.
`tests/validation/test_validation_template.py` must still pass. If it compares the rendered
config text exactly, update the expectation.

### A3. `validation/runner.py`

- `--remote` choices become `("local", "github", "azure")`. Update the help text for azure:
  "the HAIFA_AZURE_SANDBOX_REPO sandbox on Azure DevOps with the real harnesses". Update the
  parser description and the justfile comment (`just validate --remote local|github|azure [--roster DIR]`).
- Move the shared part of `preflight_github` (the `just` check and the harness check through
  `_worker_json`) into a helper `_preflight_common(roster)`.
- `preflight_azure(value, roster) -> AzureRepo`:
  1. `normalize_azure_repo(value)` runs first, before any subprocess, as github does.
  2. Check `just`.
  3. `az --version`, `az extension show --name azure-devops --output json`, and
     `az account show --output json` (skip the login check when `AZURE_DEVOPS_EXT_PAT` is set).
     Each failure is a `SetupError` with the provider's hint texts (az missing, extension
     missing, `az login`).
  4. `az repos show …` succeeds: the sandbox exists and is reachable.
  5. `git <auth args> ls-remote --heads <remoteUrl>` exits 0: git can authenticate.
  6. The harness check (`_preflight_common`).
- `main`: choose by `args.remote`. Keep the target as `target: str | AzureRepo | None` or use
  two variables. Keep mypy strict clean. `_run` calls `setup_azure` for azure.
- `summary["sandbox_repo"]`: `sandbox.github_repo or (sandbox.azure.web_url if sandbox.azure else None) or sandbox.remote_url`.
- Exit-code docs (2): add "missing `HAIFA_AZURE_SANDBOX_REPO`, failed `az` check".

### A4. `validation/context.py`

- Add a `hosting` property: `"local" | "github" | "azure"` (= `self.remote`). Keep `local`.
- `az(*args, check=True) -> str` runs `sandbox.az(self.repo, *args, …)`.
- `az_repo_args()` → `["--org", url, "--project", p, "--repository", r]`. `az_tail()` →
  `["--detect", "false", "--output", "json", "--only-show-errors"]`.
- Update the module docstring: in `--remote github` and `--remote azure` only `fake=True`
  commands are faked.

### A5. `validation/scenarios.py` (R2, RESOLVE, R3) and `validation/f2.py`

Every `if ctx.local … else <github>` branch must work on azure as well:

- `_pr_number`: azure → `az repos pr list <repo args> --source-branch <branch> --status all --top 1 <tail>`.
  Take `pullRequestId` of the first entry (the newest). The R3 check `pr_updated` compares the
  numbers before and after the return. Check live which order `--status all` returns, and filter
  `--target-branch ctx.base`.
- `_merge_outside`: azure →
  `az repos pr update --id N --org … --status completed --squash true --delete-source-branch false --merge-commit-message "Merge … outside factory" <tail>`.
  Completion is asynchronous. Poll `az repos pr show --id N` (up to about 60 s, every 5 s)
  until `status == completed`. If the PR does not complete, raise `RuntimeError` so the
  scenario fails visibly. Observation: `merge mimo factory: az repos pr update --id N --status completed --squash true`.
- `_close_outside`: azure → `az repos pr update --id N --org … --status abandoned <tail>`.
  Observation `zavření PR mimo factory: az repos pr update --id N --status abandoned`.
- R2 `_r2_approve`: the `not ctx.local` paths (`merge_failed` accepted as conflict) apply to
  azure too. Make the observation hosting-neutral ("hosting ještě nespočítal mergeability …").
- RESOLVE and F2 `_approve` retry on `merge_failed` (6×10 s) already cover non-local. Keep them.
- F2 `res.observe("just test v čistém checkoutu base se na githubu nespouští")` → say
  "na hostingu (github, azure)". Do the same for other github-only Czech texts you touch
  (`"squash se ověřuje na githubu"` → "na hostingu").
- R3 `_r3_finish` non-local observation: github keeps the D11 text. For azure, observe what
  actually happened: Azure lets you vote on your own PR, so `provider.approve` votes
  (`set-vote approve`). Verify this live with `az repos pr reviewer list --id N` after an
  approve, and record the result in the observation.

**R3 must pass without R1 and R10 in `--only`.** Today R3 takes the PR of R10 (approval in
the factory) and the PR of R1 (merge outside factory) from `ctx.state`. With
`--only R2,RESOLVE,R3,F2` both are missing, `st.missing` fills and R3 comes out
`inconclusive`. Fix it in the validation:

- `Context` gets `selected: list[str]`. `runner.make_context` gets the selected names (an
  extra parameter with default `()`). `run_scenarios` sets it before the first scenario.
- A new first R3 stage `("prerequisites", _r3_prerequisites)`. For R10 and for R1: if the
  scenario is **not selected** (so not merely failed) and its key is not in `ctx.state`,
  run `ctx.run_task(<task>)` and reference it. If the run succeeds and has a PR URL, store
  `ctx.state["R10"|"R1"] = {"task", "run", "pr"}` in the same shape `r1`/`r10` use. Add the
  observation `R3: předpoklad <task> (jinak z R10/R1) spuštěn v R3`.
  - Order: R10_TASK first (slugify, needed by the dependency check that comes next only
    through its status; R10's run does not change base). Then R1_TASK.
  - `_r3_dependency` still runs after it. A not-done slugify still blocks R4_TASK.
- A failed prerequisite run adds a failed check `prerequisite_<task>` with `cmd.brief()`, so
  it is not hidden as inconclusive.
- Update the README sentence about missing prerequisites. The R3 row then says R3 creates the
  R1/R10 PRs itself when those scenarios are not selected. Also update the cost section: the
  `--only R2,RESOLVE,R3,F2` run has 2 + 1 + 3 (+ return) + 5 runs.

### A6. `justfile`

Change only the comment above `validate`.

### A7. Tests (`aifactory/tests/validation/`)

No live service in any test.

- `test_validation_unit.py`:
  - parametrized `normalize_azure_repo` accept and reject cases (visualstudio URL, dev.azure
    URL with `org@`, `org/project/repo`, `%20` in project, garbage, empty);
  - `--remote azure` without `HAIFA_AZURE_SANDBOX_REPO` returns exit 2 before any subprocess,
    with no results or workdir created (copy the github test);
  - `git_auth_args` resets the helper first, and the helper contains the resource id and no
    token.
- `test_validation_template.py` (or unit): `materialize(..., "azure", azure=AzureRepo(...))`
  renders a `config.yaml` that `aifactory.config` loads with `git_provider: azure` and the
  right `azure` settings. local and github render no `azure:` key.
- An R3 prerequisite unit test with a stub `Context` (monkeypatch `run_task`):
  - R1/R10 not selected → both task runs are called and `ctx.state` filled;
  - selected but failed → not called.
- `local_validation.py` `HIDDEN_ENV_KEYS` and `test_validation_prompt_paths.py`: add
  `HAIFA_AZURE_SANDBOX_REPO` next to `HAIFA_SANDBOX_REPO`.
- A `preflight_azure` test with a fake `az` on PATH. You can reuse
  `tests/providers/az_fake.write_fake_az`. If importing across test packages is awkward, a
  tiny inline fake executable is fine. Cover these cases: az not logged in → SetupError
  mentioning `az login`, and `az repos show` fails → SetupError. Stub the git ls-remote and
  harness check (monkeypatch).

## Part B — the live run and the provider fixes

### B1. Run

Run from the worktree, not the main checkout:
```
export HAIFA_AZURE_SANDBOX_REPO=https://asolcz.visualstudio.com/NEO_HEF/_git/HAIFA-Azure-Sandbox
just validate --remote azure --only R2,RESOLVE,R3,F2 --keep-workdir
```
- It runs real harnesses from the template roster (claude, codex, pi). A GitHub run of all
  scenarios took about 70 minutes, and this subset is a bit shorter. Start it in the
  background and watch it. Don't poll in tight loops.
- Before you start, run `factory harness check` (the preflight does too). If a harness from
  the default roster is missing on this Mac, use `--roster aifactory/validation/rosters/<x>`
  with harnesses that exist, and note this in the task doc.
- Exit 0 with R2, R3 and F2 `passed` (RESOLVE `passed` too, since R3 and the cleanup need it)
  is the target. `inconclusive` from a real model skipping the forced review round is
  acceptable only where the README already allows it (review approved in round 1). In that
  case, re-run.

### B2. Diagnose each failure, then fix

For each failure, read `results/…/azure-*/logs/*.log`, the scenario JSON and, if needed,
`az repos pr show --id N` live. Classify it:
- a **provider difference** → fix `providers/azure.py`, mirror it in `az_fake.py`
  (`pr_json` defaults etc.), and add or adjust a test in `test_providers_azure.py`;
- a **validation bug** → fix it in `validation/`;
- a bug outside the allowed paths → a follow-up (tell the reviewer). Never edit it.

Likely differences to verify (hypotheses, confirm each one live before you change code):
1. `repository.webUrl` is null → `_pr_url` uses the fallback. `organization` in the sandbox
   config is the full `https://asolcz.visualstudio.com`. Check that the fallback URL opens
   the PR. Make the fake's `pr_json` default `repository.webUrl` null (as real), and keep one
   test that covers a present `webUrl`. Fix the tests that assert URLs.
2. Timestamps with `+00:00` and 6 digits: change the fake's `closedDate` to the real form, and
   check that `merged_at` is still normalized (a test exists in `test_utc_iso.py`; add the
   real sample).
3. `mergeStatus` right after a push is `queued` or `notSet` for longer than
   `UNKNOWN_ATTEMPTS × UNKNOWN_DELAY` (10 s). The same goes for `lastMergeSourceCommit`
   catching up in `_fresh_head` after the done commit is pushed (approve fails with
   `approve_failed … head changed`). If this happens, raise the bounded wait, for example
   attempts 10 × 3 s or a time budget. Keep the constructor parameters so the tests stay fast.
4. `pr update --status completed` returns `status: active` with `completionQueueTime` while
   Azure completes asynchronously. `_await_completion` gives up after 5 × 2 s with
   `merge_failed`. Measure the real completion time and size the poll for it.
5. A completed PR that had conflicts: the real result may be `mergeStatus: conflicts` with
   `status: active` after the update, or an az error such as
   `TF401181`/`TF401179`/"merge conflicts". R2 expects `conflict` (or `merge_failed`) with
   exit 2 and base unchanged. Map real error texts or codes to `conflict` where the PR has
   conflicts. Put the real stderr into the fake response in a test.
6. Errors: `ERROR: TF401180 …` (not found) and `TF400813` (not authorized). Make sure
   `AzError` classification matches real stderr. Add tests with the real texts.
7. `set-vote` on your own PR: check that it works. If Azure refuses it (policy), record the
   real stderr and decide with the reviewer. Approve must not break merge
   (`approve_failed`) where the GitHub provider would skip review (D11). Changing D11 is out
   of scope, so report it as a follow-up and do not edit `review/`.
8. `az repos pr list --source-branch factory/x` without the `refs/heads/` prefix: check that
   `find_open_pr` finds the PR. If not, pass `refs/heads/<branch>`.
9. `abandoned` → `CLOSED` and approve → `pr_not_open`. Check it in R3.
10. Checks: base `haifa-validate/*` has no policies → `policy list` returns `[]` → falls back
    to `az pipelines runs list --branch refs/heads/<branch> --project NEO_HEF`. Check that
    this does not fail (permissions or a project without pipelines) and that an empty list
    gives `none`.

Every fix in `azure.py` must keep the existing tests green or update them deliberately. The
module docstring (the "Commands used" list) must describe the real behaviour, for example the
`webUrl` fallback and the async completion wait. Remove the docstring's last paragraph about
"the operator verifies … see the task's app_docs guide" and point to `just validate --remote azure`.

Re-run the validation after the fixes. The final `azure-*` result directory with R2, R3 and
F2 passed is the one that stays. Delete earlier failed `azure-*` result directories of this
task before you finish (they are committed otherwise). `trace/` and `logs/` are gitignored.
The JSONs and `summary.json` are committed.

### B3. Cleanup on Azure after each run (do it yourself, then document it)

- List active PRs:
  `az repos pr list --org https://asolcz.visualstudio.com --project NEO_HEF --repository HAIFA-Azure-Sandbox --status active --detect false -o table`.
  Abandon the leftovers of this run (sync PRs `factory-sync/*` targeting `haifa-validate/*`,
  anything targeting the run's base) with `az repos pr update --id N --status abandoned`.
  Never touch PRs that target `main` or that were not created by this run.
- Delete the run's branches with git (the clone has the credential helper):
  `git -C <workdir>/repo push origin --delete haifa-validate/<stamp> factory/<…> factory-sync/<…>`.
  Find them with `git ls-remote --heads origin 'factory/*' 'factory-sync/*' 'haifa-validate/*'`.
  Alternatively, `az repos ref delete --name heads/<branch> --object-id <sha> --org … --project NEO_HEF --repository HAIFA-Azure-Sandbox`.
- Delete the `--keep-workdir` workdir afterwards.
- The `main` of the sandbox must be at the same sha as before (`ac49e7b9…` at planning time;
  record it before the run).

## Part C — documentation

- `aifactory/validation/README.md` (Czech):
  - add `just validate --remote azure` to the command block;
  - add "**azure**" to "Režimy": it needs `HAIFA_AZURE_SANDBOX_REPO` (accepted forms),
    `az` with the `azure-devops` extension, logged in (`az login --allow-no-subscriptions`) or
    `AZURE_DEVOPS_EXT_PAT`, optionally `AIFACTORY_AZ`, the roster harnesses and `just`;
  - explain git authentication (the repo-local credential helper with the az token; nothing
    stored in the keychain);
  - say that the base branch comes from the default branch, which never changes, and that
    merge outside factory and closing a PR go through `az repos pr update`;
  - update the exit code 2 list;
  - add a cleanup subsection for Azure with the B3 commands. Generalise the cost section
    ("na hostingu"), and update the R3 table row and the prerequisite sentence (A5).
- Update `validation/__init__.py` docstring with the azure mode.
- The task doc `factory/docs/HAIFA/S90-otevrene-body/HAIFA-S90-T04-…md` belongs to the
  documenter. The builder may leave it alone. Give the documenter the list of real-vs-fake
  differences found and fixed (in the envelope notes) so it lands there.

## Verification

- `just lint`, `just typecheck`.
- `just pytest tests/providers tests/validation/test_validation_unit.py tests/validation/test_validation_template.py`
  and any other `tests/validation/` files you changed (the slow `test_validation_local.py`
  once at the end, since scenarios.py changed; `-n auto` is fine).
- The live run as in B1: a results dir `aifactory/validation/results/<date>/azure-<HHMMSS>/`
  with `R2.json`, `RESOLVE.json`, `R3.json` and `F2.json`, R2, R3 and F2 `passed`, plus `summary.json`.
- The sandbox `main` sha is unchanged, and the cleanup is done.
