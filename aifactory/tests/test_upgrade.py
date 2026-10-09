"""`factory upgrade BUNDLE`: bundles built here, a fake `uv` on PATH, no network."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aifactory import __version__, upgrade
from aifactory.cli import main
from aifactory.library.remote import library_min_factory_version, version_key
from aifactory.skill import ERROR_CODES, envelope_problems, render_skill
from fake_exe import make_executable

Capsys = pytest.CaptureFixture[str]
FAKE_UV = '#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "$UV_LOG"\nexit "${UV_EXIT:-0}"\n'
NEWER = ".".join(str(n) for n in (*version_key(__version__)[:-1], version_key(__version__)[-1] + 1))


def _wheel(version: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("aifactory/__init__.py", f'__version__ = "{version}"\n')
        zf.writestr(
            f"aifactory-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: aifactory\nVersion: {version}\n",
        )
    return buf.getvalue()


def make_bundle(
    out: Path,
    version: str = NEWER,
    *,
    tamper: str | None = None,
    drop: str | None = None,
) -> Path:
    """A ``haifa-<version>.zip`` laid out like ``bundle/build.py`` makes it."""
    wheel = f"aifactory-{version}-py3-none-any.whl"
    files = {
        wheel: _wheel(version),
        "constraints.txt": b"pyyaml==6.0.3\n",
        "install.sh": b"#!/usr/bin/env bash\n",
        "INSTALL.md": b"# Instalace\n",
        "THIRD_PARTY_NOTICES": b"notices\n",
    }
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())
    ).encode()
    if tamper is not None:
        files[tamper] = b"evil==1\n"
    if drop is not None:
        files.pop(drop)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"haifa-{version}.zip"
    with zipfile.ZipFile(target, "w") as zf:
        for name, data in sorted(files.items()):
            zf.writestr(f"haifa-{version}/{name}", data)
    return target


@pytest.fixture(autouse=True)
def _not_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upgrade, "editable_install", lambda: False)


@pytest.fixture
def uv_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(FAKE_UV, encoding="utf-8", newline="\n")
    make_executable(uv)
    log = tmp_path / "uv.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("UV_LOG", str(log))
    monkeypatch.delenv("UV_EXIT", raising=False)
    return log


def _run(capsys: Capsys, *args: str) -> tuple[int, dict[str, Any]]:
    code = main(["upgrade", *args, "--json"])
    obj = json.loads(capsys.readouterr().out)
    assert envelope_problems(obj) == []
    if not obj["ok"]:
        assert obj["error"]["code"] in ERROR_CODES
    return code, obj


def test_newer_version_installs_with_uv(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle))
    assert code == 0 and obj["ok"]
    data = obj["data"]
    wheel = f"aifactory-{NEWER}-py3-none-any.whl"
    assert data["current_version"] == __version__
    assert data["target_version"] == NEWER
    assert data["installed"] is True and data["restart_dashboard"] is True
    assert data["min_factory_version"] is None
    assert data["command"] == [
        "uv",
        "tool",
        "install",
        "--force",
        wheel,
        "--constraints",
        "constraints.txt",
    ]
    assert "dashboard" in data["next"]
    cwd, argv = uv_log.read_text("utf-8").strip().split("|")
    assert argv == f"tool install --force {wheel} --constraints constraints.txt"
    assert Path(cwd).name == f"haifa-{NEWER}"
    assert not Path(cwd).exists()  # the temporary directory is gone


def test_text_output_reminds_restart(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist")
    assert main(["upgrade", str(bundle)]) == 0
    out = capsys.readouterr().out
    assert __version__ in out and NEWER in out
    assert "uv tool install --force" in out
    assert "restart" in out


def test_same_version_is_up_to_date(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist", version=__version__)
    code, obj = _run(capsys, str(bundle))
    assert code == 1 and obj["error"]["code"] == "up_to_date"
    assert obj["data"]["target_version"] == __version__
    assert not uv_log.exists()


def test_published_version_must_match_wheel(tmp_path: Path, uv_log: Path) -> None:
    bundle = make_bundle(tmp_path / "dist")
    with pytest.raises(upgrade.UpgradeError) as error:
        upgrade.run_upgrade(str(bundle), expected_version="999.0.0")
    assert error.value.code == "bundle_invalid"
    assert not uv_log.exists()


def test_older_version_is_up_to_date(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist", version="0.0.1")
    code, obj = _run(capsys, str(bundle))
    assert code == 1 and obj["error"]["code"] == "up_to_date"
    assert not uv_log.exists()


def test_broken_zip_is_bundle_invalid(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = tmp_path / f"haifa-{NEWER}.zip"
    bundle.write_bytes(b"not a zip at all")
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "bundle_invalid"
    assert not uv_log.exists()


@pytest.mark.parametrize("drop", ["SHA256SUMS", "constraints.txt"])
def test_missing_file_is_bundle_invalid(
    tmp_path: Path, uv_log: Path, capsys: Capsys, drop: str
) -> None:
    bundle = make_bundle(tmp_path / "dist", drop=drop)
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "bundle_invalid"
    assert not uv_log.exists()


def test_missing_path_is_bundle_invalid(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    code, obj = _run(capsys, str(tmp_path / "nope.zip"))
    assert code == 2 and obj["error"]["code"] == "bundle_invalid"


def test_wrong_checksum(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist", tamper="constraints.txt")
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "checksum_mismatch"
    assert obj["data"]["file"] == "constraints.txt"
    assert not uv_log.exists()


def test_editable_install_is_refused(
    tmp_path: Path, uv_log: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upgrade, "editable_install", lambda: True)
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "editable_install"
    assert "git pull" in obj["error"]["message"]
    assert not uv_log.exists()


def test_editable_detection_from_direct_url() -> None:
    editable = json.dumps({"url": "file:///src/haifa/aifactory", "dir_info": {"editable": True}})
    plain = json.dumps({"url": "file:///tmp/aifactory.whl", "archive_info": {}})
    assert upgrade.editable_from_direct_url(editable) is True
    assert upgrade.editable_from_direct_url(plain) is False
    assert upgrade.editable_from_direct_url(None) is False
    assert upgrade.editable_from_direct_url("{broken") is False


def test_dry_run_runs_nothing(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle), "--dry-run")
    assert code == 0 and obj["ok"]
    assert obj["data"]["dry_run"] is True and obj["data"]["installed"] is False
    assert obj["data"]["target_version"] == NEWER
    assert obj["data"]["command"][:4] == ["uv", "tool", "install", "--force"]
    assert not uv_log.exists()


def test_uv_failure(
    tmp_path: Path, uv_log: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_EXIT", "3")
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle))
    assert code == 1 and obj["error"]["code"] == "upgrade_failed"
    assert obj["data"]["returncode"] == 3 and obj["data"]["installed"] is False
    assert uv_log.exists()


def test_uv_missing(
    tmp_path: Path, uv_log: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aifactory.upgrade.shutil.which", lambda _name: None)
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "uv_missing"


def test_file_url(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, bundle.resolve().as_uri())
    assert code == 0 and obj["data"]["installed"] is True
    assert uv_log.read_text("utf-8").count("tool install --force") == 1


def test_missing_file_url_is_download_failed(tmp_path: Path, capsys: Capsys) -> None:
    code, obj = _run(capsys, (tmp_path / "nope.zip").as_uri())
    assert code == 2 and obj["error"]["code"] == "download_failed"


@pytest.mark.parametrize(
    "url", ["http://example.invalid/haifa-9.0.0.zip", "ftp://example.invalid/haifa.zip"]
)
def test_other_url_scheme_is_refused(url: str, uv_log: Path, capsys: Capsys) -> None:
    code, obj = _run(capsys, url)
    assert code == 2 and obj["error"]["code"] == "invalid_url"
    assert not uv_log.exists()


def test_target_below_library_minimum_warns(
    tmp_path: Path, uv_log: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upgrade, "library_min_factory_version", lambda _env=None: "999.0")
    bundle = make_bundle(tmp_path / "dist")
    code, obj = _run(capsys, str(bundle), "--dry-run")
    assert code == 0
    assert obj["data"]["min_factory_version"] == "999.0"
    assert any("999.0" in w for w in obj["warnings"])


def test_unsafe_zip_path_is_bundle_invalid(tmp_path: Path, uv_log: Path, capsys: Capsys) -> None:
    bundle = tmp_path / "evil.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("../escape.txt", b"x")
    code, obj = _run(capsys, str(bundle))
    assert code == 2 and obj["error"]["code"] == "bundle_invalid"
    assert not (tmp_path.parent / "escape.txt").exists()


def test_no_library_has_no_minimum() -> None:
    assert library_min_factory_version() is None


def test_skill_describes_upgrade() -> None:
    skill = render_skill()
    assert "factory upgrade" in skill and "### Upgrade" in skill
    for code in ("up_to_date", "bundle_invalid", "checksum_mismatch", "editable_install"):
        assert f"`{code}`" in skill
