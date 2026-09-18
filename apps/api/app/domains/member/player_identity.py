"""036-match-insights-benchmarks: who "the same player" is.

A roster row that belongs to a member is that member wherever they play and
whatever they were called there (`m:<member_id>` — also after an 028 guest
binding, which only fills `roster_entries.member_id`). An unbound guest is
just that one roster row (`r:<roster_entry_id>`): nothing ties two guest rows
together, so they are never merged. Same convention as 019's final standings.

Its own module (no ORM, no service imports) so that matchups (US2), the group
benchmark (US3) and the friend comparison (US4) can each use it without
depending on one another."""

import re
import uuid
from dataclasses import dataclass
from typing import Literal

PlayerKeyKind = Literal["m", "r"]

# Canonical lower-case UUID text only, so one player has exactly one key.
_KEY = re.compile(r"(m|r):([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


@dataclass(frozen=True)
class PlayerRef:
    key: str
    nickname: str
    member_id: str | None


def player_key(member_id: uuid.UUID | None, roster_entry_id: uuid.UUID) -> str:
    return f"m:{member_id}" if member_id is not None else f"r:{roster_entry_id}"


def parse_player_key(value: str) -> tuple[PlayerKeyKind, uuid.UUID]:
    """Raises `ValueError` for anything but a key `player_key()` could have
    produced; the router turns that into `INVALID_PLAYER_KEY` (422)."""
    match = _KEY.fullmatch(value)
    if match is None:
        raise ValueError(f"not a player key: {value!r}")
    kind: PlayerKeyKind = "m" if match.group(1) == "m" else "r"
    return kind, uuid.UUID(match.group(2))
