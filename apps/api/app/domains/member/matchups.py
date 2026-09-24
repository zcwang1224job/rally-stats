"""036-match-insights-benchmarks US2: who I play well with, and who I keep
losing to. Pure functions — no ORM, no `AsyncSession`.

Rows are keyed by WHO a player is (`player_identity.player_key`), not by what
they were called. The ranking this replaces tallied by nickname string, which
split one member across the nicknames they use in different groups, merged
different people who share a nickname — and merged every deleted account
into a single row, since 025 renames them all to "Deleted User"
(research.md Decision 3).

Only a final score and the participants are needed, so every completed match
counts: simple or detailed scoring, before or after 030."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domains.member.player_identity import PlayerRef

# Below this a row is shown but flagged, and never singled out (FR-024).
LOW_SAMPLE_BELOW = 3
# "Best partner" / "toughest opponent" compare win rates, which mean little
# over a handful of matches.
HIGHLIGHT_MIN_MATCHES = 5


@dataclass(frozen=True)
class MatchupInput:
    """One completed match from my side. `partners` excludes me and is empty
    in singles; `margin` is my team's score minus theirs."""

    ended_at: datetime
    won: bool
    margin: int
    is_doubles: bool
    partners: tuple[PlayerRef, ...]
    opponents: tuple[PlayerRef, ...]
    # 043: a draw is neither a win nor a loss.
    draw: bool = False


@dataclass(frozen=True)
class MatchupRecord:
    player_key: str
    nickname: str  # as of their latest match in range
    member_id: str | None
    matches: int
    wins: int
    losses: int
    win_rate: float
    avg_margin: float  # one decimal; negative when I usually lose to / with them
    low_sample: bool


@dataclass(frozen=True)
class MatchupHighlights:
    """Player keys, or None when nobody has played enough to be named."""

    most_played_partner: str | None
    best_partner: str | None
    most_faced_opponent: str | None
    toughest_opponent: str | None


@dataclass(frozen=True)
class MatchupResult:
    partner_records: list[MatchupRecord]
    opponent_records: list[MatchupRecord]
    highlights: MatchupHighlights
    doubles_matches: int
    # Baselines for the matchup insights (FR-025); None without any match.
    overall_win_rate: float | None
    doubles_win_rate: float | None


@dataclass
class _Tally:
    ref: PlayerRef
    named_at: datetime
    wins: int = 0
    losses: int = 0
    margin: int = 0


def _records(inputs: Sequence[MatchupInput], role: str) -> list[MatchupRecord]:
    tallies: dict[str, _Tally] = {}
    for item in inputs:
        players: Iterable[PlayerRef] = item.partners if role == "partner" else item.opponents
        for player in players:
            tally = tallies.get(player.key)
            if tally is None:
                tally = tallies[player.key] = _Tally(ref=player, named_at=item.ended_at)
            # Latest match names the row; the nickname breaks an exact tie so
            # the result never depends on the order matches arrive in.
            elif (item.ended_at, player.nickname) > (tally.named_at, tally.ref.nickname):
                tally.ref, tally.named_at = player, item.ended_at
            tally.wins += int(item.won)
            tally.losses += int(not item.won and not item.draw)
            tally.margin += item.margin
    records = [
        MatchupRecord(
            player_key=key,
            nickname=tally.ref.nickname,
            member_id=tally.ref.member_id,
            matches=tally.wins + tally.losses,
            wins=tally.wins,
            losses=tally.losses,
            win_rate=round(tally.wins / (tally.wins + tally.losses), 4),
            avg_margin=round(tally.margin / (tally.wins + tally.losses), 1),
            low_sample=(tally.wins + tally.losses) < LOW_SAMPLE_BELOW,
        )
        for key, tally in tallies.items()
    ]
    return sorted(records, key=lambda record: (-record.matches, record.player_key))


def _most_played(records: Sequence[MatchupRecord]) -> str | None:
    # Already sorted by matches (desc) then key, so the first one that has
    # played enough is the answer.
    return next((r.player_key for r in records if not r.low_sample), None)


def _by_win_rate(records: Sequence[MatchupRecord], *, highest: bool) -> str | None:
    eligible = [r for r in records if r.matches >= HIGHLIGHT_MIN_MATCHES]
    if not eligible:
        return None
    best = min(
        eligible,
        key=lambda r: (-r.win_rate if highest else r.win_rate, -r.matches, r.player_key),
    )
    return best.player_key


def _win_rate(inputs: Sequence[MatchupInput]) -> float | None:
    return round(sum(item.won for item in inputs) / len(inputs), 4) if inputs else None


def build(inputs: Sequence[MatchupInput]) -> MatchupResult:
    partners = _records(inputs, "partner")
    opponents = _records(inputs, "opponent")
    doubles = [item for item in inputs if item.is_doubles]
    return MatchupResult(
        partner_records=partners,
        opponent_records=opponents,
        highlights=MatchupHighlights(
            most_played_partner=_most_played(partners),
            best_partner=_by_win_rate(partners, highest=True),
            most_faced_opponent=_most_played(opponents),
            toughest_opponent=_by_win_rate(opponents, highest=False),
        ),
        doubles_matches=len(doubles),
        overall_win_rate=_win_rate(inputs),
        doubles_win_rate=_win_rate(doubles),
    )


@dataclass(frozen=True)
class MatchupTally:
    """Always from MY side: `wins` are mine, `avg_margin` is mine minus theirs."""

    matches: int
    wins: int
    losses: int
    win_rate: float
    avg_margin: float


@dataclass(frozen=True)
class HeadToHead:
    """036 US4. None: we never met in that role."""

    as_opponents: MatchupTally | None
    as_partners: MatchupTally | None


def _tally(inputs: Sequence[MatchupInput]) -> MatchupTally | None:
    if not inputs:
        return None
    wins = sum(item.won for item in inputs)
    return MatchupTally(
        matches=len(inputs),
        wins=wins,
        losses=len(inputs) - wins,
        win_rate=round(wins / len(inputs), 4),
        avg_margin=round(sum(item.margin for item in inputs) / len(inputs), 1),
    )


def head_to_head(inputs: Sequence[MatchupInput], friend_key: str) -> HeadToHead:
    """My record against, and alongside, one particular player — read off MY
    matches, so it needs nothing of theirs."""
    return HeadToHead(
        as_opponents=_tally([i for i in inputs if any(p.key == friend_key for p in i.opponents)]),
        as_partners=_tally([i for i in inputs if any(p.key == friend_key for p in i.partners)]),
    )
