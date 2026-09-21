"""Unit tests for 022-member-personal-settings: language preference,
login records (classify_device/record_login/list_login_records), privacy
settings, search_member's allow_search gate, and the friend-viewing
authorization layer (view_member_match_records/view_member_match_record_detail)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.models import FriendRequest
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import Member, MemberLoginRecord
from app.domains.member.service import (
    classify_device,
    list_login_records,
    record_login,
    register,
    search_member,
    set_language_preference,
    update_privacy_settings,
    view_member_match_record_detail,
    view_member_match_records,
)
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _make_verified_member(session: AsyncSession, email: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    await session.commit()
    await session.refresh(member)
    return member


async def _make_friendship(session: AsyncSession, member_a: Member, member_b: Member) -> None:
    session.add(
        FriendRequest(requester_id=member_a.id, addressee_id=member_b.id, status="accepted")
    )
    await session.commit()


async def _make_group_with_match(
    session: AsyncSession, member: Member
) -> None:
    group = Group(
        name="好友戰績測試團",
        max_members=8,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)

    my_entry = RosterEntry(group_id=group.id, nickname="小明", member_id=member.id, status="active")
    opp_entry = RosterEntry(group_id=group.id, nickname="對手", member_id=None, status="active")
    session.add_all([my_entry, opp_entry])
    await session.commit()
    await session.refresh(my_entry)
    await session.refresh(opp_entry)

    now = datetime.now(UTC)
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=1,
        status="completed",
        winner_team="A",
        score_a=11,
        score_b=5,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
        started_at=now,
        ended_at=now,
    )
    session.add(match)
    await session.flush()
    session.add(MatchParticipant(match_id=match.id, roster_entry_id=my_entry.id, team="A"))
    session.add(MatchParticipant(match_id=match.id, roster_entry_id=opp_entry.id, team="B"))
    await session.commit()


# --- classify_device (US2, research.md #3) ---------------------------------


async def test_classify_device_detects_mobile_keywords() -> None:
    assert classify_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)") == "mobile"
    assert classify_device("Mozilla/5.0 (Linux; Android 14)") == "mobile"
    assert classify_device("Mozilla/5.0 (iPad; CPU OS 17_0)") == "mobile"


async def test_classify_device_detects_desktop() -> None:
    assert classify_device("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120") == "desktop"


async def test_classify_device_unknown_for_missing_user_agent() -> None:
    assert classify_device(None) == "unknown"
    assert classify_device("") == "unknown"


# --- record_login / list_login_records (US2) --------------------------------


async def test_record_login_creates_a_row(db_session: AsyncSession) -> None:
    member = await _make_verified_member(db_session, "loginrec1@example.com")

    await record_login(db_session, member.id, "desktop")

    result = await db_session.execute(
        select(MemberLoginRecord).where(MemberLoginRecord.member_id == member.id)
    )
    rows = list(result.scalars())
    assert len(rows) == 1
    assert rows[0].device_category == "desktop"


async def test_record_login_trims_to_retention_limit(db_session: AsyncSession) -> None:
    member = await _make_verified_member(db_session, "loginrec2@example.com")

    for _ in range(55):
        await record_login(db_session, member.id, "desktop")

    result = await db_session.execute(
        select(MemberLoginRecord).where(MemberLoginRecord.member_id == member.id)
    )
    assert len(list(result.scalars())) == 50


async def test_login_does_not_add_a_record_via_token_refresh(db_session: AsyncSession) -> None:
    """FR-007/Clarifications 2026-09-13 #4: only `login()` calls
    `record_login()` — `refresh_access_token()` MUST NOT."""
    from app.domains.member.security import (
        issue_refresh_token,
        refresh_access_token,
    )

    member = await _make_verified_member(db_session, "loginrec3@example.com")
    await record_login(db_session, member.id, "desktop")

    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    await refresh_access_token(db_session, refresh_token)

    result = await db_session.execute(
        select(MemberLoginRecord).where(MemberLoginRecord.member_id == member.id)
    )
    assert len(list(result.scalars())) == 1


async def test_list_login_records_sorted_newest_first_and_paginated(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "loginrec4@example.com")
    await record_login(db_session, member.id, "desktop")
    await record_login(db_session, member.id, "mobile")

    response = await list_login_records(db_session, member.id, 1)

    assert response.page == 1
    assert len(response.records) == 2
    assert response.records[0].created_at >= response.records[1].created_at
    assert response.records[0].device_category == "mobile"


# --- set_language_preference (US1) ------------------------------------------


async def test_set_language_preference_accepts_supported_language(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "lang1@example.com")

    updated = await set_language_preference(db_session, member, "zh-TW")

    assert updated.language_preference == "zh-TW"


async def test_set_language_preference_rejects_unsupported_language(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "lang2@example.com")

    with pytest.raises(ApiError) as exc_info:
        await set_language_preference(db_session, member, "en-US")
    assert exc_info.value.error_code == "LANGUAGE_NOT_SUPPORTED"


# --- update_privacy_settings (US4) ------------------------------------------


async def test_update_privacy_settings_updates_only_provided_field(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "priv1@example.com")
    assert member.allow_search is True
    assert member.share_match_records_with_friends is True

    updated = await update_privacy_settings(
        db_session, member, allow_search=False, share_match_records_with_friends=None
    )

    assert updated.allow_search is False
    assert updated.share_match_records_with_friends is True


async def test_update_privacy_settings_allow_friend_invite_from_match_pages_independent(
    db_session: AsyncSession,
) -> None:
    """026-match-record-friend-invite FR-006/007: the new field defaults to
    True and can be changed independently of the other two — updating it
    alone MUST NOT touch allow_search/share_match_records_with_friends, and
    vice versa (T039)."""
    member = await _make_verified_member(db_session, "priv2@example.com")
    assert member.allow_friend_invite_from_match_pages is True

    updated = await update_privacy_settings(
        db_session,
        member,
        allow_search=None,
        share_match_records_with_friends=None,
        allow_friend_invite_from_match_pages=False,
    )

    assert updated.allow_friend_invite_from_match_pages is False
    assert updated.allow_search is True
    assert updated.share_match_records_with_friends is True

    updated_again = await update_privacy_settings(
        db_session,
        updated,
        allow_search=False,
        share_match_records_with_friends=None,
    )

    assert updated_again.allow_search is False
    # Omitted from this second call — MUST stay at whatever the first call left it.
    assert updated_again.allow_friend_invite_from_match_pages is False


# --- search_member allow_search gate (US4, FR-017) --------------------------


async def test_search_member_hides_member_who_disabled_allow_search(
    db_session: AsyncSession,
) -> None:
    searcher = await _make_verified_member(db_session, "searcher1@example.com")
    target = await _make_verified_member(db_session, "target1@example.com")
    target.allow_search = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await search_member(db_session, target.user_number, searcher.id)
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_search_member_self_search_unaffected_by_own_allow_search(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "searcher2@example.com")
    member.allow_search = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await search_member(db_session, member.user_number, member.id)
    assert exc_info.value.error_code == "CANNOT_SEARCH_SELF"


# --- view_member_match_records / detail authorization matrix (US4) ----------


async def test_view_member_match_records_rejects_self_view_before_friendship_check(
    db_session: AsyncSession,
) -> None:
    member = await _make_verified_member(db_session, "self1@example.com")

    with pytest.raises(ApiError) as exc_info:
        await view_member_match_records(db_session, member.id, member.id)
    assert exc_info.value.error_code == "SELF_VIEW_NOT_SUPPORTED"


async def test_view_member_match_records_target_not_found(db_session: AsyncSession) -> None:
    viewer = await _make_verified_member(db_session, "viewer1@example.com")

    with pytest.raises(ApiError) as exc_info:
        await view_member_match_records(db_session, viewer.id, uuid.uuid4())
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_view_member_match_records_rejects_non_friend_regardless_of_privacy(
    db_session: AsyncSession,
) -> None:
    viewer = await _make_verified_member(db_session, "viewer2@example.com")
    target = await _make_verified_member(db_session, "target2@example.com")
    assert target.share_match_records_with_friends is True

    with pytest.raises(ApiError) as exc_info:
        await view_member_match_records(db_session, viewer.id, target.id)
    assert exc_info.value.error_code == "FRIENDSHIP_REQUIRED"


async def test_view_member_match_records_rejects_friend_when_privacy_disabled(
    db_session: AsyncSession,
) -> None:
    viewer = await _make_verified_member(db_session, "viewer3@example.com")
    target = await _make_verified_member(db_session, "target3@example.com")
    await _make_friendship(db_session, viewer, target)
    target.share_match_records_with_friends = False
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await view_member_match_records(db_session, viewer.id, target.id)
    assert exc_info.value.error_code == "MATCH_RECORDS_PRIVATE"


async def test_view_member_match_records_delegates_when_friend_and_enabled(
    db_session: AsyncSession,
) -> None:
    """FR-018: response MUST include both per-match detail (`matches`) and
    aggregate stats (`total_matches`/`win_rate`/...), the same shape as the
    self-viewing `/members/me/match-records` endpoint (research.md #1)."""
    viewer = await _make_verified_member(db_session, "viewer4@example.com")
    target = await _make_verified_member(db_session, "target4@example.com")
    await _make_friendship(db_session, viewer, target)
    await _make_group_with_match(db_session, target)

    response = await view_member_match_records(db_session, viewer.id, target.id)

    assert response.total_matches == 1
    assert len(response.matches) == 1


async def test_view_member_match_record_detail_delegates_when_friend_and_enabled(
    db_session: AsyncSession,
) -> None:
    viewer = await _make_verified_member(db_session, "viewer5@example.com")
    target = await _make_verified_member(db_session, "target5@example.com")
    await _make_friendship(db_session, viewer, target)
    await _make_group_with_match(db_session, target)

    listed = await view_member_match_records(db_session, viewer.id, target.id)
    match_id = uuid.UUID(listed.matches[0].match_id)

    detail = await view_member_match_record_detail(db_session, viewer.id, target.id, match_id)

    assert detail.match_id == str(match_id)
    # 040-match-share-card FR-012a: the friend's detail carries the
    # match's own points-to-win too (the helper's match is 21-point).
    assert detail.target_score == 21
