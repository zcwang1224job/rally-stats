"""043 T028 (research Decisions 9/15, FR-015/FR-034): core code never queries
a table a sport type plugin owns, and never branches on a sport or sport type
name. import-linter keeps core from importing plugins; this keeps the two
things an import check cannot see."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "app"

CORE_DIRS = [APP / "domains", APP / "core", APP / "system_config", APP / "scheduler"]
CORE_FILES = [
    APP / "sports" / name
    for name in ("registry.py", "plugin.py", "presentation.py", "scoring.py")
]

# Named plugin-owned ORM classes; core may import them for typing, never select them.
PLUGIN_TABLE_SELECT = re.compile(
    r"select\(\s*(ScoreServeRecord|ShotPlacementRecord|FrameResult|FramePoint)\b"
)
PLUGIN_TABLE_DELETE = re.compile(
    r"delete\(\s*(ScoreServeRecord|ShotPlacementRecord|FrameResult|FramePoint)\b"
)
NAME_BRANCH = re.compile(
    r"""(==|!=)\s*["'](badminton|net_rally|frames|generic|billiards|table_tennis)["']"""
    r"""|["'](badminton|net_rally|frames|generic)["']\s*(==|!=)"""
    r"""|\bin\s*\(\s*["'](badminton|net_rally|frames|generic)["']"""
)

# Files where a sport key legitimately appears as data, not as a branch.
ALLOWED = {
    APP / "sports" / "catalog.py",
    APP / "system_config" / "service.py",
}


def _core_sources() -> list[Path]:
    files = [path for directory in CORE_DIRS for path in directory.rglob("*.py")]
    return sorted({*files, *CORE_FILES} - ALLOWED)


def test_core_never_queries_plugin_owned_tables() -> None:
    offenders = [
        f"{path.relative_to(APP)}:{number}"
        for path in _core_sources()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if PLUGIN_TABLE_SELECT.search(line) or PLUGIN_TABLE_DELETE.search(line)
    ]
    assert offenders == []


def test_core_never_branches_on_a_sport_name() -> None:
    offenders = [
        f"{path.relative_to(APP)}:{number}: {line.strip()}"
        for path in _core_sources()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if NAME_BRANCH.search(line)
    ]
    assert offenders == []


def test_the_scan_covers_the_files_it_should() -> None:
    sources = {path.relative_to(APP).as_posix() for path in _core_sources()}
    assert "domains/schedule/service.py" in sources
    assert "domains/group/service.py" in sources
    assert "sports/registry.py" in sources
    assert "sports/catalog.py" not in sources
