"""Unit tests: open-form validation rules (spec FR-002, FR-003, FR-004, FR-037,
FR-014). These validate the Pydantic schema directly — no DB/HTTP involved."""

import pytest
from pydantic import ValidationError

from app.domains.group.schemas import CreateGroupRequest


def _base_payload(**overrides: object) -> dict:
    payload = {
        "name": "Test Group",
        "max_members": 8,
        "match_mode": "doubles",
        "scheduling_mechanism": "fair_rotation",
        "scoring_mode": "21pt",
        "creator_nickname": "Alice",
        "turnstile_token": "tok",
    }
    payload.update(overrides)
    return payload


def test_blank_or_omitted_name_normalizes_to_none() -> None:
    """021-group-creation-defaults (FR-001, research.md #1): reverses the
    prior behavior — a blank/whitespace-only/omitted `name` used to be
    rejected; it MUST now be accepted and normalized to `None`, letting
    `create_group()` substitute the default "{暱稱}的羽球團" (service-layer
    behavior covered by test_create_group_defaults.py, not here)."""
    assert CreateGroupRequest(**_base_payload(name="   ")).name is None
    assert CreateGroupRequest(**_base_payload(name="")).name is None
    payload = _base_payload()
    del payload["name"]
    assert CreateGroupRequest(**payload).name is None


def test_non_blank_name_is_trimmed_and_kept() -> None:
    assert CreateGroupRequest(**_base_payload(name="  Test Group  ")).name == "Test Group"


def test_name_over_30_chars_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(name="x" * 31))


def test_blank_creator_nickname_rejected() -> None:
    """Regression: unlike JoinGroupRequest.nickname, this field previously
    only checked length — a whitespace-only nickname passed validation and
    the service layer's `not payload.creator_nickname` check (a non-empty
    whitespace string is truthy), producing an invisible nickname stored
    verbatim. Now mirrors JoinGroupRequest.nickname_format: strip, then
    reject blank."""
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(creator_nickname="   "))


def test_creator_nickname_is_trimmed() -> None:
    request = CreateGroupRequest(**_base_payload(creator_nickname="  Alice  "))
    assert request.creator_nickname == "Alice"


def test_singles_min_members_enforced() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(match_mode="singles", max_members=1))
    CreateGroupRequest(**_base_payload(match_mode="singles", max_members=2))


def test_doubles_min_members_enforced() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(match_mode="doubles", max_members=3))
    CreateGroupRequest(**_base_payload(match_mode="doubles", max_members=4))


def test_password_length_1_to_20() -> None:
    CreateGroupRequest(**_base_payload(password="a"))
    CreateGroupRequest(**_base_payload(password="a" * 20))
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(password="a" * 21))


def test_activity_time_must_be_paired() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(activity_time_start="19:00"))


def test_activity_time_start_before_end() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(
            **_base_payload(activity_time_start="21:00", activity_time_end="19:00")
        )
    CreateGroupRequest(**_base_payload(activity_time_start="19:00", activity_time_end="21:00"))


def test_custom_scoring_requires_fields() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(scoring_mode="custom"))


def test_custom_scoring_cap_must_be_ge_target_and_threshold() -> None:
    # target=10, threshold=5, cap=8 -> illogical (cap < target), rejected per FR-014 clarification
    with pytest.raises(ValidationError):
        CreateGroupRequest(
            **_base_payload(
                scoring_mode="custom",
                custom_scoring={"target_score": 10, "deuce_threshold": 5, "cap_score": 8},
            )
        )


def test_custom_scoring_valid_combination_accepted() -> None:
    CreateGroupRequest(
        **_base_payload(
            scoring_mode="custom",
            custom_scoring={"target_score": 11, "deuce_threshold": 10, "cap_score": 15},
        )
    )
