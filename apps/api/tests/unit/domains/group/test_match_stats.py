"""Unit test: app.domains.group.match_stats — 033-match-record-derived-stats.
Pure functions, no database. `_Sim` below reproduces what the real write
path leaves behind (schedule/service.py's apply_score_delta() +
_advance_serve_state_and_snapshot()): live recorded scores, and a serve
snapshot taken AFTER each +1 — so these tests exercise the same data shape
production rows have (research.md Decision 3)."""

import uuid
from typing import get_args

import pytest

from app.domains.group import match_stats
from app.domains.group.match_stats import (
    ClutchResult,
    EffectivePoint,
    Participant,
    Placement,
    RawEvent,
    ServeSnapshot,
    Team,
    _wins,
    clutch_stats,
    effective_points,
    ending_stats,
    landing_distribution,
    momentum_stats,
    player_landings,
    serve_stats,
    tempo_stats,
)
from app.domains.schedule.schemas import EndingType as WriteSideEndingType
from app.domains.schedule.service import match_wins

A1, A2, B1, B2 = (uuid.uuid4() for _ in range(4))
DOUBLES = [
    Participant(A1, "A"),
    Participant(A2, "A"),
    Participant(B1, "B"),
    Participant(B2, "B"),
]
SINGLES = [Participant(A1, "A"), Participant(B1, "B")]


class _Sim:
    """Mirrors the live write path. `first_server` is the pre-match random
    pick that production never persists — the simulator knows it, the
    functions under test must cope without it."""

    def __init__(self, participants: list[Participant], first_server: Team = "A") -> None:
        self.team: dict[Team, list[uuid.UUID]] = {
            "A": [p.roster_entry_id for p in participants if p.team == "A"],
            "B": [p.roster_entry_id for p in participants if p.team == "B"],
        }
        self.score: dict[Team, int] = {"A": 0, "B": 0}
        self.serving: Team = first_server
        self.ref: dict[Team, uuid.UUID] = {"A": self.team["A"][0], "B": self.team["B"][0]}
        self.events: list[RawEvent] = []
        self.snapshots: dict[uuid.UUID, ServeSnapshot] = {}
        self.clock = 0.0

    def _station(self, team: Team) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """(right, left) for `team` at its current score parity."""
        ref = self.ref[team]
        other = next((p for p in self.team[team] if p != ref), None)
        return (ref, other) if self.score[team] % 2 == 0 else (other, ref)

    def plus(self, side: Team, after: float = 20.0, snapshot: bool = True) -> uuid.UUID:
        self.clock += after
        self.score[side] += 1
        if side != self.serving:
            current = self.ref[side]
            self.ref[side] = next((p for p in self.team[side] if p != current), current)
            self.serving = side
        event_id = uuid.uuid4()
        self.events.append(
            RawEvent(event_id, side, 1, self.score["A"], self.score["B"], self.clock)
        )
        if snapshot:
            a_right, a_left = self._station("A")
            b_right, b_left = self._station("B")
            self.snapshots[event_id] = ServeSnapshot(
                self.serving, self.ref[self.serving], a_right, a_left, b_right, b_left
            )
        return event_id

    def minus(self, side: Team, after: float = 5.0) -> None:
        self.clock += after
        self.score[side] -= 1
        self.events.append(
            RawEvent(uuid.uuid4(), side, -1, self.score["A"], self.score["B"], self.clock)
        )

    def points(self) -> list[EffectivePoint]:
        result = effective_points(self.events, self.score["A"], self.score["B"])
        assert result is not None
        return result


def _play(sides: str, participants: list[Participant] = DOUBLES) -> _Sim:
    sim = _Sim(participants)
    for side in sides:
        sim.plus("A" if side == "A" else "B")
    return sim


# ---------------------------------------------------------------- effective_points (T002)


def test_effective_points_without_corrections_reaccumulates_each_score() -> None:
    points = _play("ABA").points()
    assert [(p.side, p.score_a, p.score_b) for p in points] == [
        ("A", 1, 0),
        ("B", 1, 1),
        ("A", 2, 1),
    ]
    assert all((p.score_a, p.score_b) == (p.recorded_score_a, p.recorded_score_b) for p in points)


def test_minus_voids_that_sides_latest_point() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("A")
    sim.minus("A")
    sim.plus("B")
    assert [(p.side, p.score_a, p.score_b) for p in sim.points()] == [("A", 1, 0), ("B", 1, 1)]


def test_consecutive_minuses_void_the_two_latest_points_in_turn() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    sim.plus("A")
    sim.plus("A")
    sim.minus("A")
    sim.minus("A")
    points = sim.points()
    assert [p.event_id for p in points] == [first]


def test_out_of_order_void_reaccumulates_but_keeps_recorded_score() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("B")
    sim.minus("A")
    [only] = sim.points()
    assert (only.side, only.score_a, only.score_b) == ("B", 0, 1)
    assert (only.recorded_score_a, only.recorded_score_b) == (1, 1)


def test_effective_points_is_none_when_counts_disagree_with_final_score() -> None:
    sim = _play("AAB")
    assert effective_points(sim.events, 3, 1) is None
    assert effective_points(sim.events, 2, 1) is not None


def test_minus_with_nothing_left_to_void_makes_the_history_unusable() -> None:
    events = [RawEvent(uuid.uuid4(), "A", -1, 0, 0, 1.0)]
    assert effective_points(events, 0, 0) is None


def test_gap_is_clean_only_when_the_raw_predecessor_is_an_effective_point() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")  # first raw event -> clean
    sim.plus("B")  # predecessor effective -> clean
    sim.plus("B")  # will be voided
    sim.minus("B")
    sim.plus("A")  # predecessor is a -1 -> not clean
    sim.plus("A")  # predecessor effective -> clean
    assert [p.gap_is_clean for p in sim.points()] == [True, True, False, True]


def test_gap_is_not_clean_right_after_a_point_that_gets_voided_later() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("B")  # voided below, out of order
    sim.plus("A")  # its raw predecessor is that voided +1
    sim.minus("B")
    assert [p.gap_is_clean for p in sim.points()] == [True, False]


def test_first_effective_point_is_not_clean_when_it_is_not_the_first_raw_event() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.minus("A")
    sim.plus("B")
    assert [p.gap_is_clean for p in sim.points()] == [False]


# ---------------------------------------------------------------- serve_stats (T009)


def test_serve_stats_attributes_each_point_to_the_previous_points_snapshot() -> None:
    # Worked example (A serves first, refs a1/b1): A A B B A -> 3:2.
    #  P1 excluded. P2: a1 serves to b2, A wins. P3: a1 serves to b1, B wins.
    #  P4: b2 serves to a2, B wins. P5: b2 serves to a1, A wins.
    sim = _play("AABBA")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    assert result.excluded_points == 1

    team_a, team_b = result.teams["A"], result.teams["B"]
    assert (team_a.serve_points_won, team_a.serve_points_total) == (1, 2)
    assert (team_a.receive_points_won, team_a.receive_points_total) == (1, 2)
    assert (team_b.serve_points_won, team_b.serve_points_total) == (1, 2)
    assert (team_b.receive_points_won, team_b.receive_points_total) == (1, 2)
    # Regression guard: reading each point's OWN (post-point) snapshot would
    # make every serve a won serve.
    assert team_a.serve_points_won < team_a.serve_points_total

    def counts(player: uuid.UUID) -> tuple[int, int, int, int]:
        c = result.players[player]
        return (
            c.serve_points_won,
            c.serve_points_total,
            c.receive_points_won,
            c.receive_points_total,
        )

    assert counts(A1) == (1, 2, 1, 1)
    assert counts(A2) == (0, 0, 0, 1)
    assert counts(B1) == (0, 0, 1, 1)
    assert counts(B2) == (1, 2, 0, 1)


def test_serve_stats_lists_all_four_doubles_players_in_participant_order() -> None:
    sim = _play("AA")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    assert list(result.players) == [A1, A2, B1, B2]
    assert result.players[B2].serve_points_total == 0


def test_serve_stats_totals_plus_excluded_equal_total_points() -> None:
    sim = _play("ABBABAABBBA")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    served = result.teams["A"].serve_points_total + result.teams["B"].serve_points_total
    assert served + result.excluded_points == len(sim.points())
    assert result.teams["A"].serve_points_total == result.teams["B"].receive_points_total
    assert result.teams["B"].serve_points_total == result.teams["A"].receive_points_total


def test_serve_stats_follows_the_restored_state_after_an_ordinary_undo() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("B")
    sim.minus("B")  # undo the side-out; A is serving again
    sim.plus("A")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    assert result.excluded_points == 1
    assert (result.teams["A"].serve_points_won, result.teams["A"].serve_points_total) == (1, 1)
    assert result.teams["B"].serve_points_total == 0


def test_serve_stats_excludes_a_point_whose_previous_snapshot_is_at_a_different_score() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("B")
    sim.minus("A")  # out of order: B's snapshot was taken at 1:1, the score is now 0:1
    sim.plus("A")
    sim.plus("A")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    # 3 effective points: the first, plus the one right after the mismatch.
    assert result.excluded_points == 2
    assert result.teams["A"].serve_points_total + result.teams["B"].serve_points_total == 1


def test_serve_stats_excludes_a_point_whose_previous_point_has_no_snapshot() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A", snapshot=False)  # e.g. scored before 030 shipped
    sim.plus("A")
    sim.plus("B")
    result = serve_stats(sim.points(), sim.snapshots, DOUBLES)
    assert result is not None
    assert result.excluded_points == 2
    assert (result.teams["A"].serve_points_won, result.teams["A"].serve_points_total) == (0, 1)


def test_serve_stats_is_none_without_any_snapshot() -> None:
    sim = _Sim(DOUBLES)
    for side in ("A", "B", "A"):
        sim.plus(side, snapshot=False)  # type: ignore[arg-type]
    assert serve_stats(sim.points(), sim.snapshots, DOUBLES) is None


def test_serve_stats_is_none_when_every_point_is_excluded() -> None:
    sim = _play("A")
    assert serve_stats(sim.points(), sim.snapshots, DOUBLES) is None


def test_singles_has_no_player_level_and_still_counts_receiving() -> None:
    # At 1:0 the server (A, odd) stands left while B (even) is recorded on
    # the right — the same-named court on B's side is empty, so the receiver
    # falls back to B's only player. Team-level numbers must be unaffected.
    sim = _play("AAB", SINGLES)
    result = serve_stats(sim.points(), sim.snapshots, SINGLES)
    assert result is not None
    assert result.players == {}
    assert (result.teams["A"].serve_points_won, result.teams["A"].serve_points_total) == (1, 2)
    assert (result.teams["B"].receive_points_won, result.teams["B"].receive_points_total) == (1, 2)


# ---------------------------------------------------------------- momentum_stats (T015)


def test_longest_run_reports_score_before_and_after() -> None:
    result = momentum_stats(_play("ABBBA").points())
    run_a, run_b = result.longest_runs
    assert (run_b.team, run_b.length) == ("B", 3)
    assert (run_b.start_score_a, run_b.start_score_b) == (1, 0)
    assert (run_b.end_score_a, run_b.end_score_b) == (1, 3)
    assert (run_a.team, run_a.length) == ("A", 1)


def test_longest_run_tie_keeps_the_earliest() -> None:
    [run_a, _] = momentum_stats(_play("AABAA").points()).longest_runs
    assert run_a.length == 2
    assert (run_a.start_score_a, run_a.start_score_b) == (0, 0)
    assert (run_a.end_score_a, run_a.end_score_b) == (2, 0)


def test_scoreless_team_has_a_zero_run_and_zero_lead_with_no_scores() -> None:
    result = momentum_stats(_play("AAA").points())
    run_b, lead_b = result.longest_runs[1], result.max_leads[1]
    assert (run_b.team, run_b.length) == ("B", 0)
    assert (run_b.start_score_a, run_b.end_score_b) == (None, None)
    assert (lead_b.team, lead_b.margin, lead_b.score_a, lead_b.score_b) == ("B", 0, None, None)


def test_max_lead_reports_the_first_time_the_margin_was_reached() -> None:
    # A leads by 2 at 2:0, then again at 3:1 — report 2:0.
    [lead_a, lead_b] = momentum_stats(_play("AABA").points()).max_leads
    assert (lead_a.margin, lead_a.score_a, lead_a.score_b) == (2, 2, 0)
    assert lead_b.margin == 0


def test_tie_then_same_leader_again_is_not_a_lead_change() -> None:
    assert momentum_stats(_play("ABA").points()).lead_changes == []


def test_tie_then_other_leader_is_one_lead_change() -> None:
    [change] = momentum_stats(_play("ABB").points()).lead_changes
    assert (change.new_leader, change.score_a, change.score_b) == ("B", 1, 2)


def test_first_lead_is_not_a_change_and_wire_to_wire_has_none() -> None:
    assert momentum_stats(_play("AAAA").points()).lead_changes == []


def test_lead_changes_are_listed_in_order() -> None:
    changes = momentum_stats(_play("ABBAA").points()).lead_changes
    assert [(c.new_leader, c.score_a, c.score_b) for c in changes] == [("B", 1, 2), ("A", 3, 2)]


def test_momentum_ignores_a_voided_point() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("B")
    sim.plus("A")
    sim.plus("A")  # a false lead for A, undone next
    sim.minus("A")
    sim.plus("B")
    result = momentum_stats(sim.points())
    assert result.lead_changes == []
    assert result.max_leads[0].margin == 0


# ---------------------------------------------------------------- tempo_stats (T020)


def test_tempo_measures_the_first_point_from_match_start() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A", after=12.0)
    sim.plus("B", after=30.0)
    result = tempo_stats(sim.points())
    assert result is not None
    assert result.counted_points == 2
    assert result.average_seconds == 21.0
    assert (result.longest_seconds, result.longest_score_a, result.longest_score_b) == (30.0, 1, 1)


def test_tempo_skips_gaps_that_contain_a_correction() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A", after=10.0)
    sim.plus("A", after=10.0)
    sim.minus("A", after=5.0)
    sim.plus("B", after=200.0)  # spans the correction: never the longest, never averaged
    sim.plus("B", after=20.0)
    result = tempo_stats(sim.points())
    assert result is not None
    assert result.counted_points == 2
    assert result.average_seconds == 15.0
    assert result.longest_seconds == 20.0


def test_tempo_average_is_rounded_to_one_decimal() -> None:
    sim = _Sim(DOUBLES)
    for after in (10.0, 10.0, 11.0):
        sim.plus("A", after=after)
    result = tempo_stats(sim.points())
    assert result is not None
    assert result.average_seconds == 10.3


def test_tempo_longest_tie_keeps_the_earliest() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A", after=15.0)
    sim.plus("B", after=15.0)
    result = tempo_stats(sim.points())
    assert result is not None
    assert (result.longest_score_a, result.longest_score_b) == (1, 0)


def test_tempo_is_none_when_no_gap_is_clean() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.minus("A")
    sim.plus("B")
    assert tempo_stats(sim.points()) is None


# ---------------------------------------------------------------- landing_distribution (T024)


def test_landing_distribution_splits_scored_and_lost_per_player() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("B")
    placements = {
        first: Placement(scorer_id=A1, loser_id=B2, landing=(0.8, 0.2)),
        second: Placement(scorer_id=B1, loser_id=A1, landing=(0.1, 0.9)),
    }
    result = landing_distribution(sim.points(), placements, DOUBLES)
    assert [r.roster_entry_id for r in result] == [A1, A2, B1, B2]
    by_id = {r.roster_entry_id: r for r in result}
    assert (by_id[A1].scored, by_id[A1].scored_total) == ([(0.8, 0.2)], 1)
    assert (by_id[A1].lost, by_id[A1].lost_total) == ([(0.1, 0.9)], 1)
    assert (by_id[B2].lost, by_id[B2].lost_total) == ([(0.8, 0.2)], 1)
    assert (by_id[A2].scored, by_id[A2].lost, by_id[A2].scored_total) == ([], [], 0)


def test_landing_without_coordinates_counts_toward_the_total_only() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("A")
    placements = {
        first: Placement(scorer_id=A1, loser_id=None, landing=(0.7, 0.5)),
        second: Placement(scorer_id=A1, loser_id=None, landing=None),
    }
    by_id = {r.roster_entry_id: r for r in landing_distribution(sim.points(), placements, DOUBLES)}
    assert (len(by_id[A1].scored), by_id[A1].scored_total) == (1, 2)


def test_out_of_bounds_coordinates_are_kept_verbatim() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    placements = {first: Placement(scorer_id=None, loser_id=B1, landing=(1.04, -0.12))}
    by_id = {r.roster_entry_id: r for r in landing_distribution(sim.points(), placements, DOUBLES)}
    assert by_id[B1].lost == [(1.04, -0.12)]


def test_placement_of_a_voided_point_is_ignored() -> None:
    sim = _Sim(DOUBLES)
    kept = sim.plus("A")
    voided = sim.plus("A")
    sim.minus("A")
    placements = {
        kept: Placement(scorer_id=A1, loser_id=None, landing=(0.6, 0.4)),
        voided: Placement(scorer_id=A1, loser_id=None, landing=(0.9, 0.9)),
    }
    by_id = {r.roster_entry_id: r for r in landing_distribution(sim.points(), placements, DOUBLES)}
    assert (by_id[A1].scored, by_id[A1].scored_total) == ([(0.6, 0.4)], 1)


def test_landing_distribution_is_empty_when_no_player_has_a_plotted_point() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("B")
    placements = {
        first: Placement(scorer_id=A1, loser_id=B1, landing=None),  # players, no coordinates
        second: Placement(scorer_id=None, loser_id=None, landing=(0.5, 0.5)),  # the reverse
    }
    assert landing_distribution(sim.points(), placements, DOUBLES) == []
    assert landing_distribution(sim.points(), {}, DOUBLES) == []


def test_player_landings_keeps_totals_even_when_nothing_is_plotted() -> None:
    """034 (T002): the dashboard needs "how many points was I credited
    with" from a match where the scorer picked players but never tapped a
    landing — `landing_distribution()` throws that away by design."""
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("B")
    placements = {
        first: Placement(scorer_id=A1, loser_id=B1, landing=None),
        second: Placement(scorer_id=B1, loser_id=A1, landing=None),
    }
    results = player_landings(sim.points(), placements, DOUBLES)
    assert list(results) == [A1, A2, B1, B2]
    assert (results[A1].scored_total, results[A1].lost_total) == (1, 1)
    assert (results[B1].scored_total, results[B1].lost_total) == (1, 1)
    assert results[A1].scored == [] and results[A1].lost == []
    assert landing_distribution(sim.points(), placements, DOUBLES) == []


# ---------------------------------------------------------------- clutch_stats (034 T004)


def _clutch(sides: str, target: int = 21, cap: int = 30) -> ClutchResult:
    return clutch_stats(_play(sides).points(), target, cap)


@pytest.mark.parametrize("target", [1, 11, 15, 21])
@pytest.mark.parametrize("extra", [0, 9])
def test_wins_matches_the_write_paths_rule_everywhere(target: int, extra: int) -> None:
    cap = target + extra
    for x in range(cap + 1):
        for y in range(cap + 1):
            assert _wins(x, y, target, cap) == match_wins(x, y, target, cap), (x, y)


def test_endgame_starts_once_either_side_reaches_target_minus_three() -> None:
    # 17:0 -> the 18th point is still played at 17, so it is NOT endgame;
    # every point from 18:0 on is.
    result = _clutch("A" * 17 + "A" + "BB" + "AAA")
    assert result.endgame_from == 18
    assert result.endgame is not None
    assert (result.endgame["A"].won, result.endgame["A"].total) == (3, 5)
    assert (result.endgame["B"].won, result.endgame["B"].total) == (2, 5)


def test_endgame_also_covers_the_deuce_that_follows_it() -> None:
    result = _clutch("AB" * 20 + "ABABBB")
    assert result.endgame is not None
    # A reaches 18 first, at 18:17 -> 35 points played before the phase.
    assert result.endgame["A"].total == 46 - 35


def test_endgame_does_not_apply_below_an_eleven_point_target() -> None:
    result = _clutch("A" * 7, target=7, cap=10)
    assert result.endgame_from is None and result.endgame is None
    assert result.by_state["A"].tied.total == 1  # the rest still works
    assert result.match_points["A"].converted_on == 1


def test_deuce_is_none_when_the_match_never_got_there() -> None:
    assert _clutch("A" * 21).deuce is None
    assert _clutch("AB" * 15 + "A" * 6).deuce is None  # 21:15


def test_deuce_and_match_points_through_a_long_tiebreak() -> None:
    """quickstart scenario 1: alternate to 20:20 (A scoring first, so A
    already holds a match point at 20:19 — nobody reaches 20:20 without one
    side having held one), then A B A B B B -> 22:24."""
    result = _clutch("AB" * 20 + "ABABBB")
    assert result.deuce is not None
    assert (result.deuce["A"].won, result.deuce["A"].total) == (2, 6)
    assert (result.deuce["B"].won, result.deuce["B"].total) == (4, 6)
    a, b = result.match_points["A"], result.match_points["B"]
    assert (a.held, a.converted_on, a.saved) == (3, None, 0)  # 20:19, 21:20, 22:21
    assert (b.held, b.converted_on, b.saved) == (1, 1, 3)  # 22:23


def test_winner_converts_on_the_third_match_point() -> None:
    # 20:18 (MP1) -> 20:19 (MP2) -> 20:20 -> 21:20 (MP3) -> 22:20
    result = _clutch("AB" * 18 + "AA" + "BB" + "AA")
    a, b = result.match_points["A"], result.match_points["B"]
    assert (a.held, a.converted_on, a.saved) == (3, 3, 0)
    assert (b.held, b.converted_on, b.saved) == (0, None, 2)


def test_point_before_the_cap_is_a_match_point_for_both_sides() -> None:
    result = _clutch("AB" * 29 + "A")  # 29:29, cap 30
    a, b = result.match_points["A"], result.match_points["B"]
    assert a.converted_on == a.held and b.converted_on is None
    # 29:29 counts once for each side; B never converts.
    assert a.saved == b.held
    assert a.saved + b.saved + 1 == a.held + b.held


def test_no_extension_rule_makes_the_last_tie_sudden_death() -> None:
    result = _clutch("AB" * 20 + "B", target=21, cap=21)  # 20:20 -> 20:21
    a, b = result.match_points["A"], result.match_points["B"]
    assert (a.held, a.converted_on) == (2, None)  # 20:19, then 20:20 (shared)
    assert (b.held, b.converted_on, b.saved) == (1, 1, 2)


def test_score_state_is_judged_before_the_point_is_played() -> None:
    result = _clutch("AAB")
    a, b = result.by_state["A"], result.by_state["B"]
    assert (a.tied.won, a.tied.total) == (1, 1)  # a match's first point is always tied
    assert (a.leading.won, a.leading.total) == (1, 2)
    assert (a.trailing.won, a.trailing.total) == (0, 0)
    assert (b.tied.won, b.tied.total) == (0, 1)
    assert (b.trailing.won, b.trailing.total) == (1, 2)
    assert (b.leading.won, b.leading.total) == (0, 0)


@pytest.mark.parametrize(
    "sides",
    ["AB" * 20 + "ABABBB", "AB" * 29 + "A", "A" * 21, "BBBBB" + "AB" * 13 + "A" * 7 + "BA"],
)
def test_clutch_invariants_hold_for_a_completed_match(sides: str) -> None:
    sim = _play(sides)
    points = sim.points()
    result = clutch_stats(points, 21, 30)
    winner: Team = points[-1].side
    loser: Team = "B" if winner == "A" else "A"

    for team in ("A", "B"):
        state = result.by_state[team]
        assert state.leading.total + state.tied.total + state.trailing.total == len(points)
    a, b = result.by_state["A"], result.by_state["B"]
    assert a.leading.total == b.trailing.total and a.trailing.total == b.leading.total
    assert a.tied.total == b.tied.total
    for mine, theirs in ((a.leading, b.trailing), (a.tied, b.tied), (a.trailing, b.leading)):
        assert mine.won + theirs.won == mine.total
    for phase in (result.endgame, result.deuce):
        if phase is not None:
            assert phase["A"].total == phase["B"].total
            assert phase["A"].won + phase["B"].won == phase["A"].total

    won, lost = result.match_points[winner], result.match_points[loser]
    assert won.held >= 1 and won.converted_on == won.held
    assert lost.converted_on is None
    assert won.saved + lost.saved + 1 == won.held + lost.held


def test_clutch_uses_the_reaccumulated_score_not_the_recorded_one() -> None:
    sim = _Sim(DOUBLES)
    sim.plus("A")
    sim.plus("B")  # recorded at 1:1, but re-accumulates to 0:1 once A's point is voided
    sim.minus("A")
    sim.plus("B")
    result = clutch_stats(sim.points(), 21, 30)
    b = result.by_state["B"]
    assert (b.tied.total, b.leading.total) == (1, 1)  # second point starts at 0:1, not 1:1


# ---------------------------------------------------------------- 035 EndingType (T003)


def test_ending_type_is_the_same_set_on_the_write_side_and_in_this_pure_module() -> None:
    """The pure module can't import `schedule.schemas`, so it keeps its own
    Literal. Adding a sixth kind to one and not the other would silently drop
    it from every statistic — same reason 034 pins `_wins` to `match_wins`."""
    assert get_args(match_stats.EndingType) == get_args(WriteSideEndingType)
    assert match_stats.ERROR_TYPES == tuple(
        kind for kind in get_args(WriteSideEndingType) if kind != "winner"
    )


# ---------------------------------------------------------------- ending_stats (035 T014)


def _ending(
    scorer: uuid.UUID | None, loser: uuid.UUID | None, ending: str | None
) -> Placement:
    return Placement(scorer_id=scorer, loser_id=loser, landing=None, ending=ending)  # type: ignore[arg-type]


def test_winner_goes_to_the_scorer_and_an_error_to_the_loser() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("A")
    third = sim.plus("B")
    placements = {
        first: _ending(A1, B1, "winner"),
        second: _ending(A2, B1, "net"),
        third: _ending(B2, A1, "out"),
    }

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    a1, a2, b1, b2 = (result.players[p] for p in (A1, A2, B1, B2))
    assert (a1.winners, a1.opponent_errors, a1.beaten_by_winners, a1.own_errors) == (1, 0, 0, 1)
    assert (a2.winners, a2.opponent_errors, a2.own_errors) == (0, 1, 0)
    assert (b1.beaten_by_winners, b1.own_errors, b1.own_errors_by_type["net"]) == (1, 1, 1)
    assert (b2.winners, b2.opponent_errors) == (0, 1)
    assert a1.own_errors_by_type == {"out": 1, "net": 0, "serve_fault": 0, "other_error": 0}
    assert (result.recorded_points, result.total_points) == (3, 3)


def test_an_ending_without_the_matching_player_counts_for_the_team_only() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    second = sim.plus("A")
    placements = {
        first: _ending(None, None, "winner"),
        second: _ending(None, B1, "serve_fault"),
    }

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    assert (result.teams["A"].winners, result.teams["B"].errors) == (1, 1)
    assert result.teams["B"].errors_by_type["serve_fault"] == 1
    assert all(p.winners == 0 and p.opponent_errors == 0 for p in result.players.values())
    assert result.players[B1].own_errors == 1
    assert result.recorded_points == 2


def test_each_player_split_adds_up_to_their_landing_totals() -> None:
    sim = _Sim(DOUBLES)
    kinds = ["winner", "net", None, "out", None, "other_error", "winner"]
    sides = "AABBABA"
    placements = {}
    for side, kind in zip(sides, kinds, strict=True):
        event_id = sim.plus(side)  # type: ignore[arg-type]
        scorer, loser = (A1, B2) if side == "A" else (B1, A2)
        placements[event_id] = _ending(scorer, loser, kind)

    result = ending_stats(sim.points(), placements, DOUBLES)
    landings = player_landings(sim.points(), placements, DOUBLES)

    assert result is not None
    for player_id, split in result.players.items():
        assert split.winners + split.opponent_errors + split.scored_unrecorded == (
            landings[player_id].scored_total
        ), player_id
        assert split.beaten_by_winners + split.own_errors + split.lost_unrecorded == (
            landings[player_id].lost_total
        ), player_id
    assert result.players[A1].scored_unrecorded == 1
    assert result.players[A2].lost_unrecorded == 1
    assert (result.recorded_points, result.total_points) == (5, 7)


def test_team_errors_are_the_ones_that_team_committed() -> None:
    sim = _Sim(DOUBLES)
    placements = {}
    for kind in ("out", "net", "net", "serve_fault", "winner"):
        placements[sim.plus("A")] = _ending(A1, B1, kind)  # A scores, so B errs
    placements[sim.plus("B")] = _ending(B1, A1, "other_error")

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    assert (result.teams["A"].winners, result.teams["A"].errors) == (1, 1)
    assert (result.teams["B"].winners, result.teams["B"].errors) == (0, 4)
    assert result.teams["B"].errors_by_type == {
        "out": 1, "net": 2, "serve_fault": 1, "other_error": 0
    }
    for team in result.teams.values():
        assert sum(team.errors_by_type.values()) == team.errors
    # Invariant: A's winners + B's errors = A's recorded points.
    assert result.teams["A"].winners + result.teams["B"].errors == 5
    assert result.recorded_points == 6


def test_recorded_points_counts_only_effective_points_with_an_ending() -> None:
    sim = _Sim(DOUBLES)
    with_ending = sim.plus("A")
    without = sim.plus("B")
    no_row = sim.plus("A")
    placements = {
        with_ending: _ending(A1, B1, "winner"),
        without: _ending(B1, A1, None),
    }
    assert no_row not in placements

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    assert (result.recorded_points, result.total_points) == (1, 3)


def test_a_voided_point_contributes_to_nothing() -> None:
    sim = _Sim(DOUBLES)
    kept = sim.plus("A")
    voided = sim.plus("A")
    sim.minus("A")
    placements = {
        kept: _ending(A1, B1, "winner"),
        voided: _ending(A1, B1, "net"),
    }

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    assert (result.teams["A"].winners, result.teams["B"].errors) == (1, 0)
    assert (result.players[A1].winners, result.players[A1].opponent_errors) == (1, 0)
    assert (result.recorded_points, result.total_points) == (1, 1)


def test_ending_stats_is_none_when_no_point_recorded_an_ending() -> None:
    sim = _Sim(DOUBLES)
    first = sim.plus("A")
    sim.plus("B")
    placements = {first: _ending(A1, B1, None)}

    assert ending_stats(sim.points(), placements, DOUBLES) is None
    assert ending_stats(sim.points(), {}, DOUBLES) is None


def test_players_follow_the_participants_order_and_include_all_zero_rows() -> None:
    sim = _Sim(DOUBLES)
    placements = {sim.plus("A"): _ending(A1, B1, "winner")}

    result = ending_stats(sim.points(), placements, DOUBLES)

    assert result is not None
    assert list(result.players) == [A1, A2, B1, B2]
    assert list(result.teams) == ["A", "B"]
    a2 = result.players[A2]
    assert (a2.roster_entry_id, a2.team) == (A2, "A")
    assert (
        a2.winners, a2.opponent_errors, a2.scored_unrecorded,
        a2.beaten_by_winners, a2.own_errors, a2.lost_unrecorded,
    ) == (0, 0, 0, 0, 0, 0)
    assert sum(a2.own_errors_by_type.values()) == 0
