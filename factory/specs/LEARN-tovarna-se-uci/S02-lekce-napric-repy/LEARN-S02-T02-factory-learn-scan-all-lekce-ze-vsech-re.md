# Plan LEARN-S02-T02: `factory learn scan --all`, lessons from every repo, each with a target repo

## Goal

`factory learn scan --all` reads objections from every registered repo (`learn.sources.collect_all`). The `learner` still runs read-only in an isolated clone of the repo the scan runs in. Every lesson names a target repo (`repo`, a registry id). Each lesson is saved in the `LessonStore` of its target repo, with the ids of the repos its objections came from (`origin`). Without `--all`, the lessons, the storage and the terminal output stay as they are today. The only changes are additive JSON fields and one new allowed target, `seed`.

Existing pieces to reuse (do not edit them, they are outside the allowed paths):
- `aifactory/src/aifactory/learn/sources.py`:
  - `registered_repos(home)` returns `SourceRepo(id, name, path, trace_db)` plus warnings.
  - `collect_all(since, home)` returns objections whose `repo` is set and whose key is prefixed `<id>:...`, plus warnings.
  - `factory_repo(home)` returns the `RepoEntry` of the factory repo, or None. It respects `HAIFA_FACTORY_REPO`.
  - `_split(key, known)` splits a prefixed key into `(repo_id, rest)`.
- `aifactory.web.registry`: `Registry(haifa_home()).snapshot()` and `same_repo(path_a, path_b)`.
- `aifactory/tests/learn_fixture.py`: `register_learn_repos(tmp_path, *names)` registers fixture repos, each with runs `run-a`/`run-b`/`run-c` and objections c1–c3. `fake_learner` is the fake harness.

## 1. `aifactory/src/aifactory/learn/store.py`

- Add `origin TEXT NOT NULL DEFAULT ''` to `_SCHEMA`, after `task_id`.
- Migration in `__init__`: if `"origin" not in columns`, run `ALTER TABLE learn_lessons ADD COLUMN origin TEXT NOT NULL DEFAULT ''`. This sits next to the existing `task_id` migration. Both checks use the same `columns` set, read once.
- `StoredLesson` gets a last field `origin: list[str] = field(default_factory=list)`, the ids of the repos the objections came from. The column stores it as `",".join(origin)`. Reading `''` gives `[]`, so split and drop empty parts.
- `all()` selects `origin` as the 10th column and passes it to the new field.
- `save_proposed` writes `origin` on insert, and in `ON CONFLICT ... DO UPDATE SET` it adds `origin=excluded.origin`. The `WHERE state = proposed` guard stays.
- `add_repeats` leaves `origin` unchanged. Repeats are recorded in `complaints`/`runs` only, as they are today.
- Update the module docstring: one sentence on `origin`.

## 2. `aifactory/src/aifactory/learn/scan.py`

### Models
- `TARGETS = ("CLAUDE.md", "AGENTS.md", "skill", "prompt", "seed")`. The `target` Literal gains `"seed"`. Update the `target_detail` description to: "the skill name for 'skill', the role or agent for 'prompt' or 'seed', else ''".
- `ProposedLesson.repo: str = Field(default="", max_length=100, description="id of the registered repo the rule belongs to (from 'repos'); '' without repos")`. The default `""` keeps answers without `repo` valid, so the existing single-repo tests and seed answers still work.

### Repo identity helpers (new, private)
- `_own_id(repo: Path) -> str`: the registry id of `repo` (`same_repo(e.path, repo)` over `Registry(haifa_home()).snapshot()[0].repos`), or `""` when `repo` is not registered.
- `_factory_id() -> str`: `factory_repo().id`, or `""` when there is none.

### `context(objections, settled, repos=None)`
- With `repos is None` (no `--all`), return exactly today's dict, with no new keys. This is what keeps "no change without `--all`" true.
- With `repos` (a list of `{"id", "name", "is_factory"}`):
  - Every objection item gets `"repo": o.repo`.
  - Add `"repos": repos`.
  - Add `"targets"["seed"]`: "the prompt of a role in the seed of the HAIFA library (target_detail: the role name); only for the repo with is_factory".
  - Add `"repo_rule"`: "Set `repo` of every lesson to the id of the repo the rule belongs to. A rule about the conventions or code of one repo belongs to that repo. A shortcoming of the factory itself (how a role or agent behaves, a role prompt that fails in several repos) belongs to the repo with is_factory; target 'seed' is only allowed there."
- `output_schema` stays `LessonsOutput.model_json_schema()`, which now shows `repo` and `seed`. Accept that in both modes.

### Gate in `_ask_learner`
New signature: `_ask_learner(repo, payload, known, repos: set[str] | None, own: str, factory: str)`.
- `repos is None` means single-repo mode, where the target repo is `own`.
- Otherwise the target repo is `lesson.repo.strip()`.

Keep `ids_known` and add these problems:
- In all mode, when the target repo is not in `repos`, report `f"lesson '{lesson.rule}': unknown repo id '{lesson.repo}' (repos: {', '.join(sorted(repos))})"`.
- When `lesson.target == "seed"` and (`not factory` or the target repo `!= factory`), report `f"lesson '{lesson.rule}': target 'seed' is only for the factory repo '{factory}'"`. When there is no factory repo, the text says "there is no factory repo".

This works the same way as the unknown objection id check, with one correction (`CORRECTIONS`). Pass the gate as one function, or as two functions in `gates=[...]`.

### `lessons_of` / `repeats_of`
- Count runs per `(o.repo, o.run_id)`, not per `o.run_id`. Both fixture repos have `run-a`/`run-b`. In single-repo mode `o.repo == ""`, so the result is the same as today.
- Each entry gets `"repo"`, the target id: `lesson.repo.strip()` in all mode, `own` in single-repo mode. Pass it in through a parameter `target_repo: Callable[[ProposedLesson], str]`, or pass `own` and an `all_repos` flag.
- The result row gets:
  - `"repo"`
  - `"origin"`: sorted distinct `o.repo` of the objections, without `""`
  - `"origin_repos"`: `len(origin)`, or 1 when origin is empty in single-repo mode
- Each `runs` item gets `"repo": o.repo` only when `o.repo` is non-empty, so the single-repo output is unchanged.
- `_snippet`: add `"repo": o.repo` only when it is non-empty (`view.py` imports `_snippet`, so keep its single-repo output identical).
- `repeats_of` stays as it is.
- The top-level `runs` count in `scan` is `len({(o.repo, o.run_id) for o in objections})`.

### `scan(repo, since=None, all_repos=False)`
- Single-repo mode (`all_repos=False`) keeps today's flow: `collect(db)`, one store, `store.settled()`. Then:
  - `own = _own_id(repo)` and `factory = _factory_id()` are computed only when needed. Both read only the registry, which is cheap.
  - Each lesson gets `repo=own` and `origin=[]`, and is saved with `origin=[]`.
  - The return dict keeps today's top-level keys exactly (`since`, `objections`, `runs`, `lessons`, `repeats`). The lessons gain `repo`/`origin`/`origin_repos`. `test_since_leaves_one_run_and_no_agent` asserts the whole dict and must still pass unchanged.
- All mode:
  1. `sources_list, warnings = registered_repos()`. `objections, w2 = collect_all(since_iso)`, keeping the last `_MAX_OBJECTIONS`.
  2. `factory = _factory_id()`. `repos_ctx = [{"id": s.id, "name": s.name, "is_factory": s.id == factory} for s in sources_list]`.
  3. Settled lessons from every repo's store: open `LessonStore(s.trace_db)` for each `s`. On `sqlite3.Error`/`OSError`, append a warning and skip that repo. For each settled lesson, qualify its complaints: `k if _split(k, known_ids)[0] else f"{s.id}:{k}"`. Unprefixed keys belong to the repo whose store holds them, so they now match the prefixed keys from `collect_all`. Use `dataclasses.replace(lesson, complaints=...)`. Record `owner[lesson_id] = s.id`, first one wins.
  4. If the runs number at least `MIN_RUNS`, call `_ask_learner(repo, context(objections, settled, repos_ctx), set(by_id), {s.id for s in sources_list}, own, factory)`.
  5. Save each lesson with `LessonStore(trace_db_of[lesson["repo"]]).save_proposed(StoredLesson(..., origin=lesson["origin"]))`. Its `complaints` are the prefixed keys. Its `runs` are the plain run ids (as today; T03 resolves the objections by key).
  6. Repeats: for `lid, found in repeats_of(...)`, call `add_repeats` in the store of `owner[lid]`, with the prefixed keys.
  7. Close every store you open, in `try/finally`. A simple way is a dict of opened stores keyed by repo id, closed at the end.
  8. The return dict also gets `"all": True` and `"warnings": warnings + w2`.
- The single-repo branch never touches other repos' stores.
- Keep the 400-objection cap, `parse_since` and the `MIN_RUNS` shortcut in both modes.

### `format_scan`
- The lesson header line stays `f"{id}  {occ} run(s)  -> {_where(lesson)}"`. When `data.get("all")`, append `f"  in {lesson['repo']} (objections from {lesson['origin_repos']} repo(s))"`.
- In all mode the head says `"... in N run(s) of M repo(s)"`, where M is the number of distinct `o.repo`. Include `"repos": M` in the all-mode data only.
- Single-repo text stays identical. The existing test checks the substring `f"{id}  2 run(s)  -> AGENTS.md"`.

### Docstring
Add a paragraph on `--all`: the source is `collect_all`, each lesson goes to the store of its target repo, settled lessons come from every store, and `seed` is for the factory repo only.

## 3. `aifactory/src/aifactory/cli.py` (`_add_learn_commands`, `_learn`)
- Add `scan.add_argument("--all", dest="all_repos", action="store_true", help="read the objections of every repo registered in the dashboard; each lesson names the repo its rule belongs to and is saved in that repo's trace DB (factory shortcomings go to the HAIFA repo, target 'seed' only there)")`.
- Add one sentence about `--all` to the end of the scan `description`.
- In `_learn`, call `data = scan(root, args.since, all_repos=args.all_repos)`. Pop `warnings = data.pop("warnings", [])`. With `--json`, call `_emit_ok(data, warnings)`; otherwise print `format_scan(data)` and each warning as `warning: ...` to stderr, as `accept` does.
- `web/learn.py` calls `scan(repo, since)` positionally and keeps working. Do not touch it.
- If a skill or CLI-tree snapshot test fails because of the new flag, check `aifactory/tests/skill/`. Expected: the skill is rendered from argparse with no snapshot. If one exists outside the allowed paths, report it instead of editing it.

## 4. Seed `aifactory/src/aifactory/seed/agents/learner/`
- `system.md`, new bullets in the Instructions:
  - The context may carry `repos` (id, name, `is_factory`) and a `repo` on every objection, when the scan reads every registered repo. Then every lesson needs `repo`, the id of the repo the rule belongs to:
    - a rule for the conventions or code of one repo belongs to that repo;
    - a shortcoming of the factory itself (how a role or agent behaves, a role prompt that fails in several repos) belongs to the repo with `is_factory`.
  - Without `repos`, leave `repo` empty.
  - `target`: add `seed`, the prompt of a role in the HAIFA library seed (`target_detail`: the role name), allowed only when `repo` is the factory repo. Update the `target_detail` bullet.
  - Group objections from different repos into one lesson only when they share a mistake that belongs to one target repo.
- `user.md`: the Context sentence mentions "the registered repos (`repos`, when the scan reads every repo)". Keep the `{{prompt}}` placeholder.
- `agent.yaml` needs no change unless it lists the targets. Check it.

## 5. Tests

### `aifactory/tests/learn/test_learn_store.py`
- Rename or extend the module docstring.
- Extend `test_old_table_gets_task_id_column`, or add `test_old_table_gets_origin_column`. The old schema (no `task_id`, no `origin`) migrates. `lesson.origin == []`. `save_proposed` with `origin=["alpha", "beta"]` round-trips. Reopening the store changes nothing.
- Add a table that has `task_id` but no `origin`, the exact previous schema. It also migrates.

### `aifactory/tests/learn/test_learn_scan.py`
Setup:
- A fixture `two_repos(tmp_path, monkeypatch)` calls `monkeypatch.setenv(FACTORY_REPO_ENV, "haifa")` (from `aifactory.learn.sources`) and `register_learn_repos(tmp_path, "haifa", "app")`. `haifa` is the factory repo.
- The scan runs with `--repo <haifa>` (the learner clone). Objections from both repos give c1–c3 from `haifa` and c4–c6 from `app`, in registry order. Check the order in `collect_all`: it follows the registry order.
- Helper `_scan(capsys, repo, "--all")` already supports extra arguments. Also assert `envelope["warnings"]` where relevant.

Tests:
1. `test_scan_all_saves_each_lesson_in_its_target_repo`:
   - The answer has a factory lesson `{"rule": "Builder: run ruff before reporting.", "target": "seed", "target_detail": "builder", "repo": "haifa", "complaints": ["c3", "c6"]}` and an app lesson `{**TESTS_LESSON, "repo": "app", "complaints": ["c4", "c5"]}`.
   - Assert:
     - each lesson has `repo` and `origin_repos`: 2 for the seed lesson, 1 for the app lesson;
     - the `haifa` trace DB `LessonStore.all()` holds only the seed lesson, with `origin == ["app", "haifa"]` and complaints prefixed `haifa:`/`app:`;
     - the `app` trace DB holds only the tests lesson;
     - the context has `repos` with `is_factory` true for `haifa` only, every objection has `repo`, and `targets` contains `seed`;
     - the `run(s)` count treats `run-a` of both repos as different runs.
   - The text output (`main([... "--all"])` without `--json`) shows `in haifa (objections from 2 repo(s))`.
2. `test_scan_all_unknown_repo_and_seed_outside_factory_are_corrected`:
   - The first answer has `repo: "nope"` on one lesson and `target: "seed"` with `repo: "app"` on another. The second answer is valid.
   - Assert `len(seen) == 2`, and that `seen[1].prompt` contains `unknown repo id 'nope'` and `target 'seed' is only for the factory repo`. Only the corrected lessons are saved.
3. `test_scan_all_skips_settled_lessons_of_any_repo`:
   - Store a lesson as rejected in the `app` store, through `LessonStore(...).save_proposed` then `reject`, with unprefixed complaint keys from `collect(app db)`.
   - `scan --all`, where the learner proposes the same rule for `haifa`, gives no lesson.
   - The context `rejected_lessons` contains it.
   - Optionally, also cover an accepted lesson in `app` whose repeat (`accepted` id) calls `add_repeats` in the `app` store.
4. `test_seed_target_without_all_outside_factory_is_corrected`, optional: single-repo mode with no factory repo. The `seed` lesson goes back for correction.
5. Single-repo regression. Existing tests run unchanged: `test_scan_proposes_repeated_objection_only` and the others. Add asserts there:
   - `lesson["repo"] == ""` (an unregistered fixture repo);
   - the context has no `repos` key and no `repo` on objections;
   - `"seed"` is not in `context["targets"]`;
   - the store row has `origin == []`.
   `test_since_leaves_one_run_and_no_agent` must still pass on whole-dict equality.

`learn_fixture.py` probably needs no change. If needed, add a parameter to `register_learn_repos`, keeping it backward compatible.

### `aifactory/tests/library/test_library_seed.py`
It only checks agent names (line ~102), so no change is expected. If it compares learner prompt content, update it.

## Verification (for the tester)
- `just lint`, `just typecheck`
- `cd aifactory && uv run pytest tests/learn/ tests/library/test_library_seed.py`. `tests/learn/` covers `view`/`accept`, which import `_snippet`/`trace_db` and must stay green.
- `uv run pytest tests/web/ -k learn`. `web/learn.py` calls `scan`. Find the file with `grep -rln "learn" aifactory/tests/web`.
- The CLI help test, if any: `grep -rn "learn scan" aifactory/tests`.

## Out of scope
`accept`/`view` reading prefixed keys (T03), the dashboard (T04), `docs/decisions.md` (T05).
