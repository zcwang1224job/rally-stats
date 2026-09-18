"""Unit test: matchups.build() — 036-match-insights-benchmarks US2. No database."""

from datetime import UTC, datetime, timedelta

from app.domains.member import matchups
from app.domains.member.matchups import MatchupInput, MatchupRecord
from app.domains.member.player_identity import PlayerRef

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def ref(key: str, nickname: str | None = None) -> PlayerRef:
    member_id = key[2:] if key.startswith("m:") else None
    return PlayerRef(key=key, nickname=nickname or key, member_id=member_id)


def played(
    age_days: int,
    margin: int,
    *,
    partners: tuple[PlayerRef, ...] = (),
    opponents: tuple[PlayerRef, ...] = (),
) -> MatchupInput:
    return MatchupInput(
        ended_at=NOW - timedelta(days=age_days),
        won=margin > 0,
        margin=margin,
        is_doubles=bool(partners),
        partners=partners,
        opponents=opponents,
    )


def by_key(records: list[MatchupRecord]) -> dict[str, MatchupRecord]:
    return {record.player_key: record for record in records}


def test_no_matches() -> None:
    result = matchups.build([])
    assert result.partner_records == [] and result.opponent_records == []
    assert result.doubles_matches == 0
    assert result.overall_win_rate is None and result.doubles_win_rate is None
    assert result.highlights == matchups.MatchupHighlights(None, None, None, None)


def test_one_member_under_two_nicknames_is_one_row_named_as_in_their_latest_match() -> None:
    result = matchups.build(
        [
            played(5, 3, opponents=(ref("m:a", "阿哲"),)),
            played(1, -2, opponents=(ref("m:a", "Jay"),)),  # another group, newer
            played(9, 4, opponents=(ref("m:a", "阿哲"),)),
        ]
    )
    (record,) = result.opponent_records
    assert (record.player_key, record.nickname, record.member_id) == ("m:a", "Jay", "a")
    assert (record.matches, record.wins, record.losses) == (3, 2, 1)


def test_two_players_with_one_nickname_stay_apart() -> None:
    result = matchups.build(
        [
            played(1, 5, opponents=(ref("m:a", "Deleted User"),)),
            played(2, -5, opponents=(ref("m:b", "Deleted User"),)),
            played(3, -5, opponents=(ref("r:c", "Deleted User"),)),
        ]
    )
    assert [r.player_key for r in result.opponent_records] == ["m:a", "m:b", "r:c"]
    assert [r.wins for r in result.opponent_records] == [1, 0, 0]


def test_both_doubles_opponents_are_charged_the_match_and_its_margin() -> None:
    result = matchups.build(
        [played(1, -6, partners=(ref("m:p"),), opponents=(ref("m:x"), ref("r:y")))]
    )
    records = by_key(result.opponent_records)
    assert (records["m:x"].matches, records["m:x"].avg_margin) == (1, -6.0)
    assert (records["r:y"].matches, records["r:y"].avg_margin) == (1, -6.0)
    assert by_key(result.partner_records)["m:p"].losses == 1


def test_singles_has_no_partner() -> None:
    result = matchups.build(
        [
            played(1, 3, opponents=(ref("m:x"),)),
            played(2, 3, partners=(ref("m:p"),), opponents=(ref("m:x"), ref("m:y"))),
        ]
    )
    assert [r.player_key for r in result.partner_records] == ["m:p"]
    assert result.doubles_matches == 1
    assert (result.overall_win_rate, result.doubles_win_rate) == (1.0, 1.0)


def test_the_same_person_as_partner_and_as_opponent_is_two_separate_rows() -> None:
    result = matchups.build(
        [
            played(1, 3, partners=(ref("m:a"),), opponents=(ref("m:x"), ref("m:y"))),
            played(2, -3, partners=(ref("m:x"),), opponents=(ref("m:a"), ref("m:y"))),
        ]
    )
    assert by_key(result.partner_records)["m:a"].wins == 1
    assert by_key(result.opponent_records)["m:a"].losses == 1
    assert by_key(result.opponent_records)["m:a"].matches == 1


def test_average_margin_can_be_negative_and_keeps_one_decimal() -> None:
    result = matchups.build(
        [played(i, margin, opponents=(ref("m:x"),)) for i, margin in enumerate([-10, -3, 2])]
    )
    (record,) = result.opponent_records
    assert record.avg_margin == -3.7  # −11 / 3
    assert record.win_rate == round(1 / 3, 4)


def test_low_sample_is_under_three_matches() -> None:
    result = matchups.build(
        [played(i, 1, opponents=(ref("m:two"),)) for i in range(2)]
        + [played(i, 1, opponents=(ref("m:three"),)) for i in range(3)]
    )
    records = by_key(result.opponent_records)
    assert records["m:two"].low_sample is True
    assert records["m:three"].low_sample is False


def test_sorted_by_matches_then_by_key() -> None:
    result = matchups.build(
        [played(i, 1, opponents=(ref("m:few"),)) for i in range(2)]
        + [played(i, 1, opponents=(ref("m:b"),)) for i in range(4)]
        + [played(i, 1, opponents=(ref("m:a"),)) for i in range(4)]
    )
    assert [r.player_key for r in result.opponent_records] == ["m:a", "m:b", "m:few"]


def _partner(key: str, wins: int, losses: int) -> list[MatchupInput]:
    opponents = (ref("r:o1"), ref("r:o2"))
    return [played(i, 2, partners=(ref(key),), opponents=opponents) for i in range(wins)] + [
        played(50 + i, -2, partners=(ref(key),), opponents=opponents) for i in range(losses)
    ]


def test_highlights_need_enough_matches() -> None:
    # "often" is the most matches (needs 3); "best" is the top win rate among
    # those with at least 5.
    result = matchups.build(_partner("m:often", 3, 5) + _partner("m:lucky", 4, 0))
    assert result.highlights.most_played_partner == "m:often"
    assert result.highlights.best_partner == "m:often"  # m:lucky's 4 matches do not qualify

    result = matchups.build(_partner("m:often", 3, 5) + _partner("m:good", 5, 0))
    assert result.highlights.best_partner == "m:good"


def test_highlights_are_none_when_nobody_qualifies() -> None:
    result = matchups.build(_partner("m:a", 2, 0))
    assert result.highlights.most_played_partner is None
    assert result.highlights.best_partner is None


def test_highlight_ties_go_to_more_matches_then_to_the_smaller_key() -> None:
    result = matchups.build(_partner("m:b", 3, 3) + _partner("m:a", 4, 4))
    assert result.highlights.best_partner == "m:a"  # same 50%, more matches

    result = matchups.build(_partner("m:b", 3, 3) + _partner("m:a", 3, 3))
    assert result.highlights.best_partner == "m:a"  # same in everything: fixed order
    assert result.highlights.most_played_partner == "m:a"


def test_toughest_opponent_is_the_lowest_win_rate() -> None:
    inputs = [played(i, -2, opponents=(ref("m:wall"),)) for i in range(5)]
    inputs += [played(10 + i, 2, opponents=(ref("m:easy"),)) for i in range(7)]
    result = matchups.build(inputs)
    assert result.highlights.toughest_opponent == "m:wall"
    assert result.highlights.most_faced_opponent == "m:easy"


def test_win_rates_for_the_insight_baselines() -> None:
    inputs = _partner("m:p", 3, 1) + [played(90, -1, opponents=(ref("m:x"),)) for _ in range(4)]
    result = matchups.build(inputs)
    assert result.doubles_win_rate == 0.75
    assert result.overall_win_rate == round(3 / 8, 4)


def test_same_input_same_output() -> None:
    inputs = _partner("m:b", 3, 3) + _partner("m:a", 3, 3)
    assert matchups.build(inputs) == matchups.build(list(reversed(inputs)))
