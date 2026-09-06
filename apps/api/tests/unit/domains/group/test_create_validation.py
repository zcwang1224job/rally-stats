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


def test_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(name="   "))


def test_name_over_30_chars_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(**_base_payload(name="x" * 31))


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
