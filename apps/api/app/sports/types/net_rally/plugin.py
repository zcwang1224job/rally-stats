"""Net rally sport type (badminton, table tennis, pickleball, tennis
tie-break): one game per match, every rally scores, first to target with a
win_by lead or to the cap. Badminton's serve tracking and shot placement are
optional modules of this type (spec 043 FR-002, research Decision 9)."""

from typing import ClassVar

from app.sports.plugin import BasePlugin


class NetRallyPlugin(BasePlugin):
    type_key: ClassVar[str] = "net_rally"
    modules: ClassVar[frozenset[str]] = frozenset({"serve_tracking", "shot_placement"})
    section_kinds: ClassVar[frozenset[str]] = frozenset(
        {"net_rally.match_detail", "net_rally.dashboard"}
    )
