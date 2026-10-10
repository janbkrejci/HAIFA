"""Validation gates: verify the envelope's CLAIMS, never guesses.

A gate is `gate(envelope, run) -> GateReport` — one check per item it looked at.
Violations are derived from the failed checks and sent back to the SAME agent
session as a correction. Every check is recorded either way, so a green gate
says WHAT it verified instead of only that it passed.

Gates check what is mechanically checkable; plan quality is a reviewer's job.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .data_types import EnvelopeBase, GateReport

TAIL_CHARS = 1000        # command output kept as evidence on a failure


def _size(path: Path) -> str:
    n = path.stat().st_size
    return f"{n}B" if n < 1024 else f"{n / 1024:.1f}KB"


def _inside(path: Path, roots) -> bool:
    """aifactory 2.9: True when `path` lies inside one of `roots`."""
    return any(path == root or path.is_relative_to(root) for root in roots)


def artifacts_exist(envelope: EnvelopeBase, run) -> GateReport:
    # aifactory 2.9: an artifact counts only inside the run's worktree (repo_root)
    # or its session directory. A relative path is taken from repo_root, not from
    # the process cwd, so a file the agent wrote into another checkout never passes.
    report = GateReport()
    repo_root = getattr(run, "repo_root", None)
    session_dir = getattr(run, "session_dir", None)
    roots = ([Path(repo_root).resolve(), Path(session_dir).resolve()]
             if repo_root is not None and session_dir is not None else None)
    for a in envelope.artifacts:
        p = Path(a)
        if roots is not None:
            if not p.is_absolute():
                p = Path(repo_root) / p
            p = p.resolve()
            if not _inside(p, roots):
                report.check(a, False,
                             "declared artifact is outside the run's worktree and session directory")
                continue
        report.check(a, p.exists(),
                     f"exists, {_size(p)}" if p.exists() else "declared artifact does not exist")
    return report


def files_non_empty(envelope: EnvelopeBase, run) -> GateReport:
    report = GateReport()
    for a in envelope.artifacts:
        p = Path(a)
        if not (p.exists() and p.is_file()):
            continue                       # existence is artifacts_exist's job
        empty = p.stat().st_size == 0
        report.check(a, not empty, "declared artifact is empty" if empty else _size(p))
    return report


def json_parses(envelope: EnvelopeBase, run) -> GateReport:
    report = GateReport()
    for a in envelope.artifacts:
        p = Path(a)
        if p.suffix != ".json" or not p.exists():
            continue
        try:
            parsed = json.loads(p.read_text())
            report.check(a, True, f"parses, {type(parsed).__name__}")
        except json.JSONDecodeError as e:
            report.check(a, False, f"declared JSON artifact does not parse: {e}")
    return report


def _deleted_paths() -> set[str]:
    """Paths git sees as deleted, staged or not.

    Deleting a file is a change like any other, and a builder that removes one
    reports it in `changed_files`. Without this the gate would call the removal
    a lie because the path is gone, which is the one thing a deletion
    guarantees.
    """
    paths: set[str] = set()
    for args in (["diff", "--name-only", "--diff-filter=D"],
                 ["diff", "--cached", "--name-only", "--diff-filter=D"]):
        result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            paths.update(line for line in result.stdout.splitlines() if line)
    return paths


def diff_matches_claims(envelope: EnvelopeBase, run) -> GateReport:
    """Every file claimed changed must exist on disk, or be one git says was deleted."""
    report = GateReport()
    claims = list(getattr(envelope, "changed_files", []))
    # Only pay for the git calls if something claimed is missing.
    deleted = _deleted_paths() if any(not Path(f).exists() for f in claims) else set()
    for f in claims:
        p = Path(f)
        if p.exists():
            report.check(f, True, f"exists, {_size(p)}")
        else:
            gone = f in deleted
            report.check(f, gone,
                         "deleted" if gone else "claimed changed file does not exist")
    return report


def verdict_consistent(envelope: EnvelopeBase, run) -> GateReport:
    """A review's verdict must agree with the findings it just wrote down.

    Nothing here judges the code — that is the reviewer's job. This checks the
    envelope against itself: an approval that ships blocking items, or a
    rejection that names no problem, is a claim the harness can refute without
    reading a line of the diff.
    """
    report = GateReport()
    approved = bool(getattr(envelope, "approved", False))
    blocking = list(getattr(envelope, "blocking", []))
    unmet = [f.requirement for f in getattr(envelope, "findings", []) if not f.met]

    report.check("approved vs blocking", not (approved and blocking),
                 "no blocking items" if not blocking
                 else f"{len(blocking)} blocking item(s) while approved=true"
                 if approved else f"{len(blocking)} blocking item(s), not approved")
    report.check("approved vs findings", not (approved and unmet),
                 "every requirement met" if not unmet
                 else f"{len(unmet)} unmet requirement(s) while approved=true"
                 if approved else f"{len(unmet)} unmet requirement(s), not approved")
    report.check("rejection names a problem", approved or bool(blocking or unmet),
                 "verdict is supported" if approved or blocking or unmet
                 else "approved=false but no blocking item or unmet requirement was given")
    return report


def checks_runnable(envelope: EnvelopeBase, run) -> GateReport:
    """aifactory 3.0: every check of a test plan names a program this checkout can start.

    Only the first argv element is checked (on PATH, or a file in the worktree);
    whether the checks are the right ones is the reviewer's call.
    """
    report = GateReport()
    root = Path(getattr(run, "repo_root", None) or ".")
    for check in getattr(envelope, "checks", []):
        program = check.argv[0]
        local = (root / program).is_file() if ("/" in program or "\\" in program) else False
        found = local or shutil.which(program) is not None
        report.check(check.name, found,
                     f"`{program}` found" if found
                     else f"`{program}` is neither on PATH nor a file in the worktree")
    return report


def plan_keeps_checks(envelope: EnvelopeBase, run) -> GateReport:
    """aifactory 3.0: a new test plan drops no check of the previous plan silently.

    A previous check is kept when a new check runs the same argv; otherwise its
    name must be in `dropped` with a reason. The interpreter puts the previous
    plan on `run.previous_test_plan` (None for the first plan of a run).
    """
    report = GateReport()
    previous = getattr(run, "previous_test_plan", None)
    if previous is None:
        return report
    argvs = [check.argv for check in getattr(envelope, "checks", [])]
    dropped = {d.name for d in getattr(envelope, "dropped", [])}
    for check in previous.checks:
        if check.argv in argvs:
            report.check(check.name, True, "kept")
        else:
            report.check(check.name, check.name in dropped,
                          "dropped with a reason" if check.name in dropped
                          else "left out without a `dropped` entry; keep it or say why it goes")
    return report


def tests_pass(command: str):
    """Gate factory: the given shell command must exit 0."""
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding="utf-8")
        ok = result.returncode == 0
        note = f"exit {result.returncode}"
        if not ok:
            note += "\n" + (result.stdout + result.stderr)[-TAIL_CHARS:]
        return GateReport().check(command, ok, note)
    gate.__name__ = f"tests_pass({command})"
    return gate
