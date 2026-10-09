"""Cached checks of published HAIFA bundles and one installation at a time."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from aifactory import __version__
from aifactory.library.remote import version_key
from aifactory.upgrade import UpgradeError, editable_install, run_upgrade

UPDATE_REPOSITORY = "janbkrejci/HAIFA"


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
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else os.environ.get("HAIFA_UPDATE_REPO", UPDATE_REPOSITORY)
        )
        self.current = current
        self.fetch = fetch
        self.clock = clock
        self._lock = threading.RLock()
        self._checked = float("-inf")
        self._state: dict[str, Any] = {"status": "checking", "current_version": current}
        self.installing = False

    def check(self, fresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.installing:
                return dict(self._state)
            ttl = 300 if self._state["status"] == "error" else 1800
            if not fresh and self.clock() - self._checked < ttl:
                return dict(self._state)
            try:
                release = self.fetch(self.repository)
                target = str(release.get("tag_name", "")).removeprefix("v")
                if (
                    not re.fullmatch(r"\d+\.\d+\.\d+", target)
                    or release.get("draft")
                    or release.get("prerelease")
                ):
                    raise ValueError("Vydání nemá platnou stabilní verzi.")
                filename = f"haifa-{target}.zip"
                urls = [
                    a.get("browser_download_url")
                    for a in release.get("assets", [])
                    if isinstance(a, dict) and a.get("name") == filename
                ]
                prefix = f"https://github.com/{self.repository}/releases/download/"
                if len(urls) != 1 or not isinstance(urls[0], str) or not urls[0].startswith(prefix):
                    raise ValueError("Vydání neobsahuje instalační ZIP HAIFA.")
                self._state = {
                    "status": "available"
                    if version_key(target) > version_key(self.current)
                    else "current",
                    "current_version": self.current,
                    "target_version": target,
                    "bundle": urls[0],
                    "error": None,
                }
            except Exception as exc:
                self._state = {
                    "status": "error",
                    "current_version": self.current,
                    "error": f"Kontrola aktualizací selhala: {type(exc).__name__}: {exc}",
                }
            self._checked = self.clock()
            return dict(self._state)

    def begin(self) -> dict[str, Any]:
        with self._lock:
            if self.installing:
                raise UpgradeError("update_busy", "Aktualizace již probíhá.")
            state = self.check(fresh=True)
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

    def install(self, restart: Callable[[], None]) -> None:
        try:
            result = run_upgrade(
                self._state["bundle"],
                current=self.current,
                expected_version=self._state["target_version"],
            )
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
                }
                self._checked = self.clock()

    def cancel(self) -> None:
        """Release the installation guard when a run appeared during the fresh release check."""
        with self._lock:
            self.installing = False
            self._state = {**self._state, "status": "available"}
