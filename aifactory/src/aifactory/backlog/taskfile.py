"""Text edits of a task file: header fields, ``status: done`` and a line in ``## Běhy``.

Only the edited header lines (or the end of the ``## Běhy`` section) change;
every other byte of the file stays as it was.
"""

from __future__ import annotations

import json
import re

import yaml

from aifactory.backlog.frontmatter import FrontmatterError, parse_frontmatter

RUNS_HEADING = "## Běhy"
_STATUS = re.compile(r"^status:[^\n]*$", re.MULTILINE)


def run_entry(date: str, workflow: str, pr_url: str, cost: float) -> str:
    return f"- {date} · workflow {workflow} · PR {pr_url} · náklady ${cost:.2f}"


def _split_header(text: str) -> tuple[str, str, str]:
    """(opening '---' line, header, rest from the closing '---' on)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("task file does not start with a '---' YAML header")
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return lines[0], "".join(lines[1:i]), "".join(lines[i:])
    raise ValueError("task file header is not closed with '---'")


def _set_done(header: str) -> str:
    if _STATUS.search(header):
        return _STATUS.sub("status: done", header, count=1)
    if header and not header.endswith("\n"):
        header += "\n"
    return header + "status: done\n"


def _is_done(header: str) -> bool:
    match = _STATUS.search(header)
    return match is not None and match.group(0).split(":", 1)[1].strip() == "done"


def _runs_section(body: str) -> tuple[int, int] | None:
    """Start and end offsets of the ``## Běhy`` section in `body`."""
    heading = re.search(rf"^{re.escape(RUNS_HEADING)}[ \t]*$", body, re.MULTILINE)
    if heading is None:
        return None
    following = re.search(r"^#{1,2} ", body[heading.end() :], re.MULTILINE)
    end = heading.end() + following.start() if following else len(body)
    return heading.start(), end


def _add_entry(body: str, entry: str) -> str:
    section = _runs_section(body)
    if section is None:
        sep = "" if body.endswith("\n") or not body else "\n"
        return f"{body}{sep}\n{RUNS_HEADING}\n\n{entry}\n"
    start, end = section
    part = body[start:end]
    stripped = part.rstrip("\n")
    trailing = part[len(stripped) :]
    new_part = f"{stripped}\n{entry}\n{trailing[1:]}"
    return body[:start] + new_part + body[end:]


def has_entry(text: str, pr_url: str) -> bool:
    try:
        _, _, rest = _split_header(text)
    except ValueError:
        return False
    section = _runs_section(rest)
    if section is None:
        return False
    return any(
        line.startswith("- ") and f"PR {pr_url} " in line + " "
        for line in rest[section[0] : section[1]].splitlines()
    )


def mark_done(text: str, entry: str, pr_url: str | None = None) -> str:
    """`text` with ``status: done`` and `entry` appended to ``## Běhy``.

    Idempotent: when the task is done already and ``## Běhy`` has a line for
    `pr_url` (or exactly `entry`), the text comes back unchanged.
    """
    opening, header, rest = _split_header(text)
    already = (has_entry(text, pr_url) if pr_url else False) or entry in rest.splitlines()
    if _is_done(header) and already:
        return text
    header = _set_done(header)
    if not already:
        rest = _add_entry(rest, entry)
    return opening + header + rest


FIELD_ORDER: tuple[str, ...] = (
    "id",
    "title",
    "status",
    "workflow",
    "depends_on",
    "related",
    "writes",
    "test",
    "source",
    "target",
    "test_timeout",
    "specs_dir",
    "docs_dir",
    "auto_continue",
    "auto_merge",
)
RUNS_PLACEHOLDER = "<!-- doplňuje HAIFA při schválení PR -->"
_UNSAFE_CHARS = set(":#,[]{}&*!|>'\"%@`\n\r\t")


def format_scalar(value: str) -> str:
    """`value` as a YAML scalar: plain when that reads back as the same string, else quoted."""
    plain = (
        bool(value)
        and value == value.strip()
        and not any(ch in _UNSAFE_CHARS for ch in value)
        and value[0] not in "-?"
    )
    if plain:
        try:
            plain = yaml.safe_load(value) == value
        except yaml.YAMLError:
            plain = False
    return value if plain else json.dumps(value, ensure_ascii=False)


def format_list(values: list[str]) -> str:
    return "[" + ", ".join(format_scalar(v) for v in values) + "]"


def _format_value(value: str | list[str] | bool | int) -> str:
    if isinstance(value, list):
        return format_list(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return format_scalar(value)


def _key_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    """(key, start, end) of every top-level key in header `lines`, continuations included."""
    result: list[tuple[str, int, int]] = []
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:")
    for i, line in enumerate(lines):
        match = key_re.match(line)
        if match:
            if result:
                key, start, _ = result[-1]
                result[-1] = (key, start, i)
            result.append((match.group(1), i, len(lines)))
        elif result and not (line[:1] in (" ", "\t", "-") or not line.strip()):
            key, start, _ = result[-1]
            result[-1] = (key, start, i)
    # trailing blank lines do not belong to the last key
    fixed: list[tuple[str, int, int]] = []
    for key, start, end in result:
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        fixed.append((key, start, end))
    return fixed


def _header_value(text: str, key: str) -> tuple[bool, object]:
    try:
        data, _ = parse_frontmatter(text)
    except FrontmatterError as exc:
        raise ValueError(str(exc)) from exc
    return key in data, data.get(key)


def set_field(text: str, key: str, value: str | list[str] | bool | int) -> str:
    """`text` with header field `key` set to `value` on one line; the rest stays as it was."""
    opening, header, rest = _split_header(text)
    lines = header.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    new_line = f"{key}: {_format_value(value)}\n"
    ranges = _key_ranges(lines)
    found = [r for r in ranges if r[0] == key]
    if found:
        _, start, end = found[0]
        lines[start:end] = [new_line]
    else:
        before = FIELD_ORDER[: FIELD_ORDER.index(key)] if key in FIELD_ORDER else FIELD_ORDER
        after_ends = [end for k, _, end in ranges if k in before]
        position = max(after_ends) if after_ends else len(lines)
        if not after_ends:
            while position > 0 and not lines[position - 1].strip():
                position -= 1
        lines.insert(position, new_line)
    result = opening + "".join(lines) + rest
    present, parsed = _header_value(result, key)
    if not present or parsed != value:
        raise ValueError(f"cannot set header field '{key}' safely")
    return result


def remove_field(text: str, key: str) -> str:
    """`text` without header field `key` (and its continuation lines)."""
    opening, header, rest = _split_header(text)
    lines = header.splitlines(keepends=True)
    found = [r for r in _key_ranges(lines) if r[0] == key]
    if not found:
        return text
    _, start, end = found[0]
    del lines[start:end]
    result = opening + "".join(lines) + rest
    present, _ = _header_value(result, key)
    if present:
        raise ValueError(f"cannot remove header field '{key}' safely")
    return result


def new_task_text(fields: dict[str, object], body: str = "") -> str:
    """A new task file: header fields in ``FIELD_ORDER``, ``## Zadání`` and ``## Běhy``."""
    header: list[str] = []
    for key in FIELD_ORDER:
        value = fields.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            header.append(f"{key}: {format_list([str(v) for v in value])}\n")
        elif isinstance(value, (bool, int)):
            header.append(f"{key}: {_format_value(value)}\n")
        else:
            header.append(f"{key}: {format_scalar(str(value))}\n")
    text = body.strip()
    zadani = f"## Zadání\n{text}\n" if text else "## Zadání\n"
    return f"---\n{''.join(header)}---\n\n{zadani}\n{RUNS_HEADING}\n{RUNS_PLACEHOLDER}\n"


def new_index_text(container_id: str, title: str, body: str = "") -> str:
    """A new ``index.md`` of a project or step: ``id`` and ``title``, then the description."""
    header = f"---\nid: {format_scalar(container_id)}\ntitle: {format_scalar(title)}\n---\n"
    text = body.strip()
    return f"{header}\n{text}\n" if text else header


def replace_body(text: str, body: str) -> str:
    """Replace the description while retaining the existing run history."""
    opening, header, rest = _split_header(text)
    closing, _, original = rest.partition("\n")
    section = _runs_section(original)
    proposed_section = _runs_section(body)
    if proposed_section:
        start, end = proposed_section
        body = body[:start] + body[end:]
    history = original[section[0] : section[1]] if section else ""
    return opening + header + closing + "\n" + body.rstrip() + "\n\n" + history
