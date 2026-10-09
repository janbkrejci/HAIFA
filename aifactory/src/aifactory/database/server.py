"""Public read/write SQLite service: python -m aifactory.database.server --help."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


@dataclass
class Session:
    project: str
    conn: sqlite3.Connection
    lock: Any = field(default_factory=threading.Lock)
    used: float = field(default_factory=time.monotonic)


class DatabaseServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], data: Path) -> None:
        self.data = data
        data.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()
        super().__init__(address, Handler)

    def rpc(self, body: dict[str, Any]) -> dict[str, Any]:
        project, op = body["project"], body["op"]
        if not isinstance(project, str) or not re.fullmatch(r"[a-f0-9]{64}", project):
            raise ValueError("invalid project identity")
        if op == "open":
            options = body.get("options", {})
            timeout = min(max(float(options.get("timeout", 30)), 0), 30)
            conn = sqlite3.connect(
                self.data / f"{project}.db",
                timeout=timeout,
                isolation_level=options.get("isolation_level"),
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            session = uuid.uuid4().hex
            with self.lock:
                self.sessions[session] = Session(project, conn)
            return {"session": session}
        with self.lock:
            item = self.sessions.get(body.get("session", ""))
        if item is None or item.project != project:
            raise ValueError("database session expired; reconnect")
        with item.lock:
            item.used = time.monotonic()
            if op == "close":
                item.conn.close()
                with self.lock:
                    self.sessions.pop(body["session"], None)
                return {}
            if op in {"commit", "rollback"}:
                getattr(item.conn, op)()
                return {"in_transaction": item.conn.in_transaction}
            if op == "execute":
                cursor = item.conn.execute(body["sql"], body.get("parameters", []))
            elif op == "script":
                cursor = item.conn.executescript(body["sql"])
            else:
                raise ValueError("unknown database operation")
            return {
                "rows": cursor.fetchall(),
                "description": cursor.description,
                "lastrowid": cursor.lastrowid,
                "rowcount": cursor.rowcount,
                "in_transaction": item.conn.in_transaction,
            }

    def service_actions(self) -> None:
        # Crashed/disconnected clients must not retain write transactions forever.
        with self.lock:
            expired = [
                (key, item)
                for key, item in self.sessions.items()
                if time.monotonic() - item.used > 120
            ]
        for key, item in expired:
            if item.lock.acquire(blocking=False):
                try:
                    if time.monotonic() - item.used > 120:
                        item.conn.close()
                        with self.lock:
                            self.sessions.pop(key, None)
                finally:
                    item.lock.release()

    def server_close(self) -> None:
        super().server_close()
        for item in self.sessions.values():
            with item.lock:
                item.conn.close()
        self.sessions.clear()


class Handler(BaseHTTPRequestHandler):
    server: DatabaseServer

    def do_POST(self) -> None:
        result: dict[str, Any]
        try:
            if self.path != "/rpc":
                raise ValueError("unknown endpoint")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16 * 1024 * 1024:
                raise ValueError("invalid request size")
            body = json.loads(self.rfile.read(size))
            result = self.server.rpc(body)
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            result = {"error": str(exc), "kind": type(exc).__name__}
        encoded = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="HAIFA public read/write shared database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4710, type=int)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    with DatabaseServer((args.host, args.port), args.data_dir) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
