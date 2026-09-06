"""Two-phase scheduling algorithms shared across fair_rotation, fixed_partner,
and individual_mixed scheduling mechanisms (spec FR-005, FR-008, FR-019,
FR-025). Per spec Assumptions, greedy heuristics are explicitly accepted — a
reasonable low pair-count result, not a guaranteed global optimum.

Pure functions with no ORM/DB dependency, so they're trivially unit-testable
and reusable at different granularities (individual players to form teammate
pairs, or already-formed teams to form match-ups)."""

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TypeVar, cast

T = TypeVar("T")


def stage1_select_players(
    roster: Sequence[tuple[uuid.UUID, int | None, datetime]],
    n: int,
) -> list[uuid.UUID]:
    """FR-005: top `n` roster entries by wait_count DESC (None = infinite,
    i.e. never played — always outranks any finite count), tie-broken by
    joined_at ASC. `roster` items are (roster_entry_id, wait_count,
    joined_at) tuples."""
    ordered = sorted(roster, key=lambda item: (item[1] is not None, -(item[1] or 0), item[2]))
    return [item[0] for item in ordered[:n]]


def greedy_pair_by_cost(units: Sequence[T], cost: Callable[[T, T], int]) -> list[tuple[T, T]]:
    """Generic greedy nearest-neighbor pairing: repeatedly anchors on the
    first remaining unit (preserving the caller's priority order for
    deterministic tie-breaking) and pairs it with whichever remaining unit
    minimizes `cost`, until fewer than 2 units remain. A leftover single unit
    (odd count) is dropped from the result — callers with an odd count MUST
    decide how to handle the leftover themselves (e.g. FR-020's "落單")."""
    remaining = list(units)
    pairs: list[tuple[T, T]] = []
    while len(remaining) >= 2:
        anchor = remaining.pop(0)
        best_index = min(range(len(remaining)), key=lambda i: cost(anchor, remaining[i]))
        partner = remaining.pop(best_index)
        pairs.append((anchor, partner))
    return pairs


def stage2_pair_players(
    player_ids: Sequence[uuid.UUID],
    pair_count: Callable[[uuid.UUID, uuid.UUID], int],
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """FR-008: pair up `player_ids` (already stage-1 ordered) minimizing
    pair_count per pair. MUST NOT influence who made the stage-1 cut — this
    function only ever receives the already-selected list."""
    return greedy_pair_by_cost(player_ids, pair_count)


TeamCandidate = tuple[tuple[uuid.UUID, uuid.UUID], int | None, int | None, datetime, datetime]


def team_stage1_select(
    teams: Sequence[TeamCandidate],
    n_teams: int,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """FR-018: fixed-partner "who plays" is decided per TEAM, not per player
    — a team's priority is the MAX of its two members' wait_count (None on
    either side makes the whole team infinite priority, since a never-played
    member's partner shouldn't be held back), tie-broken by the earlier of
    the two members' joined_at. `teams` items are
    ((player_a_id, player_b_id), wait_count_a, wait_count_b, joined_a,
    joined_b) tuples."""

    def sort_key(item: TeamCandidate) -> tuple[bool, int, datetime]:
        _pair, wait_a, wait_b, joined_a, joined_b = item
        is_finite = wait_a is not None and wait_b is not None
        finite_priority = max(wait_a or 0, wait_b or 0)
        earliest_joined = min(joined_a, joined_b)
        return (is_finite, -finite_priority, earliest_joined)

    ordered = sorted(teams, key=sort_key)
    return [item[0] for item in ordered[:n_teams]]


def round_robin_pairs(units: Sequence[T]) -> list[list[tuple[T, T]]]:
    """011-round-robin-scheduling research.md #1: classic "circle method" —
    fixes the first unit, rotates the rest around it, and reads off
    non-conflicting pairs each rotation. Returns a list of batches; every
    pair within a single batch is disjoint (no unit repeated), and across
    all batches every unique pair of `units` appears exactly once (total
    pair count == C(len(units), 2)). An odd `units` count is handled with an
    internal bye slot that is silently dropped from the output — callers
    never see it. Used for both individual round-robin (fair_rotation
    singles) and team round-robin (fixed_partner), since the algorithm only
    cares about opaque "units", not what they represent."""
    if len(units) < 2:
        return []

    BYE = object()
    pool: list[T | object] = list(units)
    if len(pool) % 2 == 1:
        pool.append(BYE)

    n = len(pool)
    fixed = pool[0]
    rotating = pool[1:]

    batches: list[list[tuple[T, T]]] = []
    for _ in range(n - 1):
        ring = [fixed, *rotating]
        pairs = [(ring[i], ring[n - 1 - i]) for i in range(n // 2)]
        batch = [pair for pair in pairs if BYE not in pair]
        batches.append(cast(list[tuple[T, T]], batch))
        rotating = [rotating[-1], *rotating[:-1]]

    return batches


def team_matchup_stage2(
    teams: Sequence[tuple[uuid.UUID, uuid.UUID]],
    pair_count: Callable[[uuid.UUID, uuid.UUID], int],
) -> list[tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]]:
    """FR-019: pairs up already-formed teams into match-ups, minimizing the
    sum of pair_count across all 4 cross-team member combinations. Reused
    verbatim by fair_rotation's own doubles handling (US1) and individual
    mixed's second step (FR-025) — this is the one "team vs team" primitive
    in the whole domain, not something fixed_partner owns exclusively."""

    def cross_cost(
        team_x: tuple[uuid.UUID, uuid.UUID], team_y: tuple[uuid.UUID, uuid.UUID]
    ) -> int:
        return sum(pair_count(a, b) for a in team_x for b in team_y)

    return greedy_pair_by_cost(teams, cross_cost)
