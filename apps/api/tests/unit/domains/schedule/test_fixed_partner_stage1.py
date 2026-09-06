"""Unit test: team-level stage 1 selection — priority = MAX of the two
members' wait_count (None = infinite), tie-broken by the earlier member's
joined_at (spec FR-018)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.schedule.algorithms import team_stage1_select


def _id() -> uuid.UUID:
    return uuid.uuid4()


def test_team_priority_is_max_of_members() -> None:
    now = datetime.now(UTC)
    team_hi = (( _id(), _id()), 5, 0, now, now)  # MAX = 5
    team_lo = (( _id(), _id()), 2, 2, now, now)  # MAX = 2
    selected = team_stage1_select([team_lo, team_hi], n_teams=1)
    assert selected == [team_hi[0]]


def test_either_member_never_played_gives_infinite_priority() -> None:
    now = datetime.now(UTC)
    never_played_pair = (( _id(), _id()), 100, None, now, now)
    finite_pair = (( _id(), _id()), 50, 50, now, now)
    selected = team_stage1_select([finite_pair, never_played_pair], n_teams=1)
    assert selected == [never_played_pair[0]]


def test_tie_broken_by_earlier_member_joined_at() -> None:
    t0 = datetime.now(UTC)
    early_team = (( _id(), _id()), None, None, t0, t0 + timedelta(minutes=5))
    late_team = (( _id(), _id()), None, None, t0 + timedelta(minutes=1), t0 + timedelta(minutes=2))
    selected = team_stage1_select([late_team, early_team], n_teams=1)
    assert selected == [early_team[0]]


def test_selects_top_n_teams() -> None:
    now = datetime.now(UTC)
    teams = [((_id(), _id()), i, i, now, now) for i in range(5)]
    selected = team_stage1_select(teams, n_teams=2)
    assert len(selected) == 2
    assert selected[0] == teams[4][0]  # highest wait_count first
    assert selected[1] == teams[3][0]
