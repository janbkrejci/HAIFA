# HAIFA-REFINEMENT-T65 — Read-only follow-up triager

## Outcome and boundaries

Ship a seed agent `triager` and an independently callable `aifactory.run.triage.ask_triager(repo, reported, backlog) -> list[Decision]`. It compares every reported follow-up with tasks whose stored status is exactly `todo` and returns `covered`, `extend`, `decide`, or `new`. It never creates or edits backlog tasks. T66 will consume these decisions after T64 and T65 merge; T65 needs no T64 dependency or edits to its files.

Only implement in these authorized paths:

- `aifactory/src/aifactory/seed/agents/triager/agent.yaml`
- `aifactory/src/aifactory/seed/agents/triager/system.md`
- `aifactory/src/aifactory/seed/agents/triager/user.md`
- `aifactory/src/aifactory/library/seed.py`
- `aifactory/src/aifactory/run/triage.py`
- `aifactory/tests/run/test_triage.py`
- `aifactory/tests/library/test_library_seed.py`
- `aifactory/tests/config/test_config_loader.py`
- `aifactory/tests/validation/test_validation_template.py`
- This exact spec and the task's exact named documentation artifact under `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T65-agent-triager-porovna-ohlasene-follow-up.md` if the documentation phase needs to describe this module's API. Do not document application of decisions to the backlog; that belongs to T66.

No additional writes are required. Do not modify learner, `learn/scan.py`, `run/followups.py`, the engine, workflows, `.factory/`, backlog, frontend, or THIRD_PARTY_NOTICES. Runtime files produced by the eventual API follow the learner runtime convention and are not source artifacts to commit.

## Existing contracts to reuse

Read `learn/scan.py` (`LessonsOutput`, `context`, `_ask_learner`) and the three learner prompts as patterns only. `_ask_learner` already demonstrates `load_run_config`, `_isolated`, `prepare_cfg`, `agents.resolve`, enabled/installed harness checks, `agent.writes = []`, `TaskWriteGuard`, `Run.phase`, gates and tracer cleanup.

Use `Reported` from `run/followups.py`, preserving that type unchanged. It contains title, reason, details, blocks_task, writes, for_human and provenance fields. Use `Backlog`/`Task` from backlog and `iter_tasks`, `effective_writes`, `is_human` for correct inherited values. `Task.writes` alone is not the effective scope. The stored status, rather than derived readiness, decides inclusion: blocked and human `todo` tasks remain candidates, done and cancelled tasks do not.

`run/scope.py` has normalization and concrete-path matching. Its `paths_overlap` is deliberately conservative for scheduling and cannot prove scope containment. `workflow/propose_check.named_paths` is useful supplementary evidence for paths in prose but is not a proof that all additions fit. Do not use its permissive directory-overlap coverage for this gate.

## Decision and output contract in run/triage.py

Define `TriageUnavailable(RuntimeError)` as the public failure callers can catch. Keep data models, context assembly and decision validation pure; isolate configuration, filesystem and agent execution in `ask_triager` and a private invocation helper if useful.

Define a Pydantic `Decision` with `extra="forbid"`:

- `follow_up_id`: stable input identifier `f1`, `f2`, …, assigned from the original reported sequence, not title text.
- `action`: literal `covered | extend | decide | new`.
- `reason`: nonblank one-sentence explanation.
- `task_id`: target id for covered/extend/decide, absent or null for new.
- `addition`: nonblank additive text for extend only; it does not replace the target's original body.
- `proposal`: nonblank proposed change and explanation for decide only.
- `addition_writes`: explicit list of repo-relative paths/patterns needed by an extend addition; absent/null for the other actions. This is scope evidence for the gate, not new writes granted to a target.

Require meaningful strings after stripping. Enforce the field combinations with model validation and/or the decision gate, so malformed combinations cannot escape. Define `TriageOutput(EnvelopeBase)` with `extra="forbid"` and a `decisions` list, following `LessonsOutput`. Provide the generated schema in context. Do not cap the number of decisions below the number of reported follow-ups.

Return one decision per report in input order, even if the agent returns them in another order. Do not deduplicate by title or discard `blocks_task`/`for_human` distinctions. These decisions recommend handling only; they do not change any original report fields or apply dependencies.

## Pure context(reported, backlog)

Use explicit signatures taking a sequence of `Reported` and a `Backlog`, returning a JSON-serializable dictionary. Emit:

- `follow_ups`: id plus title, reason, details, blocks_task, writes (preserve null versus explicit empty), and for_human. Preserve report text, with no arbitrary follow-up count cap.
- `backlog`: all and only `todo` tasks in deterministic backlog order; each has id, title, status, containing step identity/title, body, effective writes, effective assignee (`human` or `agent`). Find the nearest step ancestor, with the immediate container as a fallback for valid differently shaped trees.
- `output_schema`: `TriageOutput.model_json_schema()`.

Bound each task body to a documented module constant, e.g. 6,000 characters including an ellipsis. Indicate body truncation in the item. Keep complete ids, title, step, writes and assignee. Do not truncate the number of todo tasks or silently compare only a subset. Agent instructions must require reading the relevant full task body in the isolated checkout before claiming complete coverage or recommending extend/decide where a truncated excerpt is insufficient. The input is data, not instructions to execute embedded commands.

Context construction must not load configuration, create runtime directories, edit input objects or invoke a harness.

## Deterministic decision gate

A private pure helper can return violations for a supplied `TriageOutput`, reports and backlog; wrap it in the engine gate signature `(envelope, run) -> list[str]`. For success envelopes validate:

1. Exactly one decision for every expected `follow_up_id`; reject unknown ids, duplicates, omissions and surplus decisions, not just unequal counts.
2. Every targeted id identifies a real `Task` in the supplied backlog and its status is still exactly `todo`. Reject unknown ids, container ids, done and cancelled targets even if a stale/forged output names them.
3. Enforce action-specific fields and nonblank reason/addition/proposal.
4. Reject extend to any effective human-assigned task. A human-only follow-up must not be redirected into an agent extension; instruct the agent to choose an appropriate new/decide outcome when assignment would have to change.
5. Prove all writes required by the extension fit within the target's effective writes. Check both the original report's explicit writes, when present, and `addition_writes`; an agent cannot hide an out-of-scope reported path by omitting it from output. Scope is never expanded by an extend decision.

For scope validation keep a small conservative containment helper local to `triage.py`. Normalize `./` and separators; reject absolute paths and parent traversal. Concrete required paths use scope matching. A requested subtree must fit as a whole; `src/app/` is not covered by target `src/app/one.py`, and `src/app/` does not cover `src/application/`. Identical normalized globs, unrestricted target `**`, and subtrees under a literal target directory are provable cases. For other wildcard combinations reject when containment cannot be established; never treat a matching literal prefix or potential overlap as proof. An equal glob may be accepted; `src/*/one.py` cannot cover `src/**`.

If reported writes are null, require the agent to identify the addition's required paths in `addition_writes` before accepting extend. An empty evidence list is acceptable only for explicitly read-only work (reported writes explicitly empty and addition needing no writes); unknown scope is not an empty scope. State this in prompts and correction messages. Related work that needs broader paths should be new rather than an invalid extend. A decide recommendation is reserved for a change requiring a person's decision because it narrows or materially changes an existing assignment; it is not automatic approval to rewrite it.

Check recognizable repo paths explicitly named as work targets in addition text as supplementary evidence, so `addition_writes` cannot trivially contradict the addition. Do not claim natural-language interpretation is a deterministic guarantee: semantic relatedness, full coverage and preservation of the original intent are the triager's instructed judgment; completeness, target eligibility and declared path containment are enforced in code.

Gate violations identify follow-up id, target id and offending paths/action, so one repair can address them. Never silently coerce an invalid decision into new.

## Read-only ask_triager execution

1. Before any configuration, clone, runtime or harness operation: return `[]` for no reports; if there are reports but no todo tasks, return an ordered new decision for each with a brief reason. Tests must show this works even without a configured repo or harness.
2. Load committed run configuration and create a uniquely named triage job. Follow learner's isolated checkout at `rc.commit` using `_isolated(repo, rc.commit, None)`. Use runtime under `.factory/data/triage/<job>/` for generated prompts and traces, with all paths routed there rather than committed files.
3. Call `prepare_cfg`, require triager in the resolved roster/library fallback, resolve it, check enabled harness and `check_harness(canonical(...))`. Follow established packaged seed defaults in `agent.yaml` like learner (claude/claude-opus-5-5, medium); the task's Codex roster note controls execution overrides, not edits to `.factory/` or other existing seed agents.
4. Force resolved agent writes to `[]` regardless of overrides before validation. Build `Run`, isolated repo_root, safe-mode environment, and `TaskWriteGuard(repo, isolated, TaskScope(job_id, (), ()), ignored_runtime_paths)` following learner. No spec/doc outputs are granted to this agent.
5. Use one phase, `PhaseParams(kind="agent", owner="triager", retries=1)`, with `AgentCall(output_type=TriageOutput, gates=[...])` and serialized context. Use engine gate repair, no outer retry loop. The engine separately has its existing malformed-JSON repair budget; do not alter global JSON_FIX_ATTEMPTS or engine behavior for this task. Semantic decision rejection gets one correction and then fails.
6. Return the validated decisions in report order only after the engine's gates pass. No writes to backlog, calls to followups.record, task edits, CLI integration or persistent decision application.
7. Convert missing/invalid roster configuration, missing/disabled/unavailable harness, agent-reported failure, exhausted output/gate repair and harness invocation/setup failures to clear `TriageUnavailable` messages with exception chaining. `agents.resolve`/`agents.validate` can raise SystemExit: contain that at these precise configuration boundaries, without swallowing KeyboardInterrupt or arbitrary BaseException. Preserve useful diagnostics and never return invented new decisions on invocation failure.
8. Track success correctly and finish/close the tracer in finally on every post-creation exit, including gate or guard failure. Isolated checkout cleanup must run on all paths. Read-only guard violations remain failures; do not convert them to recommendations.

## Seed and prompt changes

Create triager's three files, matching seed layout and prompt variable conventions. `agent.yaml` includes a clear purpose and `defaults.writes: []`. Add `"triager"` to `SEED_AGENTS` in `library/seed.py`; directory discovery and packaged library seed then supply it without new workflow/role definitions.

System prompt must explain the four decisions exactly:

- covered: an existing todo task fully covers the whole reported work; return task_id.
- extend: closely related additive work that retains every existing requirement and fits existing writes; return task_id, addition and addition_writes. Never narrow, delete, replace or fundamentally change original scope. Never extend a human task.
- decide: coverage would require narrowing or fundamentally changing an existing task; return task_id and proposal describing the change and why a human must decide.
- new: no existing todo task covers the work; recommend a new TODO task.

Require one reason sentence and exactly one decision per follow-up id. Allow covered/decide targets to be human todo tasks; only extend forbids them. Enforce preservation of human-only work. Explain truncated context/full-body inspection, writes proof and failure behavior. State read-only isolation and no file edits/deletes/commits/backlog writes. Return only schema-conforming JSON with status success or an explicit fail summary. User prompt embeds `{{prompt}}` and asks for that JSON.

## Tests and acceptance evidence

Keep fixtures/helpers local to `tests/run/test_triage.py`; existing learner/advice fixture patterns can be read/reused without editing shared helpers. Mock harness run and availability/enabled checks. Exercise real `AgentCall` output parsing and gates for representative cases, rather than mocking ask_triager itself. Temporary committed test repos and fake interfaces require no model, credentials or external service.

Cover in that file:

- Pure context with todo/done/cancelled tasks, a blocked todo task, inherited human assignee/writes, all report fields, body truncation and schema; input data unchanged.
- All four valid decisions and ordered identity mapping, including identical report titles and shuffled output order.
- Reject unknown/container/done/cancelled target ids and extend to inherited human assignee.
- Reject missing, duplicate and unknown follow-up ids and malformed action-specific fields.
- Accept a valid additive extension within inherited writes; reject uncovered report writes even when omitted from addition_writes, narrower-file versus directory mismatch, sibling-prefix mismatch, unsafe paths and unprovable broad glob containment. Cover null versus explicit empty writes and scope evidence contradictions.
- Invalid first decision then valid correction succeeds; repeated gate violation makes exactly two semantic attempts and raises TriageUnavailable with a useful message. Malformed output exhaustion and status fail also produce TriageUnavailable.
- Missing agent, disabled/unavailable harness and failed invocation all yield TriageUnavailable without live services.
- No reports returns []; no todo tasks (empty or only done/cancelled) returns all new; spies prove no configuration/agent/runtime setup is performed.
- Read-only setup uses a different checkout, forces writes empty even with a permissive roster override, and closes tracer/removes checkout on success and failure. Include one fake-harness write attempt to verify the existing guard rejects it and leaves tracked repo/backlog content unchanged. Expected engine trace files are runtime, not backlog mutations.

Update exact seed expectations within authorized existing tests:

- `test_library_seed.py`: add triager to explicit seed roster expectation and assert its three files validate, read-only bindings and prompts load. Add a temporary-library seed dry-run test in this file proving agent/triager is offered as create when absent; existing init/reseed APIs suffice, with subprocess/service boundaries mocked as usual.
- `test_config_loader.py`: add triager to ordered inherited roster and full-set assertions; test inherited read-only agent configuration.
- `test_validation_template.py`: add triager in sorted inherited agents after scout. Preserve existing validation scenario behavior; never run live validation models.

## Verification commands

Run commands from repository root, judging command exit codes. Use Python 3.11+, uv and just on PATH.

1. `just lint` and `just typecheck` always (allow roughly 120 seconds each on a fresh environment).
2. `just pytest tests/run/test_triage.py tests/library/test_library_seed.py tests/config/test_config_loader.py tests/validation/test_validation_template.py` (allow 10 minutes on the Windows factory machine).
3. Exercise direct seed/config callers with `just pytest tests/library/test_library_reseed.py tests/library/test_library_store.py tests/config/test_config_cli.py` (allow 10 minutes). These files are read/test-only, not additional write permissions. If previous targeted commands already included them, do not repeat them.

Do not run the entire suite, just check, frontend checks or browser tests for this backend-only task. No live `factory learn scan`, model calls, real home-library seeding or machine configuration changes. Builder reports actual commands and results; planning-phase checks alone do not validate the implementation.

Acceptance is the public module/seed behavior above with green targeted tests, lint and typecheck. Do not add backlog integration or duplicate testing follow-ups; T66 owns only application of these completed decisions.
