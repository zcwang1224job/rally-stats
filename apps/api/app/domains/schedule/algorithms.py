"""Two-phase scheduling algorithms shared across fair_rotation, fixed_partner,
and individual_mixed scheduling mechanisms (spec FR-005, FR-008, FR-019,
FR-025). Per spec Assumptions, greedy heuristics are explicitly accepted — a
reasonable low pair-count result, not a guaranteed global optimum.

Pure functions with no ORM/DB dependency, so they're trivially unit-testable
and reusable at different granularities (individual players to form teammate
pairs, or already-formed teams to form match-ups)."""

import math
import random
import uuid
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import datetime, timedelta
from functools import cache
from itertools import combinations
from typing import TypeVar, cast

T = TypeVar("T")

# (matches actually played in this group, when the latest of them ended)
PlayStats = tuple[int, datetime | None]


def stage1_select_players(
    roster: Sequence[tuple[uuid.UUID, int | None, datetime]],
    n: int,
    play_stats: Mapping[uuid.UUID, PlayStats] | None = None,
    pair_cost: Callable[[uuid.UUID, uuid.UUID], int] | None = None,
    run_lengths: Mapping[uuid.UUID, int] | None = None,
) -> list[uuid.UUID]:
    """FR-005: top `n` roster entries by wait_count DESC (None = infinite,
    i.e. never played — always outranks any finite count). `roster` items
    are (roster_entry_id, wait_count, joined_at) tuples.

    Ties on wait_count go to whoever has played fewer matches, then to
    whoever finished their last match earliest (has rested longest), and
    only then to joined_at ASC. Right after a round, everyone who played
    shares wait_count 0, so a bare joined_at tie-break handed the leftover
    seats to the earliest joiners every single round whenever the roster
    wasn't a multiple of the round's capacity (10 players on 2 courts: the
    first 6 played every round, the last 4 every other round). `play_stats`
    maps roster_entry_id to `PlayStats`; a missing entry means "never
    played".

    Players who finished the same match share that end time; among them,
    whoever has played the most matches in a row without a break
    (`run_lengths`, see `current_run()`) goes last. Without it the one who
    sat out was arbitrary, and in a simulated 9-player continuous rotation
    (8 on court, 1 resting) one player went 14 matches in a row without a
    break. Runs up to `_RUN_TOLERANCE` matches count as equal: two players
    who came on together have identical runs, so ranking every difference
    kept them moving as a unit and `pair_cost` below never got to split
    them (5 fixed pairs formed in a simulated 10-player continuous
    rotation, each meeting 11-12 times in 3 hours).

    With `pair_cost` (how often two players have already met), players
    still tied at the cut-off are chosen one at a time by fewest meetings
    with those already picked, instead of by join order. Players who finish
    the same match tie on everything above, and picking the same early
    joiners among them every time kept sending the same few people on court
    together: in a simulated 3-hour continuous rotation, one pair met as
    opponents 11 times while others met once. The match count itself is
    never loosened for this: treating counts one apart as equal mixed
    people up better still, but let a player fall two matches behind."""
    stats = play_stats or {}
    runs = run_lengths or {}

    def priority(
        item: tuple[uuid.UUID, int | None, datetime],
    ) -> tuple[bool, int, int, float, int]:
        roster_entry_id, wait_count, _joined_at = item
        played, last_ended = stats.get(roster_entry_id, (0, None))
        return (
            wait_count is not None,
            -(wait_count or 0),
            played,
            last_ended.timestamp() if last_ended is not None else float("-inf"),
            max(runs.get(roster_entry_id, 0) - _RUN_TOLERANCE, 0),
        )

    ordered = sorted(roster, key=lambda item: (priority(item), item[2]))
    if pair_cost is None or len(ordered) <= n or n <= 0:
        return [item[0] for item in ordered[:n]]

    cutoff = priority(ordered[n - 1])
    selected = [item[0] for item in ordered if priority(item) < cutoff]
    tied = [item[0] for item in ordered if priority(item) == cutoff]
    needed = n - len(selected)

    def meetings(group: Sequence[uuid.UUID]) -> int:
        return sum(pair_cost(a, b) for a, b in combinations(group, 2))

    if math.comb(len(tied), needed) <= _MAX_TIE_SUBSETS:
        # Whoever is left out gets top priority next time and so tends to go
        # back on court together: in continuous rotation with 10 players and
        # 2 courts, the two left out always came from the same match and
        # always returned into the same match, so one pair met 11 times in 3
        # hours. Count their meetings too, not just those of the picked.
        # min() keeps the earliest joiners among equal subsets.
        best = min(
            combinations(tied, needed),
            key=lambda picked: meetings([*selected, *picked])
            + meetings([pid for pid in tied if pid not in picked]),
        )
        return [*selected, *best]

    while len(selected) < n:
        # min() keeps the earliest joiner among equally fresh candidates.
        pick = min(tied, key=lambda pid: sum(pair_cost(pid, other) for other in selected))
        selected.append(pick)
        tied.remove(pick)
    return selected


# Matches in a row that don't yet count against a player in selection.
_RUN_TOLERANCE = 2

# Tie pools small enough to try every subset of (in practice: a court's 4
# finishers choosing 2 or 3).
_MAX_TIE_SUBSETS = 200


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


# 2^14 subsets × 13 partner choices stays well under 10ms; past this the
# exact search grows too fast and pairing falls back to greedy + 2-opt.
_EXACT_PAIRING_MAX_UNITS = 14


def _exact_min_cost_pairing(units: Sequence[T], cost: Callable[[T, T], int]) -> list[tuple[T, T]]:
    """Minimum-total-cost matching by DP over subsets: the lowest-index
    unpaired unit is always the anchor, and ties keep the earliest partner,
    so all-equal costs reproduce the greedy result ((0, 1), (2, 3), ...).
    With an odd count, the unit left out is whichever makes the rest
    cheapest to pair, the latest one on ties."""
    n = len(units)
    costs = [[cost(units[i], units[j]) if i != j else 0 for j in range(n)] for i in range(n)]

    @cache
    def best(mask: int) -> tuple[int, tuple[tuple[int, int], ...]]:
        if mask == 0:
            return 0, ()
        anchor = (mask & -mask).bit_length() - 1
        rest = mask & ~(1 << anchor)
        best_total: int | None = None
        best_pairs: tuple[tuple[int, int], ...] = ()
        partner_mask = rest
        while partner_mask:
            partner = (partner_mask & -partner_mask).bit_length() - 1
            partner_mask &= partner_mask - 1
            sub_total, sub_pairs = best(rest & ~(1 << partner))
            total = costs[anchor][partner] + sub_total
            if best_total is None or total < best_total:
                best_total = total
                best_pairs = ((anchor, partner), *sub_pairs)
        return cast(int, best_total), best_pairs

    full = (1 << n) - 1
    if n % 2 == 0:
        _total, index_pairs = best(full)
    else:
        options = [best(full & ~(1 << left_out)) for left_out in range(n - 1, -1, -1)]
        _total, index_pairs = min(options, key=lambda option: option[0])
    return [(units[i], units[j]) for i, j in index_pairs]


def _improve_pairing_2opt(
    pairs: list[tuple[T, T]], cost: Callable[[T, T], int]
) -> list[tuple[T, T]]:
    """Local search for rosters too large for the exact search: keeps
    re-partnering any two pairs whenever one of the two alternative splits
    of their four units is strictly cheaper, until nothing improves."""
    improved = True
    while improved:
        improved = False
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                (a, b), (c, d) = pairs[i], pairs[j]
                current = cost(a, b) + cost(c, d)
                for first, second in (((a, c), (b, d)), ((a, d), (b, c))):
                    if cost(*first) + cost(*second) < current:
                        pairs[i], pairs[j] = first, second
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return pairs


def min_cost_pairing(units: Sequence[T], cost: Callable[[T, T], int]) -> list[tuple[T, T]]:
    """Pairs `units` up minimizing the total `cost` over all pairs — exact
    for rosters up to `_EXACT_PAIRING_MAX_UNITS`, greedy plus 2-opt local
    search beyond that. The greedy pass alone commits to its first anchor's
    cheapest partner even when that forces an expensive repeat further down
    the list. With an odd count one unit is left out of the result and
    callers decide what to do with it, same as `greedy_pair_by_cost`.
    (`min()` returns the first of equal options, i.e. the latest left-out
    unit, since the options run from the last unit backwards.)"""
    if len(units) <= _EXACT_PAIRING_MAX_UNITS + 1:
        return _exact_min_cost_pairing(units, cost)
    return _improve_pairing_2opt(greedy_pair_by_cost(units, cost), cost)


def stage2_pair_players(
    player_ids: Sequence[uuid.UUID],
    pair_count: Callable[[uuid.UUID, uuid.UUID], int],
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """FR-008: pair up `player_ids` (already stage-1 ordered) minimizing
    pair_count per pair. MUST NOT influence who made the stage-1 cut — this
    function only ever receives the already-selected list."""
    return min_cost_pairing(player_ids, pair_count)


# How long a player needs to have been off court before the next match
# stops preferring someone who has rested longer. Beyond this, candidates
# count as equally rested and the admin's call-up order decides. Chosen by
# simulation: 5 minutes removes as many back-to-back matches as ranking on
# raw rest time does, while leaving the admin's order alone far more often.
REST_SATURATION = timedelta(minutes=5)


def pick_next_match(
    candidates: Sequence[tuple[T, Collection[uuid.UUID]]],
    last_ended: Mapping[uuid.UUID, datetime],
    now: datetime,
    saturation: timedelta = REST_SATURATION,
    on_court_since: Mapping[uuid.UUID, datetime] | None = None,
) -> T | None:
    """Chooses which queued match a freed court should take next.
    `candidates` are (match, participant ids) in call-up order, already
    filtered to matches with nobody currently on another court; `last_ended`
    maps a player to when their latest played match ended (absent = hasn't
    played yet). Each candidate is scored by the shortest rest among its
    players, capped at `saturation`; the highest score wins. Taking the
    earliest candidate unconditionally made the same people play several
    matches in a row while others waited through long gaps: in a simulated
    12-player, 4-court singles round, 55 back-to-back starts and a
    45-minute longest wait, versus 17 and 19 minutes with this rule.

    When even the best candidate needs someone who hasn't rested yet (a
    small roster, where every queued match involves someone who just came
    off), that shortest rest is the same for everyone and used to fall
    straight through to call-up order — which kept the same player on court
    8 matches running in a simulated 6-player individual_mixed round. So
    ties go to the candidate with fewer unrested players, then to the one
    whose unrested players have been on court for the shortest unbroken
    stretch (`on_court_since`: when each player's current run of matches
    without a real rest began), and only then to call-up order."""
    since = on_court_since or {}
    best: T | None = None
    best_score: tuple[timedelta, int, timedelta] | None = None
    for item, players in candidates:
        rest = saturation
        unrested = 0
        longest_run = timedelta(0)
        for player in players:
            ended = last_ended.get(player)
            if ended is None:
                continue
            player_rest = max(now - ended, timedelta(0))
            rest = min(rest, player_rest)
            if player_rest < saturation:
                unrested += 1
                longest_run = max(longest_run, now - since.get(player, now))
        score = (rest, -unrested, -longest_run)
        if best_score is None or score > best_score:
            best, best_score = item, score
    return best


# Two matches count as one unbroken run when the second started less than
# this long after the first ended — i.e. the player went straight back on.
# Sitting out even one match takes several minutes, so this separates
# "rested" from "didn't" without depending on how long matches last.
RUN_BREAK = timedelta(minutes=1)


def current_run(
    spans: Sequence[tuple[datetime, datetime]], gap: timedelta = RUN_BREAK
) -> tuple[datetime, int] | None:
    """A player's current unbroken run of matches: when it began and how
    many matches it holds. `spans` are their played matches' (started,
    ended). None without any played match."""
    ordered = sorted(spans)
    if not ordered:
        return None
    start = ordered[-1][0]
    length = 1
    for (prev_start, prev_end), (next_start, _next_end) in zip(
        reversed(ordered[:-1]), reversed(ordered[1:]), strict=False
    ):
        if next_start - prev_end >= gap:
            break
        start = prev_start
        length += 1
    return start, length


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


def round_robin_pairs(
    units: Sequence[T], *, start_swapped: bool = False
) -> list[list[tuple[T, T]]]:
    """011-round-robin-scheduling research.md #1: classic "circle method" —
    fixes the first unit, rotates the rest around it, and reads off
    non-conflicting pairs each rotation. Returns a list of batches; every
    pair within a single batch is disjoint (no unit repeated), and across
    all batches every unique pair of `units` appears exactly once (total
    pair count == C(len(units), 2)). An odd `units` count is handled with an
    internal bye slot that is silently dropped from the output — callers
    never see it. Used for both individual round-robin (fair_rotation
    singles) and team round-robin (fixed_partner), since the algorithm only
    cares about opaque "units", not what they represent.

    Side-fairness fix: the fixed anchor (`pool[0]`) is the one unit whose
    ring position never rotates, so absent this fix it would land as
    `pairs[0][0]` — tuple position 0 — in EVERY batch it plays. Callers map
    tuple position 0/1 straight onto Team A/B (`create_match_with_
    participants`), so the anchor would be Team A in literally every match,
    every round — the reported "球員固定同一側" bug. Every other unit's
    ring position does rotate each batch, so it naturally alternates
    between tuple position 0 and 1 already; only the anchor needed a
    deliberate fix. Each batch, find whichever surviving pair contains
    `fixed` (there may be none — an odd `units` count can pair `fixed`
    with the bye slot, dropping it from that batch entirely) and swap it on
    alternating occurrences, spreading the anchor roughly evenly across
    both tuple positions within one call. (Swapping by fixed *batch index*
    instead of by the anchor's own occurrence count would sometimes target
    the very batch where `fixed` paired with the bye slot — a no-op that
    silently skips the anchor's real swap turn — so this counts only the
    anchor's own real occurrences.) That within-call fix alone isn't enough
    across repeated calls, though — the SAME roster tends to come back in
    the SAME order call after call (no `ORDER BY` on the underlying query,
    stable heap order), so `pool[0]` is often the same real person every
    round, and the anchor's first real occurrence always starts unswapped
    by default — re-introducing a smaller but real bias for whichever unit
    happens to be the perennial `pool[0]`. `start_swapped` lets callers
    flip that starting parity per round (e.g. alternate by
    `round_number % 2`), so the anchor's side alternates across rounds
    too, not just within one.

    Known residual limitation: for a very small odd `units` count (e.g.
    exactly 3), the two non-anchor units only ever play each other once and
    that single match's tuple order is fixed by the ring rotation alone —
    this fix only ever touches the anchor's own pair, so it cannot balance
    that one match. Not a regression (the pre-fix code had the same
    property for one of the two non-anchor units, just for a different
    reason), and out of scope for the reported bug, which is specifically
    about the anchor being stuck across EVERY match, every round — true for
    any `units` count, not just small odd ones."""
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
    fixed_occurrence = 0
    for _ in range(n - 1):
        ring = [fixed, *rotating]
        pairs = [(ring[i], ring[n - 1 - i]) for i in range(n // 2)]
        batch = [pair for pair in pairs if BYE not in pair]
        for index, pair in enumerate(batch):
            if fixed in pair:
                if (fixed_occurrence % 2 == 1) != start_swapped:
                    batch[index] = (pair[1], pair[0])
                fixed_occurrence += 1
                break
        batches.append(cast(list[tuple[T, T]], batch))
        rotating = [rotating[-1], *rotating[:-1]]

    return batches


def random_pair_units(units: Sequence[T]) -> list[tuple[T, T]]:
    """017-fixed-partner-autofill research.md #3: uniform-random pairing,
    deliberately kept separate from `stage2_pair_players` (history-optimized
    "auto configuration" pairing) — the two represent different semantics
    (pure gap-filling vs. continuous optimization) and MUST NOT be merged.
    Shared by the preview endpoint and the round-generation autofill step so
    both use the exact same notion of "random". An odd `units` count drops
    the last shuffled unit from the result — callers pass only members that
    are already known to be an even-count remainder."""
    shuffled = list(units)
    random.shuffle(shuffled)
    return [(shuffled[i], shuffled[i + 1]) for i in range(0, len(shuffled) - 1, 2)]


def team_matchup_stage2(
    teams: Sequence[tuple[uuid.UUID, uuid.UUID]],
    pair_count: Callable[[uuid.UUID, uuid.UUID], int],
) -> list[tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]]:
    """FR-019: pairs up already-formed teams into match-ups, minimizing the
    sum of pair_count across all 4 cross-team member combinations. Reused
    verbatim by fair_rotation's own doubles handling (US1) and individual
    mixed's second step (FR-025) — this is the one "team vs team" primitive
    in the whole domain, not something fixed_partner owns exclusively.
    Callers pass the opponent-only count here, since the teams are already
    fixed and only who faces whom is still open."""

    def cross_cost(
        team_x: tuple[uuid.UUID, uuid.UUID], team_y: tuple[uuid.UUID, uuid.UUID]
    ) -> int:
        return sum(pair_count(a, b) for a in team_x for b in team_y)

    return min_cost_pairing(teams, cross_cost)


# Up to 8 players (105 ways to form teams) every team split is tried; past
# that the search grows by an order of magnitude per court.
_JOINT_DOUBLES_MAX_PLAYERS = 8


def _all_pairings(units: list[T]) -> list[list[tuple[T, T]]]:
    if not units:
        return [[]]
    first, rest = units[0], units[1:]
    result = []
    for i, partner in enumerate(rest):
        for tail in _all_pairings(rest[:i] + rest[i + 1 :]):
            result.append([(first, partner), *tail])
    return result


def pair_doubles_matches(
    players: Sequence[uuid.UUID],
    teammate_count: Callable[[uuid.UUID, uuid.UUID], int],
    opponent_count: Callable[[uuid.UUID, uuid.UUID], int],
) -> list[tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]]:
    """Splits a multiple of 4 players into doubles matches: fewest repeat
    teammates first, then fewest repeat opponents. Pairing teammates first
    and only then matching teams can't see that a teammate split it treats
    as equal leaves the same two people facing each other again — with 4
    players there is only one way to match two teams, so the opponents were
    never considered at all. Up to `_JOINT_DOUBLES_MAX_PLAYERS` players,
    every split is compared on both counts; beyond that it falls back to
    the two steps (`stage2_pair_players` then `team_matchup_stage2`)."""
    if len(players) > _JOINT_DOUBLES_MAX_PLAYERS:
        return team_matchup_stage2(stage2_pair_players(players, teammate_count), opponent_count)

    Matchups = list[tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]]
    best: tuple[tuple[int, int], Matchups] | None = None
    for teams in _all_pairings(list(players)):
        teammate_total = sum(teammate_count(a, b) for a, b in teams)
        if best is not None and teammate_total > best[0][0]:
            continue
        matchups = team_matchup_stage2(teams, opponent_count)
        opponent_total = sum(
            opponent_count(a, b) for team_x, team_y in matchups for a in team_x for b in team_y
        )
        key = (teammate_total, opponent_total)
        if best is None or key < best[0]:
            best = (key, matchups)
    return best[1] if best is not None else []
