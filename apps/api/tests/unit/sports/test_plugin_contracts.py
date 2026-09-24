"""043 T116 (US7, SC-008): what every registered sport type promises core
and the frontend, checked for all of them at once — so a new type that
breaks one of these fails here before anyone looks at its screens.

`app/sports/section-kinds.json` is the list of section kinds each type may
send; the frontend's contract spec reads it. Regenerate after adding a kind:

    UPDATE_SECTION_KINDS=1 python -m pytest tests/unit/sports/test_plugin_contracts.py
"""

import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import app.domains.member.models  # noqa: F401  (every FK target on the metadata)
from app.core.db import Base
from app.sports import registry
from app.sports.plugin import BasePlugin, DashboardContext, DashboardRow
from app.sports.presentation import GENERIC_SECTION_KINDS
from app.sports.types import register_all

SECTION_KINDS_FILE = Path(__file__).parents[3] / "app" / "sports" / "section-kinds.json"


@pytest.fixture(autouse=True)
def _plugins() -> None:
    register_all()


def _plugins_list() -> list[BasePlugin]:
    register_all()
    return list(registry.plugins())


def _manifest() -> dict[str, list[str]]:
    kinds = {plugin.type_key: sorted(plugin.section_kinds) for plugin in _plugins_list()}
    return {"generic_kinds": sorted(GENERIC_SECTION_KINDS), "types": dict(sorted(kinds.items()))}


def test_the_three_types_are_registered() -> None:
    assert set(registry.type_keys()) >= {"net_rally", "frames", "generic"}


@pytest.mark.parametrize("plugin", _plugins_list(), ids=lambda p: p.type_key)
def test_event_kinds_carry_the_type_prefix(plugin: BasePlugin) -> None:
    for kind in plugin.event_schemas():
        assert kind.startswith(f"{plugin.type_key}."), kind
        assert len(kind) <= 24  # score_events.kind


@pytest.mark.parametrize("plugin", _plugins_list(), ids=lambda p: p.type_key)
def test_section_kinds_are_namespaced(plugin: BasePlugin) -> None:
    for kind in plugin.section_kinds:
        assert kind.startswith(f"{plugin.type_key}."), kind
        assert kind not in GENERIC_SECTION_KINDS


@pytest.mark.parametrize("plugin", _plugins_list(), ids=lambda p: p.type_key)
def test_params_schema_is_json_schema(plugin: BasePlugin) -> None:
    schema = plugin.params_schema().model_json_schema()
    assert schema["type"] == "object"
    # Defaults alone make valid params: a group opened without type_params.
    plugin.parse_params({})


@pytest.mark.parametrize("plugin", _plugins_list(), ids=lambda p: p.type_key)
def test_tables_hang_off_the_spine(plugin: BasePlugin) -> None:
    for name in plugin.tables():
        table = Base.metadata.tables[name]
        spine_keys = [
            fk
            for fk in table.foreign_keys
            if fk.parent.name == "score_event_id" and fk.column.table.name == "score_events"
        ]
        assert spine_keys, f"{name} has no score_event_id → score_events.id"
        assert all(fk.ondelete == "CASCADE" for fk in spine_keys), name


def _row(result: str) -> DashboardRow:
    match = SimpleNamespace(id=uuid.uuid4(), score_a=3, score_b=1, target_score=5)
    return DashboardRow(
        match=cast(Any, match),
        player_key="m:me",
        my_team="A",
        result=cast(Any, result),
        opponent_keys=("r:x",),
        opponent_names=("X",),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin", _plugins_list(), ids=lambda p: p.type_key)
async def test_empty_dashboard_uses_declared_kinds(plugin: BasePlugin) -> None:
    sections = await plugin.dashboard_sections(
        cast(Any, None), DashboardContext(mine=[], peers={}, me_key="m:me")
    )
    allowed = plugin.section_kinds | GENERIC_SECTION_KINDS
    assert sections and all(section.kind in allowed for section in sections)


@pytest.mark.asyncio
async def test_generic_dashboard_uses_declared_kinds() -> None:
    plugin = registry.get("generic")
    sections = await plugin.dashboard_sections(
        cast(Any, None),
        DashboardContext(mine=[_row("win"), _row("draw")], peers={}, me_key="m:me"),
    )
    assert {s.kind for s in sections} <= plugin.section_kinds | GENERIC_SECTION_KINDS


def test_section_kinds_file_is_current() -> None:
    wanted = json.dumps(_manifest(), ensure_ascii=False, indent=2) + "\n"
    if os.environ.get("UPDATE_SECTION_KINDS") == "1":
        SECTION_KINDS_FILE.write_text(wanted, encoding="utf-8")
    assert SECTION_KINDS_FILE.read_text(encoding="utf-8") == wanted, (
        "section-kinds.json drifted; regenerate with UPDATE_SECTION_KINDS=1"
    )
