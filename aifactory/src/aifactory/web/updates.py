"""Cached checks of published HAIFA bundles and one installation at a time."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aifactory import __version__
from aifactory.library.remote import version_key
from aifactory.upgrade import UpgradeError, editable_install, run_upgrade
from aifactory.web.server import RESTART_ENV, exit_process, restart_command

UPDATE_REPOSITORY = "janbkrejci/HAIFA"
MIGRATION_REPOSITORY = "janbkrejci/GIRO"


def latest_release(repository: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Zdroj aktualizací není nastavený správně.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "HAIFA-update-check"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("Server vrátil neplatné informace o vydání.")
    return data


class Updates:
    def __init__(
        self,
        *,
        repository: str | None = None,
        current: str = __version__,
        fetch: Callable[[str], dict[str, Any]] = latest_release,
        clock: Callable[[], float] = time.monotonic,
        home: Path | None = None,
    ) -> None:
        legacy = os.environ.get("HAIFA_UPDATE_REPO")
        giro = current.startswith("1.")
        self.repository = (
            repository
            if repository is not None
            else (
                (
                    os.environ.get("GIRO_UPDATE_REPO")
                    or (legacy if legacy != "janbkrejci/HAIFA" else None)
                    or MIGRATION_REPOSITORY
                )
                if giro
                else (legacy or UPDATE_REPOSITORY)
            )
        )
        self.current = current
        self.home = home
        self.fetch = fetch
        self.clock = clock
        self._lock = threading.RLock()
        self._checked = float("-inf")
        self._state: dict[str, Any] = {"status": "checking", "current_version": current}
        self.installing = False

    def check(self, fresh: bool = False, *, migration: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.installing:
                return dict(self._state)
            if self.home is not None and not fresh:
                from aifactory.transition import ERROR_FILE

                error_file = self.home / ERROR_FILE
                if error_file.exists():
                    try:
                        detail = json.loads(error_file.read_text("utf-8"))["error"]
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        detail = f"Cannot read transition recovery diagnostic: {exc}"
                    self._state = {
                        "status": "error",
                        "current_version": self.current,
                        "error": detail,
                    }
                    return dict(self._state)
            ttl = 300 if self._state["status"] == "error" else 1800
            if not fresh and self.clock() - self._checked < ttl:
                return dict(self._state)
            try:
                repository = MIGRATION_REPOSITORY if migration else self.repository
                release = self.fetch(repository)
                target = str(release.get("tag_name", "")).removeprefix("v")
                if (
                    not re.fullmatch(r"\d+\.\d+\.\d+", target)
                    or release.get("draft")
                    or release.get("prerelease")
                ):
                    raise ValueError("Vydání nemá platnou stabilní verzi.")
                if migration and not target.startswith("1."):
                    raise ValueError("Přechod vyžaduje stabilní GIRO řady 1.x.")
                brand = "giro" if migration or self.current.startswith("1.") else "haifa"
                filename = f"{brand}-{target}.zip"
                urls = [
                    a.get("browser_download_url")
                    for a in release.get("assets", [])
                    if isinstance(a, dict) and a.get("name") == filename
                ]
                expected = f"https://github.com/{repository}/releases/download/{release.get('tag_name')}/{filename}"
                if len(urls) != 1 or urls[0] != expected:
                    raise ValueError(f"Vydání neobsahuje platný instalační ZIP {filename}.")
                self._state = {
                    "status": "available"
                    if version_key(target) > version_key(self.current)
                    else "current",
                    "current_version": self.current,
                    "target_version": target,
                    "bundle": urls[0],
                    "error": None,
                    "migration": migration,
                }
            except Exception as exc:
                self._state = {
                    "status": "error",
                    "current_version": self.current,
                    "error": f"Kontrola aktualizací selhala: {type(exc).__name__}: {exc}",
                }
            self._checked = self.clock()
            return dict(self._state)

    def begin(self, migration: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.installing:
                raise UpgradeError("update_busy", "Aktualizace již probíhá.")
            if migration and not self.current.startswith("0.1."):
                raise UpgradeError(
                    "update_unavailable", "Přechod je dostupný pouze z poslední HAIFA řady 0.1."
                )
            state = self.check(fresh=True, migration=migration)
            if state["status"] != "available":
                raise UpgradeError(
                    "update_unavailable", state.get("error") or "Nová aktualizace není k dispozici."
                )
            if editable_install():
                raise UpgradeError(
                    "editable_install",
                    "Toto je vývojová instalace ze zdrojů. Aktualizuj ji pomocí git pull "
                    "a uv sync; automatická instalace je dostupná pro distribuční "
                    "instalaci přes uv tool.",
                )
            self.installing = True
            self._state = {**state, "status": "installing"}
            return dict(self._state)

    def install(
        self, restart: Callable[[], None], leave: Callable[[], None] = exit_process
    ) -> None:
        """Install the release and ``restart``; on Windows hand it off and ``leave``.

        The handoff script installs once this process has exited and starts the dashboard
        with the same command line again.
        """
        try:
            if self._state.get("migration"):
                from aifactory.transition import prepare

                if self.home is None:
                    raise UpgradeError("migration_unsafe", "Dashboard home is unavailable.")
                prepare(
                    self.home, self._state["bundle"], self.current, self._state["target_version"]
                )
                leave()
                return
            result = run_upgrade(
                self._state["bundle"],
                current=self.current,
                expected_version=self._state["target_version"],
                environ={**os.environ, RESTART_ENV: "1"},
                restart=restart_command(),
                bundle_brand="giro" if self.current.startswith("1.") else None,
            )
            if result.handed_off:
                leave()
                return
            if not result.installed:
                raise UpgradeError("upgrade_failed", "Aktualizace nebyla nainstalovaná.")
            restart()
        except Exception as exc:
            with self._lock:
                self.installing = False
                self._state = {
                    **self._state,
                    "status": "error",
                    "error": f"Aktualizace selhala: {exc}",
                    "error_code": exc.code
                    if isinstance(exc, UpgradeError) and exc.code in {"runs_active", "update_busy"}
                    else "install_failed",
                }
                self._checked = self.clock()

    def cancel(self) -> None:
        """Release the installation guard when a run appeared during the fresh release check."""
        with self._lock:
            self.installing = False
            self._state = {**self._state, "status": "available"}
