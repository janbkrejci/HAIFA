"""yamlload: the libyaml safe loader, same results as yaml.safe_load, still safe."""

from __future__ import annotations

import pytest
import yaml

from aifactory import yamlload

DOCUMENT = "name: x\nlist: [1, 2.5, true, null]\nnested:\n  key: 'č'\ndate: 2026-10-14\n"


def test_loader_is_libyaml_when_available() -> None:
    loader: object = yamlload.LOADER
    if yaml.__with_libyaml__:
        assert loader is yaml.CSafeLoader
    else:
        assert loader is yaml.SafeLoader


@pytest.mark.parametrize("stream", [DOCUMENT, DOCUMENT.encode("utf-8")])
def test_same_result_as_safe_load(stream: str | bytes) -> None:
    assert yamlload.safe_load(stream) == yaml.safe_load(stream)


@pytest.mark.parametrize("stream", ["", b""])
def test_empty_input_is_none(stream: str | bytes) -> None:
    assert yamlload.safe_load(stream) is None


def test_rejects_python_tags() -> None:
    with pytest.raises(yaml.YAMLError):
        yamlload.safe_load("!!python/object/apply:os.system [x]")
