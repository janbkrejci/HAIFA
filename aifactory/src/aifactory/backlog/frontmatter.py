"""Split a markdown file into its YAML header and body."""

from __future__ import annotations

import yaml


class FrontmatterError(Exception):
    """The YAML header of a markdown file is missing or invalid."""


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a markdown file into its YAML header (a mapping) and the body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise FrontmatterError("file does not start with a '---' YAML header")
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            header = "".join(lines[1:i])
            body = "".join(lines[i + 1 :])
            break
    else:
        raise FrontmatterError("YAML header is not closed with '---'")
    try:
        data = yaml.safe_load(header)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML in header: {exc}") from exc
    if data is None:
        return {}, body
    if not isinstance(data, dict):
        raise FrontmatterError("YAML header must be a mapping")
    return {str(k): v for k, v in data.items()}, body
