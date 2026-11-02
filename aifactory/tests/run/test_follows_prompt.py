"""Task continuation context and seed rules for handling discovered work."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import DOC, SPEC, T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.library import SEED_DIR
from aifactory.run import TaskPrRow, TaskRunRow, TaskRunStore, run_task
from aifactory.run.follows import TEXT_LIMIT
from aifactory.run.store import SUCCEEDED

T03 = "M01-S01-T03"
T04 = "M01-S01-T04"
STEP = "backlog/M01-core/S01-model"
URL = "https://example.com/pr/7"
AGENTS = ("builder", "planner", "tester", "reviewer", "documenter")


def _unfinished_work(agent: str) -> str:
    system = (SEED_DIR / "agents" / agent / "system.md").read_text(encoding="utf-8")
    return system.split("## Unfinished work\n", 1)[1].split("\n## ", 1)[0].strip()


def test_seed_agents_share_unfinished_work_rules() -> None:
    sections = [_unfinished_work(agent) for agent in AGENTS]
    assert all(section == sections[0] for section in sections)


@pytest.mark.parametrize("agent", AGENTS)
def test_seed_agents_finish_discovered_work_before_follow_ups(agent: str) -> None:
    section = _unfinished_work(agent)
    required = (
        "Never leave open work in the repository: no TODO files, no lists of open points, "
        'no "later" or "open questions" sections in docs or specs, '
        'no `TODO`/`FIXME`/"finish later" comments.',
        "Finish discovered work in this task whenever you can",
        "delegate it to a subagent and integrate the result in this run",
        "pass implementation or repair work to the builder in this run",
        "outside the allowed `writes` goes into `needs_writes`, never a follow-up",
        "return `status: fail` with `fail_kind: needs_writes`",
        "Use `follow_ups` only as a last resort",
        "belongs to an existing backlog task (name its id instead of creating a duplicate)",
        "would change this task's goal",
        "Neither extra context nor a missing write permission is a reason to create a follow-up",
        "check the earlier reports from this run and the existing backlog",
        'The documenter must not turn a builder\'s "out of scope" note into another follow-up',
        "keep it only as a finding in the task document, not as open work",
        "Set `for_human: true` only for access or credentials, "
        "an action in a system outside the repository, "
        "or a decision the agent is not authorized to make",
        "Consolidate all decisions requiring a person from this run into one `for_human` follow-up",
        "A backlog or task front-matter edit alone does not justify `for_human`",
        "put the existing task's id in `blocked_by`",
    )
    for sentence in required:
        assert sentence in section, (agent, sentence)
    assert "Work that turns out to be out of scope, extra, or a changed intent" not in section
    assert "follow-ups are for what does not" not in section
    assert "Work only a person can do (a change of the backlog" not in section


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def _done_original(repo: Path) -> str:
    """T01 merged through a merge commit, its spec too long for the prompt; T03 and T04
    continue the chain. Returns the merge commit."""
    git(repo, "checkout", "-q", "-b", f"factory/{T01}-1")
    write(repo, "src/app/model.py", "x = 1\n")
    write(repo, SPEC, "# spec\n" + "s" * (TEXT_LIMIT + 500) + "\nSPEC-TAIL\n")
    write(repo, DOC, "# doc\nDOC-BODY\n")
    tip = commit_all(repo, "T01 work")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge T01", f"factory/{T01}-1")
    merge = git(repo, "rev-parse", "HEAD")
    t01 = repo / STEP / "M01-S01-T01-schema.md"
    t01.write_text(
        t01.read_text(encoding="utf-8").replace("status: todo", "status: done"), encoding="utf-8"
    )
    write(
        repo,
        f"{STEP}/M01-S01-T03-more.md",
        f"---\nid: {T03}\ntitle: More\nstatus: todo\nfollows: {T01}\n---\n\n"
        "## Zadání\nRozšířit schéma.\n",
    )
    write(
        repo,
        f"{STEP}/M01-S01-T04-even-more.md",
        f"---\nid: {T04}\ntitle: Even more\nstatus: todo\nfollows: {T03}\n---\n\n"
        "## Zadání\nJeště dál.\n",
    )
    commit_all(repo, "backlog")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        base_sha = git(repo, "rev-parse", f"{merge}^1")
        store.claim(
            TaskRunRow(
                run_id="orig0001",
                task_id=T01,
                branch=f"factory/{T01}-1",
                worktree=str(repo / "gone"),
                base="main",
                base_sha=base_sha,
                head_sha=tip,
                state=SUCCEEDED,
                started_at="2026-10-01T10:00:00",
                ended_at="2026-10-01T10:30:00",
                workflow="plan-commit",
            )
        )
        store.save_pr(
            TaskPrRow(
                f"factory/{T01}-1", T01, "local", "7", URL, "main", base_sha, "T01", "",
                "merged", "2026-10-01T10:31:00", "2026-10-01T10:40:00",
                merged_at="2026-10-01T10:40:00", merge_sha=merge,
            )
        )  # fmt: skip
    finally:
        store.close()
    return merge


def test_prompt_carries_the_original_task(tmp_path: Path, script: Script) -> None:
    repo = make_run_repo(tmp_path / "repo")
    merge = _done_original(repo)
    script.add("planner", ok())

    result = run_task(repo, T03)

    assert result.run.state == "succeeded", result.run.error
    prompt = script.calls[0].prompt
    assert f"## Original task {T01}: Schema" in prompt
    # the whole task text of the original
    assert "Navrhnout schéma." in prompt
    # spec over the limit: cut, with the file to read the rest from
    assert "# spec" in prompt and "SPEC-TAIL" not in prompt
    assert f"read the whole text in {SPEC} in the working directory" in prompt
    # documentation fits
    assert f"### Documentation ({DOC})" in prompt and "DOC-BODY" in prompt
    assert f"- pull request: {URL} (merged)" in prompt
    assert f"- merge commit: {merge}" in prompt
    changed = prompt.split("### Changed files", 1)[1].split("###", 1)[0]
    assert "- src/app/model.py" in changed and f"- {SPEC}" in changed
    assert "run orig0001 · workflow plan-commit · succeeded" in prompt
    # the follow-up's own text comes before the original's section
    assert prompt.index("Rozšířit schéma.") < prompt.index(f"## Original task {T01}")
    assert "Earlier tasks of the chain" not in prompt


def test_chain_shows_direct_predecessor_and_links_older(tmp_path: Path, script: Script) -> None:
    repo = make_run_repo(tmp_path / "repo")
    _done_original(repo)
    script.add("planner", ok())

    result = run_task(repo, T04)

    assert result.run.state == "succeeded", result.run.error
    prompt = script.calls[0].prompt
    assert f"## Original task {T03}: More" in prompt
    assert "Rozšířit schéma." in prompt
    assert f"## Original task {T01}" not in prompt
    older = prompt.split("### Earlier tasks of the chain", 1)[1]
    assert f"- {T01} — Schema: task file {STEP}/M01-S01-T01-schema.md, spec {SPEC}" in older
    # the older generation is a reference only: none of its texts or PR
    assert "Navrhnout schéma." not in prompt
    assert "DOC-BODY" not in prompt and URL not in prompt


@pytest.mark.parametrize("related", [False, True])
def test_prompt_carries_open_dependencies(tmp_path: Path, script: Script, related: bool) -> None:
    repo = make_run_repo(tmp_path / "repo")
    task_id = "M01-S01-T02"
    if related:
        write(
            repo,
            f"{STEP}/{T03}-more.md",
            f"---\nid: {T03}\ntitle: More\nstatus: todo\nrelated: [{task_id}]\n---\n"
            "\n## Zadání\nPrověřit loader.\n",
        )
        task_id = T03
        commit_all(repo, "dependency context")
    script.add("planner", ok(blocked_by=[T01]))

    result = run_task(repo, task_id, force=True)

    prompt = script.calls[0].prompt
    section = prompt.split("## Existing open dependencies", 1)[1]
    assert f"### {T01}: Schema" in section
    assert "Navrhnout schéma." in section
    assert "M01-S01-T02 depends_on" in section
    assert "Do not report follow_ups" in section and "blocked_by" in section
    assert result.follow_ups is not None
    assert result.follow_ups.created == []
    assert result.follow_ups.blocked_by == [T01]
