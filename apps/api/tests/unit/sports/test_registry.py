"""043 T016: the core sport type registry."""

from typing import ClassVar

import pytest

from app.sports import registry
from app.sports.plugin import BasePlugin, UnknownSportType


class _Alpha(BasePlugin):
    type_key: ClassVar[str] = "test_alpha"


class _AlphaImpostor(BasePlugin):
    type_key: ClassVar[str] = "test_alpha"


@pytest.fixture(autouse=True)
def _isolated_registry():  # type: ignore[no-untyped-def]
    saved = registry.snapshot()
    yield
    registry.restore(saved)


def test_register_then_get_returns_the_same_plugin() -> None:
    plugin = _Alpha()
    registry.register(plugin)
    assert registry.get("test_alpha") is plugin
    assert "test_alpha" in registry.type_keys()


def test_registering_the_same_class_twice_is_a_no_op() -> None:
    first = _Alpha()
    registry.register(first)
    registry.register(_Alpha())
    assert registry.get("test_alpha") is first


def test_a_different_plugin_under_a_taken_key_is_rejected() -> None:
    registry.register(_Alpha())
    with pytest.raises(ValueError, match="test_alpha"):
        registry.register(_AlphaImpostor())


def test_unknown_key_raises_unknown_sport_type() -> None:
    with pytest.raises(UnknownSportType):
        registry.get("no_such_type")


def test_builtin_types_are_registered_by_register_all() -> None:
    from app.sports.types import register_all

    register_all()
    assert {"net_rally", "frames", "generic"} <= set(registry.type_keys())
