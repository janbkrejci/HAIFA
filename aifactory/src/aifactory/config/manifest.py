"""``.factory/manifest.yaml``: origin of every item and the onboarding mark (AR19).

A repo without the file is format 0 and runs as before. A repo with it takes workflows
only from its own ``.factory/workflows/`` (D32). A run reads only ``format`` from it: a
format newer than ``MANIFEST_FORMAT`` stops ``load_config`` with ``format_unsupported``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.settings import validation_issues

MANIFEST_FILE = ".factory/manifest.yaml"
MANIFEST_FORMAT = 1
OnboardingSource = Literal["init", "sssf", "pre_library"]
# manifest key of each item type
ITEM_KEYS: dict[str, str] = {
    "agent": "agents",
    "workflow": "workflows",
    "skill": "skills",
    "extension": "extensions",
}


class LibraryRef(BaseModel):
    """The library the items came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    remote: str | None = None


class Onboarding(BaseModel):
    """Written once by init or onboard and never changed after."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: OnboardingSource
    source_commit: str | None = None
    at: str
    by: str | None = None
    factory: str
    library_commit: str | None = None


class ManifestEntry(BaseModel):
    """One item in the repo: the library item and the version it was taken at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: str
    version: str


class ManifestItems(BaseModel):
    """Items by type; the key is the name in the repo (the slot for agents)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agents: dict[str, ManifestEntry] = Field(default_factory=dict)
    workflows: dict[str, ManifestEntry] = Field(default_factory=dict)
    skills: dict[str, ManifestEntry] = Field(default_factory=dict)
    extensions: dict[str, ManifestEntry] = Field(default_factory=dict)

    def of(self, type: str) -> dict[str, ManifestEntry]:
        """Entries of an item type (``agent``, ``workflow``, ``skill``, ``extension``)."""
        result: dict[str, ManifestEntry] = getattr(self, ITEM_KEYS[type])
        return result


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format: int = MANIFEST_FORMAT
    written_by: str
    library: LibraryRef | None = None
    onboarding: Onboarding | None = None
    items: ManifestItems = Field(default_factory=ManifestItems)

    def entry(self, type: str, name: str) -> ManifestEntry | None:
        return self.items.of(type).get(name)

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def unsupported_error(found: object, label: str) -> ConfigError:
    from aifactory import __version__

    return ConfigError(
        [
            ConfigIssue(
                label,
                f"manifest format {found} is newer than this HAIFA supports "
                f"(aifactory {__version__} reads format {MANIFEST_FORMAT} at most); "
                "update HAIFA with factory upgrade",
            )
        ],
        code="format_unsupported",
    )


def parse_manifest(text: str, label: str) -> Manifest:
    """The manifest in ``text``; ``ConfigError`` (``format_unsupported`` for a newer format)."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([ConfigIssue(label, f"invalid YAML: {exc}")]) from exc
    if not isinstance(raw, dict):
        raise ConfigError([ConfigIssue(label, "the manifest must be a mapping")])
    found = raw.get("format")
    if not isinstance(found, int) or isinstance(found, bool) or found < 1:
        raise ConfigError([ConfigIssue(label, "format: must be a positive integer")])
    if found > MANIFEST_FORMAT:
        raise unsupported_error(found, label)
    try:
        return Manifest.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(validation_issues(exc, label)) from exc


def dump_manifest(manifest: Manifest) -> str:
    """YAML text of ``manifest`` in the key order of AR19."""
    return yaml.safe_dump(manifest.to_json(), sort_keys=False, allow_unicode=True)


def read_manifest(root: Path) -> Manifest | None:
    """The manifest in the working tree of ``root``, or None (format 0)."""
    path = root / MANIFEST_FILE
    if not path.is_file():
        return None
    return parse_manifest(path.read_text(encoding="utf-8"), str(path))


def write_manifest(root: Path, manifest: Manifest) -> Path:
    """Write ``manifest`` into the working tree of ``root``."""
    path = root / MANIFEST_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_manifest(manifest), encoding="utf-8", newline="\n")
    return path
