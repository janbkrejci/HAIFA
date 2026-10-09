"""`status: done` and the `## Běhy` line are plain text edits of the task file."""

from __future__ import annotations

from aifactory.backlog import parse_frontmatter
from aifactory.backlog.taskfile import has_entry, mark_done, run_entry

URL = "https://github.com/o/r/pull/7"
ENTRY = run_entry("2026-09-26", "build-commit", URL, 0.4201)


def test_run_entry_format() -> None:
    assert ENTRY == (
        "- 2026-09-26 · workflow build-commit · PR https://github.com/o/r/pull/7 · náklady $0.42"
    )


def test_status_todo_becomes_done_and_section_is_added() -> None:
    text = "---\nid: T1\ntitle: X\nstatus: todo\n---\n\n## Zadání\nDo it.\n"
    out = mark_done(text, ENTRY, pr_url=URL)
    assert out == (
        f"---\nid: T1\ntitle: X\nstatus: done\n---\n\n## Zadání\nDo it.\n\n## Běhy\n\n{ENTRY}\n"
    )
    header, _ = parse_frontmatter(out)
    assert header["status"] == "done"


def test_missing_status_is_added_to_header() -> None:
    out = mark_done("---\nid: T1\n---\nbody\n", ENTRY)
    assert out.startswith("---\nid: T1\nstatus: done\n---\nbody\n")


def test_existing_section_with_comment_keeps_it() -> None:
    text = (
        "---\nid: T1\nstatus: todo\n---\n\n## Zadání\nDo it.\n\n"
        "## Běhy\n\n<!-- doplňuje HAIFA -->\n"
    )
    out = mark_done(text, ENTRY)
    assert out.endswith(f"## Běhy\n\n<!-- doplňuje HAIFA -->\n{ENTRY}\n")
    assert out.count("## Běhy") == 1


def test_entry_goes_before_the_next_section() -> None:
    text = (
        "---\nid: T1\nstatus: todo\n---\n\n## Běhy\n\n- 2026-01-01 · workflow a · PR x · "
        "náklady $1.00\n\n## Poznámky\nkeep me\n"
    )
    out = mark_done(text, ENTRY)
    assert out.endswith(f"náklady $1.00\n{ENTRY}\n\n## Poznámky\nkeep me\n")


def test_rest_of_file_is_unchanged() -> None:
    body = "\n## Zadání\nDo  it.\n\n```yaml\nstatus: todo\n```\n"
    text = f"---\nid: T1\nstatus: todo  # comment\nwrites: [a/]\n---\n{body}"
    out = mark_done(text, ENTRY)
    assert out.startswith(f"---\nid: T1\nstatus: done\nwrites: [a/]\n---\n{body}")


def test_idempotent() -> None:
    text = "---\nid: T1\nstatus: todo\n---\n\nbody\n"
    once = mark_done(text, ENTRY, pr_url=URL)
    assert has_entry(once, URL)
    later = run_entry("2026-09-27", "build-commit", URL, 1.0)
    assert mark_done(once, later, pr_url=URL) == once
    assert mark_done(once, ENTRY) == once
