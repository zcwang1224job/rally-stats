"""Unit test: player_identity — 036 data-model.md「身分鍵」. No database."""

import uuid

import pytest

from app.domains.member.player_identity import PlayerRef, parse_player_key, player_key

MEMBER = uuid.UUID("6b1f0c1e-0000-4000-8000-000000000001")
ENTRY = uuid.UUID("9a2e0c1e-0000-4000-8000-000000000002")


def test_a_member_is_keyed_by_member_id_whatever_the_roster_row() -> None:
    assert player_key(MEMBER, ENTRY) == f"m:{MEMBER}"
    assert player_key(MEMBER, uuid.uuid4()) == f"m:{MEMBER}"


def test_an_unbound_guest_is_keyed_by_roster_entry() -> None:
    assert player_key(None, ENTRY) == f"r:{ENTRY}"


@pytest.mark.parametrize("member_id", [MEMBER, None])
def test_round_trip(member_id: uuid.UUID | None) -> None:
    kind, value = parse_player_key(player_key(member_id, ENTRY))
    assert (kind, value) == (("m", MEMBER) if member_id else ("r", ENTRY))


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "m:",
        f"x:{MEMBER}",
        f"M:{MEMBER}",
        f" m:{MEMBER}",
        f"m:{MEMBER} ",
        f"m:{str(MEMBER).upper()}",
        f"m:{MEMBER.hex}",
        str(MEMBER),
        "m:not-a-uuid",
    ],
)
def test_malformed_keys_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_player_key(bad)


def test_player_ref_is_a_plain_value() -> None:
    ref = PlayerRef(key=f"m:{MEMBER}", nickname="阿哲", member_id=str(MEMBER))
    assert ref == PlayerRef(key=f"m:{MEMBER}", nickname="阿哲", member_id=str(MEMBER))
