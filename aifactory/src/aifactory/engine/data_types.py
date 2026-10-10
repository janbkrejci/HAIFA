"""Concrete data types for the SSSF ADW system.

RULE (four-param rule): any function that takes more than 4 parameters takes
ONE of these objects instead. AgentCall and PhaseParams are the pattern.

Every agent call declares a concrete output type — an EnvelopeBase subclass —
that its final JSON response is parsed against. No untyped handoffs.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional, Type

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

# aifactory 3.0: the tester agent's checks and the evidence of what the test step ran.
from aifactory.testing.model import Check, Coverage, Dropped, Evidence, plan_problems

PhaseKind = Literal["engineer", "agent", "code"]
PhaseStatus = Literal["queued", "running", "success", "fail"]


# ── Phases ────────────────────────────────────────────────────────────────────

class PhaseParams(BaseModel):
    """Everything run.phase() needs. Passed as one object, never loose params."""

    name: str                       # short id, unique within the run: "plan", "build"
    kind: PhaseKind                 # which lane the block renders in
    owner: str                      # engineer's name, "git", or an agent name from config
    description: str                # REQUIRED: what this phase does and why — see below
    retries: int = 0                # agent phases: gate-failure retries via continue

    @field_validator("description")
    @classmethod
    def _description_must_be_earned(cls, value: str, info: ValidationInfo) -> str:
        """A phase name identifies; a description explains. Both are required.

        The description is the only sentence the trace, the console, and the
        phase block in the UI ever show about intent — everything else is ids,
        statuses, and timings. `commit_plan: "Commit the plan"` tells a reader
        nothing they could not already see, so an echo is rejected the same way
        a blank one is. This is a construction-time error on purpose: it fires
        before the phase opens, not after a run is already in the trace.
        """
        text = " ".join(value.split())
        name = str(info.data.get("name", "?"))
        if not text:
            raise ValueError(
                f"phase {name!r}: description is required — one sentence on what this "
                f"phase does and why. It is what the trace and the UI show.")
        if text.rstrip(".").casefold() == name.replace("_", " ").casefold():
            raise ValueError(
                f"phase {name!r}: description {text!r} only restates the phase name — "
                f"say what it does and why instead.")
        return text


class Phase(BaseModel):
    """The persisted phase record — PhaseParams plus lifecycle."""

    phase_id: str
    adw_id: str
    seq: int
    params: PhaseParams
    status: PhaseStatus = "fail"    # success must be earned
    attempt: int = 0
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


# ── Envelopes (agent output types) ───────────────────────────────────────────

class EnvelopeBase(BaseModel):
    """Base of every agent's final JSON response. Output types extend this."""

    status: Literal["success", "fail"]
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    notes_for_next_agent: str = ""


class GenericOutput(EnvelopeBase):
    pass


class PlanOutput(EnvelopeBase):
    # Subject for committing the PLAN — the spec file the planner wrote, not the
    # implementation it describes. Each agent's commit_message covers its own
    # work product, so a chain that commits per step never reuses one agent's
    # words for another agent's diff.
    commit_message: str = ""


class BuildOutput(EnvelopeBase):
    changed_files: list[str] = Field(default_factory=list)
    commit_message: str = ""        # consumed by the git commit phase


class ScoutFinding(BaseModel):
    file: str
    note: str = ""


class ScoutOutput(EnvelopeBase):
    findings: list[ScoutFinding] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    """One thing the request (or plan) asked for, and whether it is there."""

    requirement: str                # the ask, in the requester's words
    met: bool
    evidence: str = ""              # where it lives, or what is missing


class ReviewOutput(EnvelopeBase):
    """Confirmation that what was built is what was asked for — not a test run."""

    approved: bool = False
    findings: list[ReviewFinding] = Field(default_factory=list)
    blocking: list[str] = Field(default_factory=list)   # what must change before approval


class DocumentOutput(EnvelopeBase):
    """Where the write-up of a completed change landed."""

    document_path: str = ""         # the doc in the repo, e.g. app_docs/<task-id>-<slug>.md
    documented_files: list[str] = Field(default_factory=list)
    commit_message: str = ""


# ── Deterministic quality blocks ─────────────────────────────────────────────

QualityArea = Literal["frontend", "backend"]
QualityOperation = Literal["lint", "typecheck", "build"]


class QualityCheckSpec(BaseModel):
    """One deterministic quality command."""

    name: str
    area: QualityArea
    operation: QualityOperation
    argv: list[str]
    timeout_seconds: int = 120


class QualityCheckResult(BaseModel):
    """Captured evidence from one quality command."""

    name: str
    area: QualityArea
    operation: QualityOperation
    command: str
    returncode: int
    passed: bool
    duration_seconds: float
    output_artifact: str
    # The tail of stdout+stderr, verbatim and unparsed. A failure has to travel
    # back to the builder as an envelope, and the builder cannot open a log file
    # it was never handed — so the evidence rides along. Deliberately raw: every
    # runner formats failures differently and a generic parser would be
    # confidently wrong. The full log is always at output_artifact.
    output_tail: str = ""


class QualityResult(BaseModel):
    """Aggregate result from a quality block: every check it ran, and the verdict."""

    # aifactory 3.0: which checks of the tester's plan ran.
    test_plan: Evidence | None = None
    passed: bool
    checks: list[QualityCheckResult] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


# ── Change capture (git diff, deterministic) ─────────────────────────────────

class ChangeCapture(BaseModel):
    """Everything documentation.capture() needs. One object, never loose params."""

    base: str = "main"              # the ref the work is measured against
    max_diff_lines: int = 2000      # the diff artifact is truncated past this
    include_untracked: bool = True  # a brand-new file is part of the change


class BaseRef(BaseModel):
    """The commit a change is measured from, and why that one.

    `reason` is the line the trace shows. A diff is only as trustworthy as the
    thing it was taken against, so the ADW records that choice instead of
    leaving the reader to infer it.
    """

    ref: str                        # what was asked for: "main", or a pinned sha
    commit: str                     # the commit actually diffed against
    reason: str = ""

    @property
    def label(self) -> str:
        """Display form — a named ref as itself, a pinned raw sha shortened."""
        if len(self.ref) == 40 and all(c in "0123456789abcdef" for c in self.ref):
            return self.ref[:7]
        return self.ref


class ChangeSet(BaseModel):
    """What changed since the base commit — pure git facts, no judgement."""

    base: BaseRef
    files: list[str] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    stat: str = ""                  # `git diff --stat` output, verbatim
    diff_path: str = ""             # the full diff, written into context_handoff/
    truncated: bool = False

    @property
    def empty(self) -> bool:
        return not (self.files or self.untracked)


class ChangesOutput(EnvelopeBase):
    """A ChangeSet shaped as an envelope so an agent can be handed it directly.

    Same adapter idea as VerifyOutput: code computes the diff, the documenter
    consumes it through the one door every agent handoff uses.
    """

    base: str = ""                  # "<ref> @ <commit> — <reason>"
    changed_files: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    stat: str = ""
    diff_path: str = ""             # read this for the full diff


class VerifyOutput(EnvelopeBase):
    """A deterministic result, shaped as an envelope so an agent can consume it.

    Agents hand each other typed envelopes; code blocks return QualityResult.
    This is the adapter, so a failing lint or test run flows back into the
    builder through exactly the same door a tester agent's report used to —
    the ADW script is the only thing that knows the difference.
    """

    # aifactory 3.0: what the test step ran from the tester's plan; `coverage` repeats
    # the plan's coverage for conditions (`test.coverage == "full"`), "" for a command.
    test_plan: Evidence | None = None
    coverage: str = ""
    passed: bool = False
    failures: list[str] = Field(default_factory=list)


# aifactory 3.0: the tester agent picks the checks; the `test` step runs exactly these.
class TestPlanOutput(EnvelopeBase):
    """The checks that verify this change: enough to trust it, nothing beyond.

    `full` runs the whole suite, `scoped` a subset the change can affect, `none`
    nothing (for example a documentation-only change). A later plan keeps every
    check of the previous one or names it in `dropped` with the reason. The
    reviewer judges the choice; the harness only checks that the plan is
    coherent, runnable and drops nothing silently.
    """

    coverage: Coverage
    reason: str = Field(min_length=1)
    checks: list[Check] = Field(default_factory=list)
    dropped: list[Dropped] = Field(default_factory=list)
    # Set only when the tester triages failed checks: `plan` (the checks themselves
    # were wrong; this envelope is the corrected plan) or `code` (the plan stands).
    failure_cause: Literal["", "code", "plan"] = ""

    @model_validator(mode="after")
    def coherent(self) -> "TestPlanOutput":
        problems = plan_problems(self.coverage, self.checks)
        if problems:
            raise ValueError("; ".join(problems))
        return self


# ── Agent calls ──────────────────────────────────────────────────────────────

class GateCheck(BaseModel):
    """One thing a gate looked at, and what it found.

    `note` is the evidence — "exists, 2.1KB", "exit 0", "not in the diff". On a
    failed check it doubles as the reason, so it is what the agent is told.
    """

    item: str                       # what was checked: a path, a command, a test
    ok: bool
    note: str = ""


class GateReport(BaseModel):
    """What every gate returns: the checks it ran. Violations are derived.

    Authoring stays a one-liner per item — `report.check(...)` appends and
    returns self, so a gate is a loop and a return.
    """

    checks: list[GateCheck] = Field(default_factory=list)

    def check(self, item: str, ok: bool, note: str = "") -> "GateReport":
        self.checks.append(GateCheck(item=item, ok=ok, note=note))
        return self

    @property
    def violations(self) -> list[str]:
        return [f"{c.item}: {c.note or 'failed'}" for c in self.checks if not c.ok]

    @property
    def passed(self) -> bool:
        return not self.violations


class AgentCall(BaseModel):
    """One agent invocation: prompt in, typed envelope out, gates verified."""

    model_config = {"arbitrary_types_allowed": True}

    output_type: Type[EnvelopeBase]
    prompt: str
    previous: Optional[EnvelopeBase] = None
    gates: list[Callable] = Field(default_factory=list)   # gate(envelope, run) -> list[str]
    # Extra `{{name}}` prompt variables of this call (HAIFA-S03-T12: a workflow
    # step with several inputs). The engine's own variables win on a clash.
    variables: dict[str, str] = Field(default_factory=dict)


# ── Config ───────────────────────────────────────────────────────────────────

class PromptEngineering(BaseModel):
    system: str                     # path to system.md
    user: str                       # path to user.md


class AgentConfig(BaseModel):
    name: str
    coding_agent: Literal["pi", "claude_code"] = "pi"
    model: str = "google/gemini-3.6-flash"
    thinking: str = "medium"        # off | minimal | low | medium | high | xhigh | max
    color: str = ""                 # hex swatch for this agent's lane in the UI
    purpose: str = ""
    prompt_engineering: PromptEngineering
    harness_engineering: list[str] = Field(default_factory=list)
    # aifactory 2.10: library skills bound to this agent, indexed in its prompt.
    skills: list[str] = Field(default_factory=list)
    tools: Optional[list[str]] = None    # allowlist; None = all tools usable
    # What this agent may MODIFY in the repo, enforced in code after every call
    # (see adw_modules/permissions.py). `tools` cannot express this: `bash` runs
    # anything and `write` reaches any path, so an agent's capability list is a
    # statement of intent that nothing checks.
    #   None  -> unrestricted, except the roster-wide `protected_files` paths
    #   []    -> read-only: may modify nothing tracked
    #   [...] -> only these. A trailing "/" means a directory prefix; a "*"
    #            makes it a glob; anything else is an exact path.
    writes: Optional[list[str]] = None
    # Shell commands the agent must not run (HAIFA-S03-T12), e.g. `just test` or
    # `pytest` without a path. Written as the command pattern the harness matches
    # (`*` is a wildcard); harnesses that cannot enforce it are reported, never
    # silently trusted.
    disallowed_commands: list[str] = Field(default_factory=list)


class ChainStep(BaseModel):
    """One step of a composed chain: what to run, and who runs it.

    `raw` is kept because it is what the engineer typed — the console, the
    trace and a saved recipe all show the chain back in their own words, and
    reconstructing it from the parsed fields would quietly rewrite them.
    """
    name: str                       # a key in roles.ROLES or roles.CODE_STEPS
    kind: PhaseKind                 # "agent" or "code"
    model: str = ""                 # as typed after @, before resolution
    thinking: str = ""              # as typed after ~
    raw: str = ""


class Recipe(BaseModel):
    """A chain worth running again, saved under adws/adw_recipes/."""
    name: str
    description: str = ""
    steps: list[ChainStep] = Field(default_factory=list)


class ModelOverrides(BaseModel):
    """What `--model` asked for, before the roster is touched.

    Two scopes, deliberately: a bare `--model haiku` retunes the whole chain in
    one word (which is how a cheap dry run is set up), while `--model
    builder=opus` pins one lane (which is how the expensive agent is bought
    only where it earns its keep). Per-agent wins over the blanket value.
    """
    every_agent: str = ""
    per_agent: dict[str, str] = Field(default_factory=dict)


class ConfigDefaults(BaseModel):
    coding_agent: Literal["pi", "claude_code"] = "pi"
    model: str = "google/gemini-3.6-flash"
    thinking: str = "medium"
    color: str = ""
    harness_engineering: list[str] = Field(default_factory=list)
    tools: Optional[list[str]] = None    # roster-wide allowlist; None = all tools usable
    disallowed_commands: list[str] = Field(default_factory=list)  # roster-wide default
    # Off-limits to every agent that has not named them in its own `writes`.
    # The factory's own code is the default: an agent must not be able to edit
    # the machinery that decides whether its work passed.
    protected_files: list[str] = Field(default_factory=lambda: [
        "adws/adw_modules/", "adws/adw_sssf_config/", "adws/adw_*.py",
    ])
    data_dir: str = "adws/adw_data"


class ObservabilityConfig(BaseModel):
    db: str = "adws/adw_data/sssf.db"
    poll_ms: int = 500


class SSSFConfig(BaseModel):
    defaults: ConfigDefaults = Field(default_factory=ConfigDefaults)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    agents: list[AgentConfig] = Field(default_factory=list)


# ── Tracing ──────────────────────────────────────────────────────────────────

class EventRecord(BaseModel):
    """One traced event, always logged against adw_id + phase."""

    adw_id: str
    phase_id: str = ""
    type: str                       # phase_start | agent_start | tool_call | handoff | gate_pass | gate_fail | log | agent_end | phase_end | error
    name: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_id: str = ""
    tokens: Optional[int] = None
    # Spans: set both when an event covers real elapsed time (a tool call), so
    # the UI lays it out on a time axis without parsing payload JSON. Left unset,
    # the tracer stamps started_at with the moment the event was recorded.
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


# ── Pi coding agent interface ────────────────────────────────────────────────

class PiRequest(BaseModel):
    """Everything one non-interactive pi run needs."""

    prompt: str
    system_prompt: str
    model: str                      # registry pattern, resolved to provider + id
    thinking: str = "medium"
    session_id: str                 # pi --session-id: creates or continues
    session_dir: str
    raw_output_path: str            # JSONL stream lands here
    tools: Optional[list[str]] = None
    extensions: list[str] = Field(default_factory=list)
    disallowed_commands: list[str] = Field(default_factory=list)  # shell commands the agent may not run
    cwd: str = "."                  # set from run.repo_root — the codebase root agents work in


class UsageBreakdown(BaseModel):
    """Tokens and the dollars they cost, per component, summed over a call.

    Mirrors pi's `usage` shape one-for-one so the numbers reconcile with what
    pi itself reports: `input` EXCLUDES cache reads, which bill at their own
    (cheaper) rate — add them to learn the size of the prompt that was sent.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    # Thinking tokens. NOT a fifth component: measured across every session on
    # disk, reasoning is always <= output and the four components above always
    # sum to totalTokens, so reasoning is the thinking SHARE of output, billed
    # at the output rate. Report it nested under output, never added to it.
    reasoning_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_read_cost: float = 0.0
    cache_write_cost: float = 0.0
    total_cost: float = 0.0

    def add_turn(self, usage: dict, total_tokens: int) -> None:
        """Fold in one pi `message_end` usage object.

        `total_tokens` is passed in rather than re-derived: the caller already
        computes it pi's way (totalTokens, else the sum of the parts).
        """
        cost = usage.get("cost") or {}
        self.input_tokens += usage.get("input") or 0
        self.output_tokens += usage.get("output") or 0
        self.cache_read_tokens += usage.get("cacheRead") or 0
        self.cache_write_tokens += usage.get("cacheWrite") or 0
        self.reasoning_tokens += usage.get("reasoning") or 0
        self.total_tokens += total_tokens
        self.input_cost += cost.get("input") or 0.0
        self.output_cost += cost.get("output") or 0.0
        self.cache_read_cost += cost.get("cacheRead") or 0.0
        self.cache_write_cost += cost.get("cacheWrite") or 0.0
        self.total_cost += cost.get("total") or 0.0

    def merge(self, other: "UsageBreakdown") -> None:
        """Add another call's usage — a phase that retries spends more than once."""
        for field in self.model_fields:
            setattr(self, field, getattr(self, field) + getattr(other, field))


class PiResult(BaseModel):
    text: str = ""
    returncode: int = 0
    session_id: str = ""
    tokens: int = 0
    cost: float = 0.0
    usage: UsageBreakdown = Field(default_factory=UsageBreakdown)
    # Context occupancy after the LAST turn — not a sum. `tokens` bills every
    # turn; this is how full the window is right now, which is what the
    # visualizer's context bar measures against `context_window`.
    context_tokens: int = 0
    context_window: int = 0         # 0 when the registry declares no ceiling


# The transport every coding-agent interface speaks — pi and Claude Code alike.
# Named Pi* while pi was the only harness; the aliases are what new code uses,
# so a third interface never has to pretend to be pi to be callable.
AgentRequest = PiRequest
AgentResult = PiResult
