"""Choosing a folder to add as a repository: browse directories under home, or a native dialog.

A web page cannot learn the absolute path of a folder the user picks, so the server offers
two ways. ``list_dirs`` lists the subdirectories of a directory under the user's home
(``GET /api/fs/dirs``); a path outside home once symlinks are resolved is refused with
``outside_home``. ``FolderPicker`` opens the system's folder dialog on the server's own
display (``POST /api/fs/pick``): ``osascript`` on macOS, ``zenity`` or ``kdialog`` on Linux,
always with fixed arguments and nothing from the request. One dialog runs at a time
(``picker_busy``) and for at most ``timeout`` seconds (``picker_timeout``). Without a
graphical session (an SSH login, no ``DISPLAY`` or ``WAYLAND_DISPLAY`` on Linux) the picker
is not available (``picker_unavailable``). Neither writes anything anywhere.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory import oscompat
from aifactory.web.registry import RepoError

MAX_ENTRIES = 500
"""The most directories ``list_dirs`` returns; ``truncated`` tells there were more."""

PICK_TIMEOUT = 300.0
"""How long a folder dialog may stay open, in seconds."""

PICK_PROMPT = "Vyber složku repozitáře"


def _inside(path: Path, home: Path) -> bool:
    return path == home or home in path.parents


def _exists(path: Path) -> bool:
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def list_dirs(raw: str | None, home: Path) -> dict[str, Any]:
    """The visible subdirectories of ``raw`` (default: ``home``), which must be under ``home``.

    Hidden entries (a leading dot) and anything that is not a directory are left out, as is
    a symlink that leads outside home. At most ``MAX_ENTRIES`` are returned, sorted by name.
    ``is_git`` and ``has_factory`` come from a ``stat`` of ``.git`` and ``.factory`` only.
    """
    home = home.resolve()
    if raw is None or raw.strip() == "":
        target = home
    else:
        given = Path(raw)
        if not given.is_absolute():
            raise RepoError("invalid_value", f"path must be absolute, got {raw!r}")
        try:
            target = given.resolve(strict=True)
        except FileNotFoundError:
            raise RepoError("path_not_found", f"{raw} does not exist") from None
        except (OSError, RuntimeError, ValueError) as exc:
            raise RepoError("invalid_value", f"cannot resolve {raw!r}: {exc}") from None
    if not _inside(target, home):
        raise RepoError(
            "outside_home", f"{raw} is outside the home folder {home}", data={"home": str(home)}
        )
    if not target.is_dir():
        raise RepoError("not_a_directory", f"{target} is not a directory")
    try:
        with os.scandir(target) as listing:
            candidates = [e for e in listing if not e.name.startswith(".")]
    except PermissionError:
        raise RepoError("permission_denied", f"{target} cannot be read") from None
    candidates.sort(key=lambda e: (e.name.casefold(), e.name))
    entries: list[dict[str, Any]] = []
    truncated = False
    for entry in candidates:
        try:
            if not entry.is_dir():
                continue
            if entry.is_symlink() and not _inside(Path(entry.path).resolve(), home):
                continue
        except (OSError, RuntimeError):
            continue
        if len(entries) >= MAX_ENTRIES:
            truncated = True
            break
        path = Path(entry.path)
        entries.append(
            {
                "name": entry.name,
                "path": str(path),
                "is_git": _exists(path / ".git"),
                "has_factory": _exists(path / ".factory"),
            }
        )
    parent = None if target == home else str(target.parent)
    return {"path": str(target), "parent": parent, "entries": entries, "truncated": truncated}


@dataclass(frozen=True)
class _Dialog:
    argv: list[str]
    cancel_code: int = 1
    cancel_text: str | None = None
    """Text stderr must contain for ``cancel_code`` to mean cancel (osascript: ``-128``)."""


class FolderPicker:
    """The native folder dialog, opened by the server on its own graphical session.

    ``platform`` and ``env`` default to this process's; tests pass their own ``env`` (with
    fake dialog programs on ``PATH``) and a short ``timeout``.
    """

    def __init__(
        self,
        *,
        platform: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = PICK_TIMEOUT,
    ) -> None:
        self.platform = sys.platform if platform is None else platform
        self.env = dict(os.environ if env is None else env)
        self.timeout = timeout
        self._lock = threading.Lock()

    def _which(self, program: str) -> str | None:
        return shutil.which(program, path=self.env.get("PATH", os.defpath))

    def _remote(self) -> bool:
        return any(self.env.get(k) for k in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))

    def _dialog(self) -> _Dialog | None:
        """The command of the dialog this session can show, or ``None``."""
        if self._remote():
            return None
        if self.platform == "darwin":
            program = self._which("osascript")
            if program is None:
                return None
            script = f'POSIX path of (choose folder with prompt "{PICK_PROMPT}")'
            return _Dialog([program, "-e", script], cancel_text="-128")
        if self.platform.startswith("linux"):
            if not (self.env.get("DISPLAY") or self.env.get("WAYLAND_DISPLAY")):
                return None
            zenity = self._which("zenity")
            if zenity is not None:
                argv = [zenity, "--file-selection", "--directory", f"--title={PICK_PROMPT}"]
                return _Dialog(argv)
            kdialog = self._which("kdialog")
            if kdialog is not None:
                home = self.env.get("HOME") or str(Path.home())
                argv = [kdialog, "--title", PICK_PROMPT, "--getexistingdirectory", home]
                return _Dialog(argv)
        return None

    def available(self) -> bool:
        """Whether a dialog can be opened; looks at the environment only, runs nothing."""
        return self._dialog() is not None

    def pick(self) -> dict[str, Any]:
        """Open the dialog and wait: ``{path}`` or ``{cancelled: true}``. Blocks the thread."""
        dialog = self._dialog()
        if dialog is None:
            raise RepoError(
                "picker_unavailable",
                "no graphical session for a folder dialog (SSH login, no DISPLAY or no "
                "osascript, zenity or kdialog); browse the folders instead",
            )
        if not self._lock.acquire(blocking=False):
            raise RepoError("picker_busy", "a folder dialog is already open")
        try:
            return self._run(dialog)
        finally:
            self._lock.release()

    def _run(self, dialog: _Dialog) -> dict[str, Any]:
        proc = subprocess.Popen(
            dialog.argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
            start_new_session=True,
            creationflags=oscompat.NEW_GROUP,
            encoding="utf-8",
        )
        try:
            out, err = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            try:
                oscompat.kill_group(proc.pid, force=True)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            proc.communicate()
            raise RepoError(
                "picker_timeout",
                f"the folder dialog was not answered within {self.timeout:g} s",
            ) from None
        if proc.returncode == dialog.cancel_code and (
            dialog.cancel_text is None or dialog.cancel_text in err
        ):
            return {"cancelled": True}
        if proc.returncode != 0:
            detail = err.strip() or f"exit code {proc.returncode}"
            raise RepoError("picker_failed", f"the folder dialog failed: {detail}")
        chosen = out.strip()
        if not chosen:
            return {"cancelled": True}
        if len(chosen) > 1:
            chosen = chosen.rstrip("/")
        return {"path": chosen}
