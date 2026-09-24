"""Fairness simulation across every scheduling mechanism.

Plays whole sessions through the real schedule service against the test
database, with a controllable clock: every match lasts a random 8-15
minutes, the earliest-finishing match ends first, and the service's own
end-of-match hook (`_advance_after_terminal`) decides what each freed court
plays next — exactly the path a real "match over" takes. Round-based
mechanisms plan + start each new round once the previous one is done.

Per session it measures, for every player:
- matches played (how even is it, overall and within each round?),
- back-to-back starts (on court again with no rest), the longest run of
  them, and the longest wait between two matches (is anyone's schedule
  bunched up?),
- how often each pair ended up as teammates and as opponents (doubles).

Run with `-s` to see the report table."""

import random
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member import models as member_models
from app.domains.roster.models import RosterEntry
from app.domains.schedule import service
from app.domains.schedule.models import Match, MatchParticipant, Partnership

# groups.created_by_member_id references members; keep it in the metadata.
assert member_models.Member.__tablename__ == "members"

SESSION_START = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
SEEDS = (1, 2, 3)
BACK_TO_BACK = timedelta(seconds=30)


class _Clock(datetime):
    current = SESSION_START

    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def, override]
        return cls.current


@dataclass
class Scenario:
    label: str
    mechanism: str
    match_mode: str
    players: int
    courts: int
    rounds: int = 1
    continuous_minutes: int | None = None
    partner_source: str = "manual"
    formal_pairs: bool = False
    # Regression guards. Match counts must stay within one of each other
    # (overall and within every round) except where a whole-round bye makes
    # that impossible; the other two are the worst seen when this was
    # written plus a margin, so an ordinary seed-to-seed wobble passes but
    # a real regression doesn't.
    max_play_spread: int = 1
    max_opponent_repeat: int | None = None
    max_streak: int | None = None

    @property
    def round_based(self) -> bool:
        return self.continuous_minutes is None

    @property
    def key(self) -> str:
        """ASCII test id (pytest escapes the Chinese label, so `-k` can't
        match it)."""
        mode = "continuous" if not self.round_based else f"{self.rounds}rounds"
        source = f"-{self.partner_source}" if self.mechanism == "fixed_partner" else ""
        formal = "-formal" if self.formal_pairs else ""
        return (
            f"{self.mechanism}-{self.match_mode}-{self.players}p{self.courts}c"
            f"-{mode}{source}{formal}"
        )


@dataclass
class Report:
    scenario: Scenario
    plays: dict[uuid.UUID, int]
    round_spreads: list[int]
    back_to_back: dict[uuid.UUID, int]
    longest_streak: int
    longest_wait: timedelta
    teammates: Counter[frozenset[uuid.UUID]] = field(default_factory=Counter)
    opponents: Counter[frozenset[uuid.UUID]] = field(default_factory=Counter)

    @property
    def play_spread(self) -> int:
        return max(self.plays.values()) - min(self.plays.values())


async def _setup(session: AsyncSession, sc: Scenario) -> tuple[Group, list[Court], list[uuid.UUID]]:
    group = Group(
        name=sc.label,
        max_members=30,
        match_mode=sc.match_mode,
        scheduling_mechanism=sc.mechanism,
        partner_source=sc.partner_source,
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    courts = []
    for i in range(sc.courts):
        court = Court(group_id=group.id, name=f"場{i + 1}")
        session.add(court)
        await session.commit()
        courts.append(court)
    ids = []
    for i in range(sc.players):
        entry = RosterEntry(group_id=group.id, nickname=f"P{i + 1}", status="active")
        session.add(entry)
        await session.commit()
        ids.append(entry.id)
    if sc.formal_pairs:
        for i in range(0, sc.players - 1, 2):
            session.add(Partnership(group_id=group.id, player_a_id=ids[i], player_b_id=ids[i + 1]))
        await session.commit()
    await session.refresh(group)
    return group, courts, ids


async def _play_until_round_done(
    session: AsyncSession, group: Group, rng: random.Random, deadline: datetime | None
) -> None:
    """Ends matches one at a time, earliest finish first, letting the
    service refill courts, until nothing is on court (round over) or the
    clock passes `deadline` (continuous rotation never runs dry)."""
    finish_at: dict[uuid.UUID, datetime] = {}
    while True:
        playing = (
            await session.execute(
                select(Match).where(Match.group_id == group.id, Match.status == "in_progress")
            )
        ).scalars().all()
        if not playing:
            queued = (
                await session.execute(
                    select(Match.id).where(Match.group_id == group.id, Match.status == "queued")
                )
            ).scalars().all()
            assert not queued, "courts went idle while matches were still queued"
            return
        for match in playing:
            if match.id not in finish_at:
                finish_at[match.id] = _Clock.current + timedelta(minutes=rng.uniform(8, 15))
        match = min(playing, key=lambda m: finish_at[m.id])
        _Clock.current = finish_at[match.id]
        if deadline is not None and _Clock.current > deadline:
            return
        await session.execute(
            update(Match)
            .where(Match.id == match.id)
            .values(status="completed", winner_team="A", score_a=21, ended_at=_Clock.current)
        )
        await session.commit()
        await session.refresh(match)
        await service._advance_after_terminal(session, match)


async def _run(session: AsyncSession, sc: Scenario, seed: int) -> Report:
    rng = random.Random(seed)
    # The service shuffles call-up order and random pairings with the
    # module-level `random`; seed it too so a seed means one session. Roster
    # ids are still random uuids, so tie-breaks can differ between runs.
    random.seed(seed)
    _Clock.current = SESSION_START
    group, _courts, ids = await _setup(session, sc)

    if not sc.round_based:
        group = await service.set_continuous_rotation(session, group, True)
    rounds = sc.rounds if sc.round_based else 1
    deadline = (
        None if sc.round_based else SESSION_START + timedelta(minutes=sc.continuous_minutes or 0)
    )
    for _ in range(rounds):
        group = await service.plan_next_round(session, group)
        group = await service.start_planned_round(session, group)
        await _play_until_round_done(session, group, rng, deadline)

    rows = (
        await session.execute(
            select(Match, MatchParticipant)
            .join(MatchParticipant, MatchParticipant.match_id == Match.id)
            # A continuous session is cut off mid-match: count those on court
            # at the cut-off as playing, or everyone on court looks one
            # match behind whoever is waiting.
            .where(Match.group_id == group.id, Match.status.in_(("completed", "in_progress")))
        )
    ).all()
    lineups: dict[uuid.UUID, dict[str, list[uuid.UUID]]] = defaultdict(lambda: {"A": [], "B": []})
    matches: dict[uuid.UUID, Match] = {}
    for match, participant in rows:
        matches[match.id] = match
        lineups[match.id][participant.team].append(participant.roster_entry_id)

    plays: dict[uuid.UUID, int] = dict.fromkeys(ids, 0)
    per_round: dict[int, Counter[uuid.UUID]] = defaultdict(Counter)
    spans: dict[uuid.UUID, list[tuple[datetime, datetime]]] = defaultdict(list)
    teammates: Counter[frozenset[uuid.UUID]] = Counter()
    opponents: Counter[frozenset[uuid.UUID]] = Counter()
    for match_id, sides in lineups.items():
        match = matches[match_id]
        assert match.started_at is not None
        for pid in sides["A"] + sides["B"]:
            plays[pid] += 1
            per_round[match.round_number][pid] += 1
            if match.ended_at is not None:
                spans[pid].append((match.started_at, match.ended_at))
        for side in (sides["A"], sides["B"]):
            if len(side) == 2:
                teammates[frozenset(side)] += 1
        for a in sides["A"]:
            for b in sides["B"]:
                opponents[frozenset((a, b))] += 1

    round_spreads = []
    for counts in per_round.values():
        values = [counts.get(pid, 0) for pid in ids]
        round_spreads.append(max(values) - min(values))

    back_to_back: dict[uuid.UUID, int] = dict.fromkeys(ids, 0)
    longest_streak = 1
    longest_wait = timedelta(0)
    for pid, player_spans in spans.items():
        player_spans.sort()
        longest_wait = max(longest_wait, player_spans[0][0] - SESSION_START)
        streak = 1
        for (_s0, e0), (s1, _e1) in zip(player_spans, player_spans[1:], strict=False):
            rest = s1 - e0
            longest_wait = max(longest_wait, rest)
            if rest < BACK_TO_BACK:
                back_to_back[pid] += 1
                streak += 1
                longest_streak = max(longest_streak, streak)
            else:
                streak = 1

    return Report(sc, plays, round_spreads, back_to_back, longest_streak, longest_wait,
                  teammates, opponents)


def _summary(reports: list[Report]) -> str:
    """One line per metric: the mean over seeds, and the worst seed."""
    sc = reports[0].scenario
    per_match = 2 if sc.match_mode == "singles" else 4
    on_court = min(sc.players // per_match * per_match, sc.courts * per_match)

    def stat(values: list[float], fmt: str = "{:.1f}") -> str:
        return f"{fmt.format(sum(values) / len(values))}(最差{fmt.format(max(values))})"

    lines = [
        f"\n[{sc.label}] 場上最多 {on_court}/{sc.players} 人",
        "    上場次數差: " + stat([r.play_spread for r in reports])
        + ", 每輪內差距: " + stat([max(r.round_spreads) for r in reports]),
        "    連打總次數: " + stat([sum(r.back_to_back.values()) for r in reports])
        + ", 單人最長連打: " + stat([r.longest_streak for r in reports])
        + " 場, 最長等待: "
        + stat([r.longest_wait.total_seconds() / 60 for r in reports], "{:.0f}") + " 分",
    ]
    if sc.match_mode == "doubles":
        pairs = sc.players * (sc.players - 1) // 2
        lines.append(
            "    隊友: 同一組最多 " + stat([max(r.teammates.values(), default=0) for r in reports])
            + " 次, 當過隊友的組數 " + stat([len(r.teammates) for r in reports]) + f"/{pairs}"
        )
        lines.append(
            "    對手: 同一組最多 " + stat([max(r.opponents.values(), default=0) for r in reports])
            + " 次, 最少 " + stat([min(r.opponents.values(), default=0) for r in reports])
            + " 次, 交手過的組數 " + stat([len(r.opponents) for r in reports]) + f"/{pairs}"
        )
    return "\n".join(lines)


SCENARIOS = [
    Scenario("單打循環 5人2場 3輪", "fair_rotation", "singles", 5, 2, rounds=3, max_streak=6),
    Scenario("單打循環 8人3場 2輪", "fair_rotation", "singles", 8, 3, rounds=2, max_streak=5),
    Scenario("雙打輪替 8人2場 10輪", "fair_rotation", "doubles", 8, 2, rounds=10,
             max_opponent_repeat=4),
    Scenario("雙打輪替 10人2場 10輪", "fair_rotation", "doubles", 10, 2, rounds=10,
             max_opponent_repeat=5, max_streak=6),
    Scenario("雙打輪替 7人2場 10輪", "fair_rotation", "doubles", 7, 2, rounds=10,
             max_opponent_repeat=4, max_streak=3),
    # 12 of 13 (and below, 8 of 9) are on court at any time, so nearly
    # everyone plays nearly every match, and the longest run is the metric
    # most sensitive to tie-break order: before `random` was seeded it
    # ranged 5-7 and 6-10 over five repeats. These two guards only catch a
    # gross regression.
    Scenario("雙打輪替 13人3場 10輪", "fair_rotation", "doubles", 13, 3, rounds=10,
             max_opponent_repeat=4, max_streak=8),
    Scenario("雙打連續輪轉 10人2場 3小時", "fair_rotation", "doubles", 10, 2,
             continuous_minutes=180, max_opponent_repeat=10, max_streak=7),
    Scenario("雙打連續輪轉 9人2場 3小時", "fair_rotation", "doubles", 9, 2,
             continuous_minutes=180, max_opponent_repeat=11, max_streak=10),
    Scenario("個人混雙 6人2場 2輪", "individual_mixed", "doubles", 6, 2, rounds=2,
             max_opponent_repeat=9, max_streak=4),
    Scenario("個人混雙 8人2場 2輪", "individual_mixed", "doubles", 8, 2, rounds=2,
             max_opponent_repeat=5),
    Scenario("個人混雙 9人2場 2輪", "individual_mixed", "doubles", 9, 2, rounds=2,
             max_opponent_repeat=8, max_streak=11),
    Scenario("固定搭檔(正式) 8人2場 3輪", "fixed_partner", "doubles", 8, 2, rounds=3,
             formal_pairs=True, max_opponent_repeat=4),
    Scenario("固定搭檔(自動) 8人2場 3輪", "fixed_partner", "doubles", 8, 2, rounds=3,
             partner_source="auto", max_opponent_repeat=4),
    # 7 members: one sits out a whole round each round (the bye), so over 4
    # rounds whoever never drew it has played 2 more than whoever did.
    Scenario("固定搭檔(自動) 7人2場 4輪", "fixed_partner", "doubles", 7, 2, rounds=4,
             partner_source="auto", max_play_spread=2, max_opponent_repeat=4, max_streak=5),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.key for s in SCENARIOS])
async def test_schedule_fairness(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, scenario: Scenario
) -> None:
    monkeypatch.setattr(service, "datetime", _Clock)
    reports = [await _run(db_session, scenario, seed=seed) for seed in SEEDS]
    print(_summary(reports))

    for report in reports:
        assert report.play_spread <= scenario.max_play_spread
        assert max(report.round_spreads) <= scenario.max_play_spread
        if scenario.max_opponent_repeat is not None:
            assert max(report.opponents.values()) <= scenario.max_opponent_repeat
        if scenario.max_streak is not None:
            assert report.longest_streak <= scenario.max_streak


# --- 037-rest-ready-toggle SC-004: resting is not a way to jump the queue ---

REST_PLAYERS = 10
REST_COURTS = 2
REST_MINUTES = 360
# More seeds than SEEDS: roster ids are random uuids, so tie-breaks — and
# with them each seed's numbers — vary from run to run; pooling six longer
# sessions keeps that noise well inside the tolerance.
REST_SEEDS = (1, 2, 3, 4, 5, 6)
# Only these (by join order) ever rest; everyone else stays ready and is the
# yardstick a returning player is compared against.
RESTLESS = (0, 1, 2)
REST_PROBABILITY = 0.3
RETURN_PROBABILITY = 0.15


@dataclass
class RestEpisode:
    player: uuid.UUID
    wait_before: int | None
    wait_after: int | None = None
    # Matches that went on court from the return until the player rested
    # again or the session ended, and how many of them the player was in.
    window_matches: int = 0
    window_plays: int = 0
    # The same window's play count for every always-ready player.
    ready_plays: dict[uuid.UUID, int] = field(default_factory=dict)
    open: bool = True
    # Index into the recorded stage-1 selections at the moment of return.
    selection_index: int | None = None

    @property
    def excess(self) -> float | None:
        """Share of the window's matches the returning player played, minus
        the median always-ready player's share — > 0 means they played more
        than a typical player who never left."""
        if self.window_matches == 0 or not self.ready_plays:
            return None
        rates = sorted(n / self.window_matches for n in self.ready_plays.values())
        median = rates[len(rates) // 2]
        return self.window_plays / self.window_matches - median


async def _run_with_rests(
    session: AsyncSession, seed: int, selections: list[tuple[list, list, dict]]
) -> list[RestEpisode]:
    """A continuous-rotation session where players in RESTLESS rest and come
    back at random moments (via the real `set_rest_state()`), recording what
    SC-004 checks."""
    from app.domains.schedule.rest import set_rest_state

    rng = random.Random(seed)
    random.seed(seed)
    _Clock.current = SESSION_START
    sc = Scenario("rest", "fair_rotation", "doubles", REST_PLAYERS, REST_COURTS,
                  continuous_minutes=REST_MINUTES)
    group, _courts, ids = await _setup(session, sc)
    group = await service.set_continuous_rotation(session, group, True)
    group = await service.plan_next_round(session, group)
    group = await service.start_planned_round(session, group)
    restless = {ids[i] for i in RESTLESS}
    always_ready = [pid for pid in ids if pid not in restless]
    episodes: list[RestEpisode] = []
    open_by_player: dict[uuid.UUID, RestEpisode] = {}
    resting: set[uuid.UUID] = set()
    deadline = SESSION_START + timedelta(minutes=REST_MINUTES)
    finish_at: dict[uuid.UUID, datetime] = {}
    counted: set[uuid.UUID] = set()

    async def entry(pid: uuid.UUID) -> RosterEntry:
        result = await session.execute(select(RosterEntry).where(RosterEntry.id == pid))
        return result.scalar_one()

    while True:
        playing = (
            await session.execute(
                select(Match).where(Match.group_id == group.id, Match.status == "in_progress")
            )
        ).scalars().all()
        # Count every match that has gone on court into the open windows.
        for match in playing:
            if match.id in counted:
                continue
            counted.add(match.id)
            on_court = set(
                (
                    await session.execute(
                        select(MatchParticipant.roster_entry_id).where(
                            MatchParticipant.match_id == match.id
                        )
                    )
                ).scalars()
            )
            for episode in episodes:
                if episode.open and episode.wait_after is not None:
                    episode.window_matches += 1
                    episode.window_plays += episode.player in on_court
                    for pid in always_ready:
                        seen = episode.ready_plays.get(pid, 0)
                        episode.ready_plays[pid] = seen + (pid in on_court)
        if not playing:
            return episodes
        for match in playing:
            finish_at.setdefault(match.id, _Clock.current + timedelta(minutes=rng.uniform(8, 15)))
        match = min(playing, key=lambda m: finish_at[m.id])
        _Clock.current = finish_at[match.id]
        if _Clock.current > deadline:
            return episodes
        await session.execute(
            update(Match)
            .where(Match.id == match.id)
            .values(status="completed", winner_team="A", score_a=21, ended_at=_Clock.current)
        )
        await session.commit()
        await session.refresh(match)
        await service._advance_after_terminal(session, match)
        await session.refresh(group)

        busy = set(
            (
                await session.execute(
                    select(MatchParticipant.roster_entry_id)
                    .join(Match, Match.id == MatchParticipant.match_id)
                    .where(Match.group_id == group.id, Match.status == "in_progress")
                )
            ).scalars()
        )
        idle_restless = sorted(pid for pid in restless - resting - busy)
        if idle_restless and rng.random() < REST_PROBABILITY:
            pid = rng.choice(idle_restless)
            player = await entry(pid)
            episode = RestEpisode(pid, player.wait_count)
            episodes.append(episode)
            if pid in open_by_player:
                open_by_player[pid].open = False
            open_by_player[pid] = episode
            resting.add(pid)
            await set_rest_state(session, group, player, resting=True)
        elif resting and rng.random() < RETURN_PROBABILITY:
            pid = rng.choice(sorted(resting))
            resting.discard(pid)
            episode = open_by_player[pid]
            episode.selection_index = len(selections)
            await set_rest_state(session, group, await entry(pid), resting=False)
            episode.wait_after = (await entry(pid)).wait_count
        await session.refresh(group)


def _patch_rest_clock_and_selection(
    monkeypatch: pytest.MonkeyPatch, selections: list[tuple[list, list, dict]]
) -> None:
    from app.domains.schedule import rest as rest_module

    monkeypatch.setattr(service, "datetime", _Clock)
    monkeypatch.setattr(rest_module, "datetime", _Clock)
    real_select = service.stage1_select_players

    def recording_select(roster, n, histories=None, pair_cost=None):  # type: ignore[no-untyped-def]
        picked = real_select(roster, n, histories, pair_cost)
        selections.append((list(roster), list(picked), dict(histories or {})))
        return picked

    monkeypatch.setattr(service, "stage1_select_players", recording_select)


def _disable_rest_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """What scheduling did before research.md Decisions 3 and 4: rest counted
    straight through a break, and no played credit on return. The wait
    count stays frozen either way (that is T008, not under test here)."""
    from app.domains.schedule import algorithms
    from app.domains.schedule import rest as rest_module

    def histories_ignoring_rest(matches, _periods=None):  # type: ignore[no-untyped-def]
        return algorithms.player_histories(matches)

    monkeypatch.setattr(service, "player_histories", histories_ignoring_rest)

    async def no_credit(*_args: object) -> int:
        return 0

    monkeypatch.setattr(rest_module, "_returning_credit", no_credit)


def _mean_excess(episodes: list[RestEpisode]) -> float:
    values = [e.excess for e in episodes if e.excess is not None]
    return sum(values) / len(values) if values else 0.0


def _jumped_ahead(episode: RestEpisode, selections: list[tuple[list, list, dict]]) -> bool:
    """At the first selection after the return that could pick the player:
    were they picked over someone who had waited strictly longer? (A
    wait_count of None — never played — outranks any number.)"""
    assert episode.selection_index is not None
    for roster, picked, _histories in selections[episode.selection_index:]:
        waits = {pid: wait for pid, wait, _joined in roster}
        if episode.player not in waits:
            continue
        if episode.player not in picked:
            return False
        own = waits[episode.player]
        return any(
            pid not in picked and _waited_longer(wait, own)
            for pid, wait in waits.items()
            if pid != episode.player
        )
    return False


def _waited_longer(other: int | None, own: int | None) -> bool:
    if own is None:
        return False  # nothing outranks "never played"
    if other is None:
        return True
    return other > own


# SC-004 tolerance (tasks.md T018, analyze B1). Mean excess — the returning
# player's share of the matches after their return minus the median
# always-ready player's — pooled over REST_SEEDS' returns. Measured
# 2026-09-19, three repeats, 10 players, 2 courts, 6 hours, REST/RETURN
# 0.3/0.15:
#   fixes off (research.md Decisions 3 and 4 disabled): +0.062 +0.053 +0.067
#   fixes on:                                           -0.003 -0.001 -0.060
# Worst cases -0.001 on vs +0.053 off; the midpoint, rounded down, is 0.02.
# An earlier setting (4 hours, 3 seeds, return 0.35) pooled as low as +0.028
# with the fixes off — rests too short to show much — so the rests were
# made longer rather than the tolerance squeezed.
MAX_RETURN_EXCESS = 0.02


@pytest.mark.asyncio
@pytest.mark.parametrize("fixes", ["on", "off"])
async def test_resting_is_not_a_shortcut(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, fixes: str
) -> None:
    """With the fixes on, a returning player keeps their wait count, never
    goes ahead of someone who waited longer, and doesn't then play more than
    those who never left. With them off, the same measure MUST trip — proof
    that it can catch the problem at all."""
    selections: list[tuple[list, list, dict]] = []
    _patch_rest_clock_and_selection(monkeypatch, selections)
    if fixes == "off":
        _disable_rest_fixes(monkeypatch)
    returned: list[RestEpisode] = []
    for seed in REST_SEEDS:
        episodes = await _run_with_rests(db_session, seed, selections)
        seed_returns = [e for e in episodes if e.wait_after is not None]
        print(
            f"\n[fixes {fixes} seed {seed}] rests {len(episodes)}, returns {len(seed_returns)}, "
            f"mean excess {_mean_excess(seed_returns):+.3f}"
        )
        returned.extend(seed_returns)

    assert len(returned) >= 6, "too few returns to say anything"
    pooled = _mean_excess(returned)
    if fixes == "off":
        assert pooled > MAX_RETURN_EXCESS
        return
    assert pooled <= MAX_RETURN_EXCESS
    for episode in returned:
        assert episode.wait_after == episode.wait_before  # FR-024
        assert not _jumped_ahead(episode, selections)
