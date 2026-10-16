"""The guide's only way to data: an allowlist of read-only ``factory`` commands and SQL.

The dashboard guide (``assistant.py``) runs as a coding agent that may execute exactly one
command, the ``guide`` script in its working directory, which calls ``main`` here::

    guide repos                          the registered repositories
    guide factory REPO COMMAND...        one allowed factory command with --json in REPO
    guide sql REPO "SELECT ..."          one read-only query on the trace DB of REPO

``REPO`` is the id of a registered repository (``dashboard.yaml`` in the HAIFA home); ``-``
is accepted for the library commands, which need no repository. Allowed commands are
``ALLOWED``: ``task list/show/runs``, ``backlog list/check``, ``check``, ``config show``,
``library list/show`` and ``workflow show`` (answered here: the workflow YAML of the
repository, else of the package). Anything else, ``--repo`` and any argument naming an
``.env`` file, is refused with exit code 2. The SQL connection is opened read-only with an
authorizer that permits reading only; a shared database server is not queried.

Every output passes ``redact``: values of ``.env`` files of the registered repositories and
of the HAIFA home, and of secret-looking environment variables, become ``[redacted]``.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from aifactory.home import haifa_home

ALLOWED: tuple[tuple[str, ...], ...] = (
    ("task", "list"),
    ("task", "show"),
    ("task", "runs"),
    ("backlog", "list"),
    ("backlog", "check"),
    ("check",),
    ("config", "show"),
    ("library", "list"),
    ("library", "show"),
    ("workflow", "show"),
)
NO_REPO: tuple[tuple[str, ...], ...] = (("library", "list"), ("library", "show"))
MAX_OUTPUT = 200_000
MAX_ROWS = 200
MAX_CELL = 4_000
TIMEOUT_S = 120
REDACTED = "[redacted]"
_SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE|CREDENTIAL|AUTH)", re.I)
_WORKFLOW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


class Refused(Exception):
    """A command the guide may not run."""


def allowed_label() -> str:
    """The allowlist as text for the guide's prompt."""
    return ", ".join(f"`{' '.join(c)}`" for c in ALLOWED)


def check_command(args: Sequence[str]) -> tuple[str, ...]:
    """The allowlist entry ``args`` starts with; ``Refused`` for anything else."""
    words = [str(a) for a in args]
    match = next((c for c in ALLOWED if tuple(words[: len(c)]) == c), None)
    if match is None:
        raise Refused(f"command not allowed: factory {' '.join(words)}".rstrip())
    for word in words[len(match) :]:
        if word == "--repo" or word.startswith("--repo="):
            raise Refused("--repo is not allowed; name the repository by its id")
        if ".env" in word.lower():
            raise Refused("secrets are not available to the guide")
    return match


# ── secrets ──────────────────────────────────────────────────────────────────────────────


def _env_values(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    values = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        value = line.split("=", 1)[1].strip().strip("'\"")
        if len(value) >= 4:
            values.append(value)
    return values


def secrets(roots: Iterable[Path], home: Path | None = None) -> list[str]:
    """Values that must never reach the guide, longest first."""
    found: set[str] = set()
    for root in [*roots, home if home is not None else haifa_home()]:
        try:
            files = [p for p in root.glob(".env*") if p.is_file()]
        except OSError:
            continue
        for path in files:
            found.update(_env_values(path))
    for name, value in os.environ.items():
        if _SECRET_NAME.search(name) and len(value) >= 8:
            found.add(value)
    return sorted(found, key=len, reverse=True)


def redact(text: str, values: Iterable[str]) -> str:
    for value in values:
        if value and value in text:
            text = text.replace(value, REDACTED)
    return text


# ── repositories ─────────────────────────────────────────────────────────────────────────


def registered(home: Path | None = None) -> dict[str, Path]:
    """Registered repository id -> path."""
    from aifactory.web.registry import Registry

    state = Registry(home if home is not None else haifa_home()).snapshot()[0]
    return {entry.id: Path(entry.path) for entry in state.repos}


def _repo(repos: dict[str, Path], repo_id: str) -> Path:
    if repo_id not in repos:
        raise Refused(f"unknown repository {repo_id!r}; see `guide repos`")
    return repos[repo_id]


# ── commands ─────────────────────────────────────────────────────────────────────────────


def workflow_show(root: Path | None, name: str) -> dict[str, Any]:
    """The YAML of workflow ``name``: the repository's own, else the packaged default."""
    from aifactory.workflow.parse import DEFAULT_WORKFLOWS_DIR

    if not _WORKFLOW_NAME.match(name) or ".." in name:
        raise Refused(f"invalid workflow name {name!r}")
    own = root / ".factory/workflows" / f"{name}.yaml" if root else None
    if own is not None and own.is_file():
        return {"name": name, "source": "repo", "yaml": own.read_text(encoding="utf-8")}
    path = DEFAULT_WORKFLOWS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise Refused(f"unknown workflow {name!r}")
    return {"name": name, "source": "package", "yaml": path.read_text(encoding="utf-8")}


def run_factory(
    repos: dict[str, Path], repo_id: str, args: Sequence[str], *, run_id: str = ""
) -> tuple[int, str]:
    """Run one allowed factory command; ``(exit code, stdout)``."""
    match = check_command(args)
    if repo_id == "-":
        if match not in NO_REPO:
            raise Refused(f"factory {' '.join(match)} needs a repository id")
        cwd: Path | None = None
    else:
        cwd = _repo(repos, repo_id)
    words = [str(a) for a in args]
    if match == ("workflow", "show"):
        if len(words) != 3:
            raise Refused("usage: factory workflow show NAME")
        data = workflow_show(cwd, words[2])
        return 0, json.dumps({"ok": True, "data": data}, ensure_ascii=False)
    if "--json" not in words:
        words.append("--json")
    env = {**os.environ, "HAIFA_RUN_ID": run_id or os.environ.get("HAIFA_RUN_ID", "guide")}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "aifactory", *words],
            cwd=str(cwd) if cwd else str(haifa_home()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return 1, json.dumps({"ok": False, "error": f"timed out after {TIMEOUT_S}s"})
    output = result.stdout or result.stderr
    return result.returncode, output[:MAX_OUTPUT]


class _ReadOnly:
    READ = frozenset(
        {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            getattr(sqlite3, "SQLITE_RECURSIVE", 33),
        }
    )

    def __call__(self, action: int, *_: object) -> int:
        return sqlite3.SQLITE_OK if action in self.READ else sqlite3.SQLITE_DENY


def run_sql(repos: dict[str, Path], repo_id: str, query: str) -> dict[str, Any]:
    """Rows of one read-only query on the trace DB of ``repo_id``."""
    from aifactory import database
    from aifactory.web.repos import trace_db_of

    root = _repo(repos, repo_id)
    path = trace_db_of(root)
    if database.is_remote(path):
        raise Refused("the trace DB is on a shared database server; use factory commands")
    if not path.is_file():
        raise Refused(f"repository {repo_id!r} has no trace DB yet")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_ReadOnly())
        try:
            cursor = conn.execute(query)
        except (sqlite3.DatabaseError, sqlite3.Warning) as exc:
            raise Refused(f"query refused: {exc}") from exc
        columns = [d[0] for d in cursor.description or ()]
        rows = cursor.fetchmany(MAX_ROWS + 1)
    finally:
        conn.close()

    def cell(value: object) -> object:
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        if isinstance(value, str) and len(value) > MAX_CELL:
            return value[:MAX_CELL] + "…"
        return value

    return {
        "columns": columns,
        "rows": [[cell(v) for v in row] for row in rows[:MAX_ROWS]],
        "truncated": len(rows) > MAX_ROWS,
    }


USAGE = (
    'usage: guide repos | guide factory REPO COMMAND... | guide sql REPO "SELECT ..."\n'
    f"allowed factory commands: {', '.join(' '.join(c) for c in ALLOWED)}"
)


def execute(argv: Sequence[str], home: Path | None = None) -> tuple[int, str]:
    """``(exit code, output)`` of one guide command; the output is already redacted."""
    repos = registered(home)
    values = secrets(repos.values(), home)
    run_id = os.environ.get("HAIFA_RUN_ID", "guide")
    try:
        if list(argv[:1]) == ["repos"] and len(argv) == 1:
            listed = [{"id": key, "path": str(path)} for key, path in repos.items()]
            code, out = 0, json.dumps({"ok": True, "data": listed}, ensure_ascii=False)
        elif len(argv) >= 3 and argv[0] == "factory":
            code, out = run_factory(repos, argv[1], argv[2:], run_id=run_id)
        elif len(argv) == 3 and argv[0] == "sql":
            data = run_sql(repos, argv[1], argv[2])
            code, out = 0, json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)
        else:
            raise Refused(USAGE)
    except Refused as exc:
        return 2, json.dumps({"ok": False, "error": {"code": "refused", "message": str(exc)}})
    return code, redact(out, values)


def main(argv: Sequence[str] | None = None) -> int:
    code, out = execute(list(sys.argv[1:] if argv is None else argv))
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
