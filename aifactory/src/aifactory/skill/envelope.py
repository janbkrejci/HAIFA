"""The one JSON envelope every ``--json`` command prints.

``{"ok": bool, "data": dict | null, "error": dict | null, "warnings": [str]}``; see
``envelope_problems`` for the rules, which are also the executable spec.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aifactory.skill.codes import ERROR_CODES

ENVELOPE_KEYS: tuple[str, ...] = ("ok", "data", "error", "warnings")
ERROR_KEYS: tuple[str, ...] = ("code", "message", "path", "id", "issues")


def envelope_ok(data: Mapping[str, Any], warnings: Iterable[str] = ()) -> dict[str, Any]:
    """A successful result."""
    return {"ok": True, "data": dict(data), "error": None, "warnings": list(warnings)}


def envelope_fail(
    code: str,
    message: str,
    *,
    data: Mapping[str, Any] | None = None,
    path: str | None = None,
    id: str | None = None,
    issues: Iterable[Mapping[str, Any]] = (),
    warnings: Iterable[str] = (),
) -> dict[str, Any]:
    """A failed command; ``data`` stays filled when a result exists."""
    error = {
        "code": code,
        "message": message or code,
        "path": path,
        "id": id,
        "issues": [dict(i) for i in issues],
    }
    return {
        "ok": False,
        "data": None if data is None else dict(data),
        "error": error,
        "warnings": list(warnings),
    }


def strip_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Split a builder payload into ``data`` (without ``ok``/``warnings``) and warnings."""
    data = {k: v for k, v in payload.items() if k not in ("ok", "warnings")}
    raw = payload.get("warnings") or []
    return data, [str(w) for w in raw]


def envelope_problems(obj: object) -> list[str]:
    """Every rule ``obj`` breaks; an empty list means a valid envelope."""
    if not isinstance(obj, dict):
        return ["the envelope is not an object"]
    problems: list[str] = []
    if sorted(obj) != sorted(ENVELOPE_KEYS):
        problems.append(f"top-level keys are {sorted(obj)}, expected {sorted(ENVELOPE_KEYS)}")
    ok = obj.get("ok")
    data = obj.get("data")
    error = obj.get("error")
    warnings = obj.get("warnings")
    if not isinstance(ok, bool):
        problems.append("ok is not a bool")
    if data is not None and not isinstance(data, dict):
        problems.append("data is neither an object nor null")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        problems.append("warnings is not a list of strings")
    if ok is True:
        if error is not None:
            problems.append("ok is true but error is not null")
        if not isinstance(data, dict):
            problems.append("ok is true but data is not an object")
    elif ok is False:
        problems.extend(_error_problems(error))
    return problems


def _error_problems(error: object) -> list[str]:
    if not isinstance(error, dict):
        return ["ok is false but error is not an object"]
    problems: list[str] = []
    if sorted(error) != sorted(ERROR_KEYS):
        problems.append(f"error keys are {sorted(error)}, expected {sorted(ERROR_KEYS)}")
    code = error.get("code")
    if not isinstance(code, str):
        problems.append("error.code is not a string")
    elif code not in ERROR_CODES:
        problems.append(f"error.code {code!r} is not a documented error code")
    message = error.get("message")
    if not isinstance(message, str) or not message:
        problems.append("error.message is not a non-empty string")
    for key in ("path", "id"):
        if error.get(key) is not None and not isinstance(error.get(key), str):
            problems.append(f"error.{key} is neither a string nor null")
    issues = error.get("issues")
    if not isinstance(issues, list):
        problems.append("error.issues is not a list")
    else:
        for n, issue in enumerate(issues):
            if not isinstance(issue, dict):
                problems.append(f"error.issues[{n}] is not an object")
            elif not isinstance(issue.get("code"), str) or not isinstance(
                issue.get("message"), str
            ):
                problems.append(f"error.issues[{n}] lacks a string code and message")
    return problems
