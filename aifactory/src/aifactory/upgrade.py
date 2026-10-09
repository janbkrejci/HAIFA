"""`factory upgrade BUNDLE`: install a newer HAIFA from a ``haifa-<version>.zip`` bundle.

The bundle (a path, or an ``https``/``file`` URL) is downloaded and unpacked into a temporary
directory, every file listed in ``SHA256SUMS`` is verified, the target version is read from
the wheel's metadata and compared with the running ``__version__``. Then, unless dry run,
``uv tool install --force <wheel> --constraints constraints.txt`` runs in the unpacked bundle,
exactly like the bundle's ``install.sh``. An editable install (development from the repo) is
refused: it is updated with ``git pull``.
"""

from __future__ import annotations

import email.parser
import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

from aifactory import __version__
from aifactory.library.remote import library_min_factory_version, version_key

SUMS_FILE = "SHA256SUMS"
CONSTRAINTS_FILE = "constraints.txt"
DISTRIBUTION = "aifactory"
URL_SCHEMES = ("https", "file")
DOWNLOAD_TIMEOUT = 60.0
RESTART_HINT = "restart a running dashboard (factory obs) to load the new version"


class UpgradeError(Exception):
    """An expected failure of `factory upgrade` with a stable ``code`` and exit code."""

    def __init__(
        self, code: str, message: str, exit_code: int = 2, data: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.data = dict(data) if data is not None else None


@dataclass
class UpgradeResult:
    """What `factory upgrade` found and did."""

    bundle: str
    current_version: str
    target_version: str
    wheel: str
    min_factory_version: str | None
    command: list[str]
    dry_run: bool
    installed: bool = False
    stdout: str = ""
    stderr: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle,
            "current_version": self.current_version,
            "target_version": self.target_version,
            "wheel": self.wheel,
            "min_factory_version": self.min_factory_version,
            "command": self.command,
            "dry_run": self.dry_run,
            "installed": self.installed,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "restart_dashboard": self.installed,
        }


# ── editable install ──────────────────────────────────────────────────────────


def editable_from_direct_url(text: str | None) -> bool:
    """Whether a ``direct_url.json`` (PEP 610) describes an editable install."""
    if not text:
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    info = data.get("dir_info") if isinstance(data, dict) else None
    return isinstance(info, dict) and info.get("editable") is True


def editable_install() -> bool:
    """Whether the running ``aifactory`` is an editable install (development from the repo)."""
    try:
        dist = metadata.distribution(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return False
    return editable_from_direct_url(dist.read_text("direct_url.json"))


# ── fetch and unpack ──────────────────────────────────────────────────────────


def _is_url(source: str) -> bool:
    return "://" in source


def fetch_bundle(source: str, workdir: Path) -> Path:
    """The bundle zip as a local file: a path as is, a URL downloaded into ``workdir``."""
    if not _is_url(source):
        path = Path(source).expanduser()
        if not path.is_file():
            raise UpgradeError("bundle_invalid", f"the bundle {source} does not exist")
        return path
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme.lower() not in URL_SCHEMES:
        raise UpgradeError(
            "invalid_url",
            f"the bundle URL must use https or file, not {parsed.scheme or '(none)'}: {source}",
        )
    name = PurePosixPath(urllib.parse.unquote(parsed.path)).name or "bundle.zip"
    target = workdir / name
    try:
        with (
            urllib.request.urlopen(source, timeout=DOWNLOAD_TIMEOUT) as response,  # noqa: S310
            target.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpgradeError("download_failed", f"cannot download {source}: {exc}") from exc
    return target


def unpack_bundle(zip_path: Path, dest: Path) -> Path:
    """Unpack ``zip_path`` into ``dest``; the directory holding ``SHA256SUMS``."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                parts = PurePosixPath(info.filename).parts
                if info.filename.startswith(("/", "\\")) or ".." in parts or ":" in info.filename:
                    raise UpgradeError(
                        "bundle_invalid", f"the bundle has an unsafe path: {info.filename}"
                    )
            zf.extractall(dest)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError) as exc:
        raise UpgradeError("bundle_invalid", f"{zip_path} is not a valid zip: {exc}") from exc
    if (dest / SUMS_FILE).is_file():
        return dest
    found = sorted(p.parent for p in dest.glob(f"*/{SUMS_FILE}") if p.is_file())
    if len(found) != 1:
        raise UpgradeError("bundle_invalid", f"the bundle has no {SUMS_FILE}")
    return found[0]


def verify_checksums(root: Path) -> dict[str, str]:
    """Check every file of ``SHA256SUMS``; the ``name -> digest`` map."""
    sums: dict[str, str] = {}
    try:
        text = (root / SUMS_FILE).read_text("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UpgradeError("bundle_invalid", f"cannot read {SUMS_FILE}: {exc}") from exc
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, sep, name = line.partition("  ")
        name = name.removeprefix("*")
        if not sep or not name or len(digest) != 64 or "/" in name or name in (".", ".."):
            raise UpgradeError("bundle_invalid", f"{SUMS_FILE} has a malformed line: {line!r}")
        sums[name] = digest.lower()
    if not sums:
        raise UpgradeError("bundle_invalid", f"{SUMS_FILE} lists no files")
    for name, digest in sums.items():
        path = root / name
        if not path.is_file():
            raise UpgradeError("bundle_invalid", f"the bundle lacks {name} listed in {SUMS_FILE}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise UpgradeError(
                "checksum_mismatch",
                f"{name}: SHA-256 {actual} differs from {digest} in {SUMS_FILE}",
                data={"file": name, "expected": digest, "actual": actual},
            )
    return sums


def find_wheel(root: Path, sums: Mapping[str, str]) -> str:
    """The one ``aifactory`` wheel of the bundle (covered by ``SHA256SUMS``)."""
    wheels = sorted(n for n in sums if n.startswith(f"{DISTRIBUTION}-") and n.endswith(".whl"))
    if len(wheels) != 1:
        raise UpgradeError(
            "bundle_invalid",
            f"the bundle must list exactly one {DISTRIBUTION} wheel in {SUMS_FILE}, "
            f"found {len(wheels)}",
        )
    if CONSTRAINTS_FILE not in sums:
        raise UpgradeError("bundle_invalid", f"the bundle lacks {CONSTRAINTS_FILE}")
    return wheels[0]


def wheel_version(wheel: Path) -> str:
    """``Version`` from the wheel's ``*.dist-info/METADATA``."""
    try:
        with zipfile.ZipFile(wheel) as zf:
            names = [
                n for n in zf.namelist() if n.count("/") == 1 and n.endswith(".dist-info/METADATA")
            ]
            if len(names) != 1:
                raise UpgradeError("bundle_invalid", f"{wheel.name} has no dist-info METADATA")
            raw = zf.read(names[0]).decode("utf-8")
    except (zipfile.BadZipFile, OSError, UnicodeDecodeError, EOFError) as exc:
        raise UpgradeError("bundle_invalid", f"{wheel.name} is not a valid wheel: {exc}") from exc
    meta = email.parser.Parser().parsestr(raw, headersonly=True)
    name = (meta.get("Name") or "").strip().lower().replace("_", "-")
    version = (meta.get("Version") or "").strip()
    if name != DISTRIBUTION or not version:
        raise UpgradeError("bundle_invalid", f"{wheel.name} is not an {DISTRIBUTION} wheel")
    return version


# ── upgrade ───────────────────────────────────────────────────────────────────


def install_command(wheel: str) -> list[str]:
    return ["uv", "tool", "install", "--force", wheel, "--constraints", CONSTRAINTS_FILE]


def run_upgrade(
    source: str,
    *,
    dry_run: bool = False,
    current: str = __version__,
    expected_version: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> UpgradeResult:
    """Install HAIFA from the bundle ``source`` (path or URL); see the module docstring."""
    if editable_install():
        raise UpgradeError(
            "editable_install",
            "factory runs from an editable install (development from the repo); "
            "update it with git pull instead",
            data={"current_version": current},
        )
    with tempfile.TemporaryDirectory(prefix="haifa-upgrade-") as tmp:
        work = Path(tmp)
        zip_path = fetch_bundle(source, work)
        root = unpack_bundle(zip_path, work / "bundle")
        sums = verify_checksums(root)
        wheel = find_wheel(root, sums)
        target = wheel_version(root / wheel)
        if expected_version is not None and target != expected_version:
            raise UpgradeError(
                "bundle_invalid",
                "The bundle version does not match the published release; nothing installed.",
            )
        minimum = library_min_factory_version(environ)
        versions = {"current_version": current, "target_version": target}
        if version_key(target) <= version_key(current):
            raise UpgradeError(
                "up_to_date",
                f"the bundle has HAIFA {target}, installed is {current}; nothing to upgrade",
                exit_code=1,
                data={**versions, "min_factory_version": minimum},
            )
        result = UpgradeResult(
            bundle=source,
            current_version=current,
            target_version=target,
            wheel=wheel,
            min_factory_version=minimum,
            command=install_command(wheel),
            dry_run=dry_run,
        )
        if minimum is not None and version_key(target) < version_key(minimum):
            result.warnings.append(f"the library needs factory {minimum}, the bundle has {target}")
        if dry_run:
            return result
        uv = shutil.which("uv")
        if uv is None:
            raise UpgradeError(
                "uv_missing",
                "uv is not on PATH; install it (https://docs.astral.sh/uv/) and run again",
                data={**versions, "command": result.command},
            )
        try:
            proc = subprocess.run(
                [uv, *result.command[1:]],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except OSError as exc:
            raise UpgradeError(
                "upgrade_failed",
                f"uv could not be started: {exc}",
                exit_code=1,
                data={**versions, "command": result.command},
            ) from exc
        result.stdout = proc.stdout
        result.stderr = proc.stderr
        if proc.returncode != 0:
            raise UpgradeError(
                "upgrade_failed",
                f"uv tool install exited with {proc.returncode}; HAIFA {current} stays installed",
                exit_code=1,
                data={**result.to_json(), "returncode": proc.returncode},
            )
        result.installed = True
        return result
