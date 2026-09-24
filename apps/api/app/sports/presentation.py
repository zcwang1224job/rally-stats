"""Shapes the sport type plugins hand back to core and core hands to clients
(spec 043 contracts/sections-manifest.md, contracts/sports-api.md)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# Section kinds every sport type may emit and the frontend renders without a
# sport type module (contracts/sections-manifest.md §2).
GENERIC_SECTION_KINDS: frozenset[str] = frozenset(
    {"metric_grid", "stat_table", "score_timeline", "text_note"}
)


class Section(BaseModel):
    """One block of a match-detail page or member dashboard.

    `data=None` on `net_rally.*` kinds means "the data is the response's
    top-level fields" / "the section component fetches it itself" (research
    Decision 12)."""

    model_config = ConfigDict(frozen=True)

    kind: str
    title_key: str | None = None
    data: Any = None


VenueNoun = Literal["court", "table", "board", "arena", "station", "venue"]
ScoreNoun = Literal["point", "frame", "score"]
MemberNoun = Literal["player", "member", "competitor"]


class Nouns(BaseModel):
    """i18n keys for "court / point / player" as this activity calls them."""

    model_config = ConfigDict(frozen=True)

    venue: VenueNoun
    score: ScoreNoun
    member: MemberNoun


class SportSummary(BaseModel):
    """What every group / match response says about its activity.

    Built-ins carry `name_key` (translated by the client) and no `name`;
    custom and "other" activities carry the user's `name` and no key."""

    model_config = ConfigDict(frozen=True)

    sport_key: str
    type_key: str
    name_key: str | None
    name: str | None
    icon: str
    nouns: Nouns
