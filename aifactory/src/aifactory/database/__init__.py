"""SQLite connections, optionally executed by a shared HAIFA database service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

import yaml

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.home import haifa_home

_ENDPOINTS: dict[str, tuple[str, str]] = {}
MACHINE = hashlib.sha256(f"{socket.gethostname()}:{uuid.getnode()}".encode()).hexdigest()


def canonical_remote(remote: str) -> str:
    """Join HTTPS/SSH spellings; retain repository path case and nonstandard ports."""
    text = remote.strip().rstrip("/")
    if "://" not in text:
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", text)
        if match:
            text = f"ssh://{match[1]}/{match[2]}"
    parsed = urlsplit(text)
    if parsed.scheme not in {"https", "http", "ssh", "git"} or not parsed.hostname:
        raise ValueError("shared database requires a network Git remote")
    port = parsed.port
    default = {"https": 443, "http": 80, "ssh": 22, "git": 9418}[parsed.scheme]
    host = parsed.hostname.lower() + (f":{port}" if port and port != default else "")
    path = parsed.path.strip("/").removesuffix(".git")
    if not path:
        raise ValueError("Git remote has no repository path")
    return f"{host}/{path}"


def database_path(root: Path, local: Path, url: str | None = None) -> Path:
    """Global database.yaml / HAIFA_DATABASE_URL, with an optional local override."""
    label = str(haifa_home() / "database.yaml")
    try:
        if url is None:
            url = os.environ.get("HAIFA_DATABASE_URL")
        if url is None and Path(label).is_file():
            data = yaml.safe_load(Path(label).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"url"}:
                raise ValueError("expected a mapping containing only 'url'")
            url = data["url"]
        if url is None:
            _ENDPOINTS.pop(str(local), None)
            return local
        if not isinstance(url, str):
            raise ValueError("database URL must be a string")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("database URL must use http:// or https://")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("database URL must not contain credentials, query or fragment")
        from aifactory.run.gitops import read_git

        config = root / ".factory/config.yaml"
        settings = yaml.safe_load(config.read_text(encoding="utf-8")) if config.is_file() else {}
        if settings is not None and not isinstance(settings, dict):
            raise ValueError("factory configuration must be a mapping")
        name = (settings or {}).get("remote", "origin")
        remote = read_git(root, "remote", "get-url", name)
        if not remote:
            raise ValueError(f"shared database requires Git remote {name!r}")
        project = hashlib.sha256(canonical_remote(remote).encode()).hexdigest()
        endpoint_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = root / ".factory/data/remote-db" / endpoint_id / f"{project}.db"
        _ENDPOINTS[str(path)] = (url.rstrip("/"), project)
        return path
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ConfigError([ConfigIssue(label, str(exc))]) from exc


def is_remote(path: str | Path) -> bool:
    return str(path) in _ENDPOINTS


def available(path: Path) -> bool:
    return is_remote(path) or path.is_file()


class RemoteCursor:
    def __init__(self, connection: RemoteConnection, result: dict[str, Any]) -> None:
        self.connection = connection
        self.description = result.get("description")
        self.lastrowid = result.get("lastrowid")
        self.rowcount = result.get("rowcount", -1)
        self._rows = iter(result.get("rows", []))
        self._metadata: sqlite3.Cursor | None = None

    def fetchone(self) -> Any:
        values = next(self._rows, None)
        if values is None:
            return None
        row = tuple(values)
        if self.connection.row_factory is sqlite3.Row:
            # SQLite Row needs a native cursor's description, but no native data.
            if self._metadata is None:
                conn = sqlite3.connect(":memory:")
                try:
                    self._metadata = conn.execute(
                        "SELECT "
                        + ", ".join(
                            'NULL AS "' + c[0].replace('"', '""') + '"'
                            for c in (self.description or [])
                        )
                    )
                finally:
                    conn.close()
            return sqlite3.Row(self._metadata, row)
        return row

    def fetchall(self) -> list[Any]:
        return list(self)

    def __iter__(self) -> Iterator[Any]:
        while (row := self.fetchone()) is not None:
            yield row


class RemoteConnection:
    """A DB-API subset: transactions remain on one server-side SQLite connection."""

    def __init__(self, url: str, project: str, options: dict[str, Any]) -> None:
        self.url = url
        self.project = project
        self.row_factory: Any = None
        self.timeout = max(float(options.get("timeout", 30)), 30) + 5
        self._lock = threading.RLock()
        self._closed = False
        self._options = options
        self._in_transaction = False
        self.session = self._request("open", options=options)["session"]

    def _request(self, op: str, **kwargs: Any) -> dict[str, Any]:
        body = {"op": op, "project": self.project, **kwargs}
        if hasattr(self, "session"):
            body["session"] = self.session
        request = Request(
            self.url + "/rpc",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
            method="POST",
        )
        with self._lock:
            if self._closed:
                raise sqlite3.ProgrammingError("connection is closed")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result: dict[str, Any] = json.load(response)
            except (URLError, HTTPError, OSError, ValueError) as exc:
                raise sqlite3.OperationalError(f"shared database unavailable: {exc}") from exc
        if result.get("error", "").startswith("database session expired"):
            if op == "close":
                return {}
            if not self._in_transaction:
                self.session = self._request("open", options=self._options)["session"]
                return self._request(op, **kwargs)
        if "error" in result:
            kind = result.get("kind")
            error = sqlite3.IntegrityError if kind == "IntegrityError" else sqlite3.OperationalError
            raise error(result["error"])
        self._in_transaction = result.get("in_transaction", self._in_transaction)
        return result

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> RemoteCursor:
        return RemoteCursor(self, self._request("execute", sql=sql, parameters=list(parameters)))

    def executescript(self, sql: str) -> RemoteCursor:
        return RemoteCursor(self, self._request("script", sql=sql))

    def commit(self) -> None:
        self._request("commit")

    def rollback(self) -> None:
        self._request("rollback")

    def close(self) -> None:
        if not self._closed:
            try:
                self._request("close")
            finally:
                self._closed = True


def connect(database: str | Path, **options: Any) -> sqlite3.Connection:
    """Keep the existing native SQLite interface and error types for local callers."""
    raw = str(database)
    path = unquote(raw[5:].split("?", 1)[0]) if raw.startswith("file:") else raw
    endpoint = _ENDPOINTS.get(path)
    if endpoint is None:
        return cast(sqlite3.Connection, sqlite3.connect(database, **options))
    options = {key: value for key, value in options.items() if key != "uri"}
    return cast(sqlite3.Connection, RemoteConnection(*endpoint, options))
