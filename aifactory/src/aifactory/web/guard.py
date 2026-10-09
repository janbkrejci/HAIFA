"""Write guard: reject writes under ``/api/`` from another origin or with a non-JSON body.

Every POST, PUT, PATCH and DELETE under ``/api/`` is checked before routing. ``Origin``, if
sent, must be ``http://<Host>`` of the request and ``Sec-Fetch-Site``, if sent, must be
``same-origin``; otherwise HTTP 403 ``cross_origin``. A body whose ``Content-Type`` is not
``application/json`` gets HTTP 415 ``unsupported_media_type``. Requests without ``Origin``
and ``Sec-Fetch-Site`` (CLI, curl) and a POST without a body pass; GET is not checked.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from aifactory.skill.envelope import envelope_fail

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def write_problem(headers: Headers) -> tuple[str, int, str] | None:
    """``(code, status, message)`` when a write with these headers must be rejected."""
    host = headers.get("host", "")
    origin = headers.get("origin")
    if origin is not None and origin.strip().lower() != f"http://{host}".lower():
        return "cross_origin", 403, f"Origin {origin!r} does not match http://{host}"
    site = headers.get("sec-fetch-site")
    if site is not None and site.strip().lower() != "same-origin":
        return "cross_origin", 403, f"Sec-Fetch-Site {site!r} is not same-origin"
    ctype = headers.get("content-type")
    length = headers.get("content-length", "0").strip()
    has_body = length not in ("", "0") or "transfer-encoding" in headers
    if ctype is None:
        bad = has_body
    else:
        bad = ctype.split(";", 1)[0].strip().lower() != "application/json"
    if bad:
        got = ctype or "no Content-Type"
        message = f"the request body must be application/json, got {got}"
        return "unsupported_media_type", 415, message
    return None


class WriteGuardMiddleware:
    """Reject writes under ``/api/`` from another origin or with a non-JSON body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in WRITE_METHODS
            and is_api_path(scope["path"])
        ):
            problem = write_problem(Headers(scope=scope))
            if problem is not None:
                code, status, message = problem
                response = JSONResponse(envelope_fail(code, message), status_code=status)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


RESTART_PATH = "/api/restart"


def is_restart_path(path: str) -> bool:
    """``/api/restart``, the only write a stale dashboard still accepts."""
    return path == RESTART_PATH


STALE_MESSAGE = (
    "Kód HAIFA se od spuštění dashboardu změnil. Restartuj dashboard (tlačítko v liště "
    "nebo just dash), zápisy jsou do té doby vypnuté."
)


class StaleCodeMiddleware:
    """Reject writes under ``/api/`` while the dashboard runs code older than the package on disk.

    HAIFA builds itself: a merge can replace the package under a running dashboard, whose code
    in memory would then write by stale rules. Every POST, PUT, PATCH and DELETE under ``/api/``
    except ``/api/restart`` gets HTTP 409 ``stale_code``
    until the dashboard restarts; reads keep working. The watch is ``app.state.code``
    (``codeprint.CodeWatch``).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in WRITE_METHODS
            and is_api_path(scope["path"])
        ):
            watch = getattr(getattr(scope.get("app"), "state", None), "code", None)
            updates = getattr(getattr(scope.get("app"), "state", None), "updates", None)
            if updates is not None and updates.installing:
                response = JSONResponse(
                    envelope_fail(
                        "update_busy", "Probíhá aktualizace HAIFA. Počkej na restart dashboardu."
                    ),
                    status_code=409,
                )
                await response(scope, receive, send)
                return
            if watch is not None and not is_restart_path(scope["path"]) and watch.stale():
                response = JSONResponse(envelope_fail("stale_code", STALE_MESSAGE), status_code=409)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
