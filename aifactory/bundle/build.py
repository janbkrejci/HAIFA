"""Build the HAIFA distribution bundle ``dist/haifa-<version>.zip`` (``just bundle``).

The zip holds one directory ``haifa-<version>/`` with exactly: the ``aifactory`` wheel,
``constraints.txt`` (runtime dependencies pinned from ``uv.lock``), ``install.sh``,
``INSTALL.md``, ``THIRD_PARTY_NOTICES`` and ``SHA256SUMS`` over all the other files.
The frontend is not built here: ``just bundle`` runs ``just web-build`` first, and the
build packages whatever is in ``src/aifactory/web/static/``. No network is needed.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
ZIP_TIME = (2026, 1, 1, 0, 0, 0)


class BundleError(Exception):
    """The bundle cannot be built (missing frontend build, broken lock, failed wheel)."""


def version(project: Path = PROJECT) -> str:
    """``aifactory.__version__`` read from the source, without importing the package."""
    for line in (project / "src" / "aifactory" / "__init__.py").read_text("utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise BundleError("__version__ not found in src/aifactory/__init__.py")


def constraints(lock_path: Path, root: str = "aifactory") -> str:
    """``name==version`` lines for every runtime dependency of ``root`` in ``uv.lock``."""
    lock = tomllib.loads(lock_path.read_text("utf-8"))
    packages: dict[str, dict[str, Any]] = {}
    for pkg in lock.get("package", []):
        if pkg["name"] in packages:
            raise BundleError(f"uv.lock pins {pkg['name']} more than once")
        packages[pkg["name"]] = pkg
    if root not in packages:
        raise BundleError(f"{root} not found in {lock_path}")
    pinned: dict[str, str] = {}
    todo: list[tuple[str, list[str]]] = [(root, [])]
    seen: set[tuple[str, str]] = set()
    while todo:
        name, extras = todo.pop()
        pkg = packages[name]
        deps = list(pkg.get("dependencies", []))
        for extra in extras:
            deps += pkg.get("optional-dependencies", {}).get(extra, [])
        for dep in deps:
            dep_name = dep["name"]
            dep_extras = list(dep.get("extra", []))
            key = (dep_name, ",".join(sorted(dep_extras)))
            if key in seen:
                continue
            seen.add(key)
            pinned[dep_name] = packages[dep_name]["version"]
            todo.append((dep_name, dep_extras))
    return "".join(f"{name}=={pinned[name]}\n" for name in sorted(pinned))


def build_wheel(out_dir: Path, project: Path = PROJECT) -> Path:
    """Build the ``aifactory`` wheel with hatchling (in-process deps, no build isolation)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "--target",
            "wheel",
            "--directory",
            str(out_dir),
        ],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    wheels = sorted(out_dir.glob("aifactory-*.whl"))
    if proc.returncode != 0 or len(wheels) != 1:
        raise BundleError(f"wheel build failed:\n{proc.stdout}{proc.stderr}")
    return wheels[0]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_bundle(out_dir: Path, project: Path = PROJECT) -> Path:
    """Build ``out_dir/haifa-<version>.zip`` and return its path."""
    if not (project / "src" / "aifactory" / "web" / "static" / "index.html").is_file():
        raise BundleError("frontend build missing: run `just web-build` first")
    ver = version(project)
    with tempfile.TemporaryDirectory() as tmp:
        wheel = build_wheel(Path(tmp), project)
        files: dict[str, bytes] = {
            wheel.name: wheel.read_bytes(),
            "constraints.txt": constraints(project / "uv.lock").encode("utf-8"),
        }
    for template in ("install.sh", "INSTALL.md"):
        text = (HERE / template).read_text("utf-8")
        text = text.replace("@VERSION@", ver).replace("@WHEEL@", wheel.name)
        files[template] = text.encode("utf-8")
    files["THIRD_PARTY_NOTICES"] = (project / "THIRD_PARTY_NOTICES").read_bytes()
    files["SHA256SUMS"] = "".join(
        f"{_sha256(data)}  {name}\n" for name, data in sorted(files.items())
    ).encode("utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"haifa-{ver}.zip"
    top = f"haifa-{ver}"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if name == "install.sh" else 0o644
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, files[name])
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", type=Path, default=PROJECT / "dist", help="output directory")
    args = parser.parse_args(argv)
    try:
        path = build_bundle(args.out)
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
