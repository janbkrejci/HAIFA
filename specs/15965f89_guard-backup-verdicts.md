# Plan: guard backup of the main checkout, absolute handoff dir in prompts, R1/R10 verdicts

Fixes three findings of the GitHub validation with the `claude-haiku` roster (run `github-185807`):

- **V7:** in R4 an agent reverted uncommitted work in the main checkout. The guard reported
  `REVERTED-BY-AGENT (uncommitted work lost, cannot restore)`.
- **V6:** in R10 the planner wrote `plan.md` into a `context_handoff/` directory inside the
  worktree instead of into the session directory.
- **V8:** R10 reported `inconclusive` although `run_ok` failed.

Hard constraints (from the ask):
- The guard never deletes or overwrites uncommitted work of the engineer. When in doubt, it
  saves a backup and fails the phase.
- `vendor/` and `prototype/` do not change.
- Tests never call a model.
- Out of scope: models in rosters, OS-level sandboxing. Also out of scope: the
  engine-level guard `aifactory/src/aifactory/engine/permissions.py` (used by non-task
  `factory run`). It keeps its `_roll_back` and `tests/engine/test_permissions.py` still
  asserts its wording. The change covers the task-run guard in `aifactory/src/aifactory/run/`.

---

## Background (what exists today)

- `aifactory/src/aifactory/run/guard.py` holds `TaskWriteGuard`. The engine calls
  `guard.snapshot(run)` once per phase before the first send, and
  `guard.enforce(run, phase, agent, before)` after it. It also calls `enforce` when the phase
  fails (see `aifactory/src/aifactory/engine/agents.py` ~L182–253, `_enforce_after_failure`).
  `ConflictWriteGuard` in `run/resolve.py` subclasses it and overrides only `snapshot`
  (it calls `super().snapshot(run)`).
- The main-checkout state is `gitops.fingerprint()`. It records only numstat per tracked file
  plus `untracked` per new file, with no content. In `roll_back()`, a path that was dirty before
  the phase is either `left as-is (was already modified)` or
  `REVERTED-BY-AGENT (uncommitted work lost, cannot restore)`. Nothing can be restored because
  nothing was saved.
- `run` (engine `runner.py`) has `run.session_dir` (absolute in task runs, see
  `run/task.py::data_dir`, which resolves the path). `session_dir` sits under `data_dir`, which
  the guard already ignores in the main checkout (`_main_ignored`) and which is in
  `.git/info/exclude`. A backup written there therefore does not show up as a main-checkout
  change and survives `git clean -fd`.
- `context_handoff_dir` is rendered as `str(run.context_handoff_dir)`, which is already
  absolute in task runs. V6 is a prompt problem: the model took the name for a repo-relative
  directory.
- The prompts that use `context_handoff_dir` live only in
  `aifactory/validation/template/.factory/prompts/`. `aifactory/src` has no separate default
  prompt set; confirm this with `grep -rl context_handoff_dir aifactory/src`. If a prompt `.md`
  shows up there, it gets the same rule.
- `validation/scenarios.py`:
  - R1 uses `_roster_gap` correctly.
  - R10 has an unconditional `return res.inconclusive(...)` in the branch
    `if not fixes: if not ctx.local:`. When the run itself failed (for example a planner
    breach), no fix round ran, so this branch hides the failed `run_ok`. That is V8.

---

## Part 1 — V7: save and restore the main checkout (and pre-dirty worktree files)

### 1a. New module `aifactory/src/aifactory/run/backup.py`

A self-contained helper for one checkout. It has no engine imports, only `gitops`, `hashlib`,
`shutil`, `os` and `pathlib`.

```python
@dataclass(frozen=True)
class FileState:
    kind: Literal["file", "symlink", "absent"]
    digest: str = ""          # sha256 of bytes (file) or of the link target (symlink)
    mode: int = 0             # st_mode & 0o777 for files

@dataclass
class CheckoutBackup:
    root: Path
    dir: Path                 # where the copies live
    head: str | None
    ref: str | None
    index_tree: str | None    # `git write-tree`, None when it fails (unmerged index)
    files: dict[str, FileState]   # every dirty path at capture time

def dirty_paths(root: Path, ignored: tuple[str, ...]) -> set[str]
def capture(root: Path, dest: Path, ignored: tuple[str, ...]) -> CheckoutBackup
def state_of(root: Path, path: str) -> FileState
def verify(backup: CheckoutBackup, ignored) -> list[str]      # paths not equal to the capture
def restore(backup: CheckoutBackup, ignored, paths: Iterable[str]) -> dict[str, str]  # path -> outcome
```

Semantics:

- **`dirty_paths`** is the union of:
  - `git diff HEAD --name-only -z --no-renames` (tracked changes, staged or not, including
    deletions),
  - `git diff --cached --name-only -z --no-renames` (so a staged-then-reverted file is
    covered),
  - `git ls-files --others --exclude-standard -z` (untracked, not gitignored, listed
    per file).

  It drops paths matching `ignored`, using the same prefix rule as `guard._ignored`; move
  `_ignored` into `backup.py` and import it from `guard.py`. Use `-z` so paths with spaces
  survive.
- **`capture`** creates `dest/files/` and, for every dirty path:
  - regular file: `shutil.copy2` to `dest/files/<path>` and record digest and mode;
  - symlink: record `os.readlink` and write it to `dest/links.json`;
  - missing (tracked file deleted in the tree): `absent`.

  It also records `head`, `symbolic_head` and `git write-tree` (index). It writes a small
  `dest/manifest.json` (paths, states, head, index_tree) so a human can restore by hand. Any
  OSError while copying must raise (see 1b: the phase must not start without a backup).
- **`state_of`** returns the current state of the path on disk (`lstat`: file, symlink or
  absent).
- **Expected state** of a path: `backup.files[path]` if it was dirty at capture. Otherwise it is
  the content at `backup.head`: `absent` if `git cat-file -e <head>:<path>` fails, else the
  sha256 of `git cat-file blob <head>:<path>`. Ignore the executable bit for HEAD comparisons;
  comparing bytes is enough.
- **`verify`** checks `backup.files` ∪ the current `dirty_paths` and returns every path whose
  current state differs from the expected state. This catches all four cases:
  - an agent-introduced change to a clean path;
  - a pre-dirty file the agent reverted to HEAD (it no longer shows in the diff, but it is in
    `backup.files`);
  - a pre-dirty file the agent edited further;
  - a pre-dirty untracked file the agent deleted.
- **`restore(paths)`**, for each path:
  1. **Never lose anything.** If the path currently exists on disk and will be overwritten or
     deleted, first copy it to `dir/replaced/<path>`, even though it is presumed to be the
     agent's.
  2. Pre-dirty path: write back the saved bytes (`mkdir -p` parents, `copy2`, `chmod` mode),
     recreate the symlink, or remove the file if the saved state is `absent`. The outcome is
     `restored from backup`.
  3. Clean path the agent changed: if it exists in `backup.head`, write the blob bytes from
     `git cat-file blob` to disk. Do not use `git checkout`, so the index is untouched here.
     Otherwise delete it (`deleted`, after step 1).
  4. After all paths: if `index_tree` is set and `git write-tree` now differs, run
     `git read-tree <index_tree>`. This touches only the index, not files, so agent `git add` /
     `git rm --cached` are undone. Report it as a pseudo-path `index` with `restored`.
  5. Call `verify` again. Every path still off is reported as
     `could not restore (backup kept at <dir>)`.

  OSError on any path is caught and reported the same way. It never raises mid-loop.
- If `head`/`ref` moved, do not restore clean paths against the old HEAD and do not touch the
  index. Restore only the pre-dirty paths from their saved bytes (safe: it puts the engineer's
  bytes back). Leave other paths alone and report them `not restored: HEAD moved`. The existing
  HEAD message stays.

### 1b. `aifactory/src/aifactory/run/guard.py`

- **`snapshot`**:
  - Pick a backup directory: `Path(run.session_dir) / "guard_backup" / f"{self._seq:03d}"`,
    where `self._seq` is a counter on the guard incremented per snapshot. Fall back to
    `tempfile.mkdtemp(prefix="haifa-guard-")` when `run` has no `session_dir`.
  - Call `backup.capture(self.main_root, dir / "main", self.main_ignored)` and
    `backup.capture(self.worktree, dir / "worktree", ())`.
  - Store both in the snapshot dict (`"main_backup"`, `"worktree_backup"`) together with the
    existing keys. Keep `"worktree"` (`permissions.snapshot`) and the HEAD keys so the commit
    reset logic is unchanged.
  - Drop `"main"` fingerprint usage in favour of the backup.
  - If `capture` raises, let it propagate as `permissions.PermissionBreach` with the message
    `cannot back up the main checkout before <agent>: <error>`, so the agent is not started.
    `snapshot` runs before `_send_and_check` in `agents.py`, so raising there prevents the call.
    Check that the task-run caller turns this into a failed run, not a crash. If `snapshot` is
    outside the try in `agents.execute`, it propagates as an exception, and `run_task` must
    record `state=failed` with the message. Verify this in the test from 1d.
- **`enforce`**, in this order:
  1. Worktree HEAD handling: unchanged.
  2. Worktree paths:
     - `touched = changed_paths(before["worktree"], after)` as today, plus every path from
       `backup.verify(before["worktree_backup"])` that was pre-dirty. This catches same-numstat
       edits and reverts of earlier phases' work.
     - For an unpermitted path that was pre-dirty, call `backup.restore(worktree_backup, [path])`
       instead of the old `left as-is` / `cannot restore`.
     - For an unpermitted path that was not pre-dirty, keep the existing `roll_back` behaviour.
     - Permitted pre-dirty changes stay as they are (the agent may edit its own `writes`).
  3. Main checkout:
     - `off = backup.verify(before["main_backup"], self.main_ignored)`.
     - If non-empty: `outcomes = backup.restore(before["main_backup"], self.main_ignored, off)`.
     - Add one problem per path: `f"{MAIN}: {path} — {outcome}"`.
     - Then add one line naming the backup: `f"{MAIN}: backup of the state before the phase at {dir}"`.
  4. Main HEAD/ref check: unchanged.
  5. On success (no problems), remove the backup directory of this snapshot (`shutil.rmtree`,
     ignore errors) so sessions do not grow. On any breach, keep it.
- Delete the old `roll_back` branch that returns `REVERTED-BY-AGENT ... cannot restore` and
  `left as-is (was already modified)`. After the change, `grep -rn "cannot restore" aifactory/src/aifactory/run`
  is empty. Keep `roll_back` only for the non-pre-dirty worktree case, or fold it into
  `backup.restore`.
- Update the module docstring:
  - The main checkout is saved before every call.
  - Any difference is restored exactly: tracked, untracked and index.
  - A backup stays under `<session>/guard_backup/NNN/` when a breach happened.
  - Keep the known limit about gitignored files.
- `ConflictWriteGuard` needs no change beyond still calling `super().snapshot(run)`.

### 1c. Unit tests: new `aifactory/tests/run/test_guard_backup.py`

Build a tiny git repo in `tmp_path` (init, user config, commit `a.txt`, `b.txt`, `exec.sh`
with mode 755). No model and no engine; call `backup.capture/verify/restore` directly:

1. **Tracked edit plus untracked file.** `a.txt` modified, `new/wip.txt` untracked. Capture,
   then run `git checkout -- .` and `git clean -fd`. `verify` lists both paths. `restore`
   brings back both exact bytes, and a second `verify` is `[]`.
2. **Staged change.** Capture after `git add b.txt` (modified). The agent runs
   `git reset -q` plus `git checkout -- b.txt`. After restore, the file and `git diff --cached`
   are as before.
3. **Deleted tracked file.** Pre-dirty `rm a.txt`. The agent restores it via `git checkout`.
   After restore, `a.txt` is absent again.
4. **Agent-introduced changes on clean paths.** The agent modifies `b.txt` and adds `x.txt`.
   After restore, `b.txt` equals HEAD and `x.txt` is gone, and a copy of both is under
   `dir/replaced/`.
5. **Pre-dirty file edited further.** The agent adds a line with the same numstat, e.g. swaps
   one line for another. `verify` catches it by digest and `restore` puts back the saved bytes.
6. **Ignored prefixes.** A file under an ignored prefix (e.g. `.factory/data/x`) is never
   captured or restored.

### 1d. Task-run test with the fake harness: `aifactory/tests/run/test_task_run.py`

Add `test_agent_reverting_main_checkout_work_is_restored(repo, script)`:

```python
write(repo, "README.md", "engineer wip\n")          # tracked, uncommitted
write(repo, "notes/wip.txt", "draft\n")              # untracked, new dir

def wipe(wt: Path) -> None:
    git(repo, "checkout", "--", ".")
    git(repo, "clean", "-fd")

script.on("planner", wipe)
script.add("planner", ok())
result = run_task(repo, T01)

assert result.run.state == "failed"
assert (repo / "README.md").read_text() == "engineer wip\n"
assert (repo / "notes" / "wip.txt").read_text() == "draft\n"
error = result.run.error or ""
assert "main checkout: README.md" in error and "notes/wip.txt" in error
assert "cannot restore" not in error
```

Before writing this test, check that `run_task` does not refuse a dirty main checkout.
`test_config_comes_from_base` already runs with an uncommitted file, so it should not. Also
check that `git clean -fd` in `repo` leaves the session data alone: `.factory/data/` and the
worktrees dir are in `info/exclude`, and `clean` without `-x` respects that. If it does not,
the test shows it.

Keep the existing tests green:
- `test_write_to_main_checkout_is_reverted`: README rolled back and x.md deleted; its
  `git status --porcelain == ""` still holds, since the backup lives under the excluded data dir.
- `test_breach_is_reverted_even_when_gate_fails`
- `test_artifact_in_main_checkout_is_rejected`
- `test_config_comes_from_base`: the operator's uncommitted change survives.
- The resolve tests in `tests/run/test_task_resolve.py`.

Add a worktree case: an agent that runs `git checkout -- <spec from earlier phase>` in the
worktree gets that file restored. Only add it if a plan→build workflow is easy to drive in the
existing fixtures. It is optional; the unit tests in 1c cover the mechanism.

---

## Part 2 — V6: prompts say `context_handoff_dir` is an absolute path outside the repo

Canonical rule, the exact same text in every prompt that uses `context_handoff_dir`:

> `<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.

Files, all in `aifactory/validation/template/.factory/prompts/`:
- `planner/system.md`: add the rule as a bullet under `## Instructions`, next to the
  `plan.md` bullet.
- `reviewer/system.md`: the same, under its instructions.
- `planner/user.md`, `builder/user.md`, `documenter/user.md`, `reviewer/user.md`: add the rule
  as a line directly under the `{{context_handoff_dir}}` value in `### context_handoff_dir`,
  before `## Task`.

  **It must not go inside `## Task`.** `validation/fake.py::output_path` takes the first
  backticked relative `.md` path in the last `## Task` section. The rule has no `.md` span, but
  keep it out of `## Task` anyway.
- Any other `.md` under `aifactory/` outside `validation/results/` that contains
  `context_handoff_dir` (grep first; builder/documenter system.md currently do not).

Test: new `aifactory/tests/validation/test_agent_prompts_handoff_dir.py` (style of
`test_agent_prompts_no_git.py`):

```python
PROMPTS = AIFACTORY_DIR / "validation/template/.factory/prompts"
RULE = "is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo"

def prompt_files() -> list[Path]:
    roots = [PROMPTS, AIFACTORY_DIR / "src"]
    return sorted(p for r in roots for p in r.rglob("*.md")
                  if "context_handoff_dir" in p.read_text("utf-8"))

def test_some_prompts_use_it() -> None:
    assert len(prompt_files()) >= 6

@pytest.mark.parametrize("path", prompt_files(), ids=str)
def test_prompt_says_handoff_dir_is_absolute(path: Path) -> None:
    assert RULE in path.read_text("utf-8")
```

Exclude `src/aifactory/skill/skill.md` only if it mentions `context_handoff_dir` without being
an agent prompt. Currently it does not mention it at all.

Also run the existing `test_validation_prompt_paths.py` and `test_validation_template.py`. The
template may have a checksum or snapshot test. If a test pins template content, update the pin
deliberately.

---

## Part 3 — V8: R1/R10 report `failed` when a real check failed

In `aifactory/validation/scenarios.py`:

- Rename the idea of `_roster_gap` to a general helper and keep `_roster_gap` as-is, since
  `test_validation_roster.py` imports it:

  ```python
  def _inconclusive_unless_failed(res: ScenarioResult, why: str) -> ScenarioResult:
      """Inconclusive for `why` only when every kept check passed; else keep `failed`, observe why."""
  ```

  `_roster_gap` delegates to it.
- **R10** (`r10`):
  - Replace the unconditional `return res.inconclusive("opravné kolo neproběhlo, ...")` in
    `if not fixes: if not ctx.local:` with
    `return _inconclusive_unless_failed(res, "opravné kolo neproběhlo, ...")`.
  - Order: when `run_ok` failed, the result is `failed` no matter which branch. Make sure no
    other R10/R1 path sets `res.forced = INCONCLUSIVE` or calls `res.inconclusive` while a check
    has failed. Review each `inconclusive` / `forced` in `r1`, `r10`, `_unverified` and
    `_roster_gap`. `_unverified` already guards; keep it.
  - `if not run_id: return res` stays; with `run_ok` false its outcome is `failed`.
- **R1**: already correct through `_roster_gap`. Verify that `missing` alone (all checks
  passed) gives inconclusive and that a failed `run_ok` gives `failed`.
- Update the module docstring line on R1/R10 if needed: "inconclusive only when the roster
  lacks the harness and every other check passed".

Tests: new `aifactory/tests/validation/test_validation_verdicts.py`. It is a unit test with a
stub context and no model or sandbox; skip `just` markers. Make a minimal stub class
implementing what `r1`/`r10` call:
- attributes: `remote`, `local`, `harnesses`, `state`;
- methods: `catch_up_base`, `run_task` (returns a `Cmd`-like object with `ok`, `run`, `pr`,
  `payload`, `script=None`, `brief()`), `reference` (returns a run_id and records it),
  `add_pr`, `phases`, `phase_rows`, `agent_starts`, `session_usage`, `phase_tokens`,
  `task_run`, `test_output`, `test_passed`, `session_dir` (to `tmp_path`), `envelope`.

Read `r1`, `r10`, `_run_checks` and `_review_round_checks` for the exact calls, and use
`validation.context.Cmd` directly if it is a simple dataclass.

Cases:
1. **R10, remote not local, roster without codex** (`harnesses = {"build": "claude", "fix": "claude", ...}`):
   - run failed (`cmd.ok=False`, `run.state="failed"`, a run_id), no fix phase gives
     `outcome == "failed"` and a failed check named `run_ok`;
   - run succeeded, all phases ok, the review round verified, no codex gives
     `outcome == "inconclusive"`. Use the local branch or give it a fix phase to reach
     `_roster_gap`. The goal is one "only the harness is missing" case.
2. **R1, roster missing codex/pi**:
   - run failed gives `failed`;
   - everything passing gives `inconclusive`.

If the stub grows too large, it is acceptable to test R10 through the `LocalValidation`
fixture of `test_validation_roster.py` with a fake variant that makes the run fail. Prefer the
stub, which is fast.

Keep `test_roster_gap_is_inconclusive_only_when_kept_checks_pass` and the pi-haiku roster
end-to-end tests green.

---

## Verification

Run from the repo root (judge by exit status):

1. `just test`
2. `just typecheck`
3. `just lint`
4. `just validate --remote local`, then check the new `summary.json`: no scenario `failed`.
5. `grep -rn "cannot restore" aifactory/src/aifactory/run` returns nothing.
6. `git status` must not show changes under `vendor/` or `prototype/`.

## Files touched (summary)

- new `aifactory/src/aifactory/run/backup.py`
- `aifactory/src/aifactory/run/guard.py`
- `aifactory/validation/template/.factory/prompts/{planner,reviewer}/system.md`
- `aifactory/validation/template/.factory/prompts/{planner,builder,documenter,reviewer}/user.md`
- `aifactory/validation/scenarios.py`
- new `aifactory/tests/run/test_guard_backup.py`
- `aifactory/tests/run/test_task_run.py` (new test)
- new `aifactory/tests/validation/test_agent_prompts_handoff_dir.py`
- new `aifactory/tests/validation/test_validation_verdicts.py`
