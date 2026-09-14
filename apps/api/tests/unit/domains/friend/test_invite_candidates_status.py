"""Unit tests for get_invite_candidates_status() — the batched
026-match-record-friend-invite lookup that lets a match-record/live-status
page render every "加好友" entry with one call (research.md #2)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import (
    create_friend_request_by_member_id,
    get_invite_candidates_status,
    respond_friend_request,
)
from app.domains.member.models import Member
from app.domains.member.service import delete_account, register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_none_status_is_eligible_by_default(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer1@example.com", "V")
    target = await _verified(db_session, "cand-target1@example.com", "T")

    response = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])

    (candidate,) = response.candidates
    assert candidate.member_id == str(target.id)
    assert candidate.friendship_status == "none"
    assert candidate.invite_eligible is True


async def test_friends_status_is_not_eligible(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer2@example.com", "V")
    target = await _verified(db_session, "cand-target2@example.com", "T")
    created = await create_friend_request_by_member_id(db_session, viewer.id, target.id)
    await respond_friend_request(
        db_session, target.id, uuid.UUID(created.friend_request_id), accept=True
    )

    response = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])

    (candidate,) = response.candidates
    assert candidate.friendship_status == "friends"
    assert candidate.invite_eligible is False


async def test_pending_outgoing_and_incoming_are_not_eligible(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer3@example.com", "V")
    target = await _verified(db_session, "cand-target3@example.com", "T")
    await create_friend_request_by_member_id(db_session, viewer.id, target.id)

    from_viewer = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])
    (viewer_candidate,) = from_viewer.candidates
    assert viewer_candidate.friendship_status == "pending_outgoing"
    assert viewer_candidate.invite_eligible is False

    from_target = await get_invite_candidates_status(db_session, target.id, [str(viewer.id)])
    (target_candidate,) = from_target.candidates
    assert target_candidate.friendship_status == "pending_incoming"
    assert target_candidate.invite_eligible is False


async def test_missing_member_id_omitted_not_errored(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer4@example.com", "V")

    response = await get_invite_candidates_status(db_session, viewer.id, [str(uuid.uuid4())])

    assert response.candidates == []


async def test_deleted_member_omitted(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer5@example.com", "V")
    target = await _verified(db_session, "cand-target5@example.com", "T")
    await delete_account(db_session, target, "abc12345")

    response = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])

    assert response.candidates == []


async def test_unverified_target_not_eligible(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer6@example.com", "V")
    unverified = await register(db_session, "cand-target6@example.com", "abc12345")

    response = await get_invite_candidates_status(db_session, viewer.id, [str(unverified.id)])

    (candidate,) = response.candidates
    assert candidate.friendship_status == "none"
    assert candidate.invite_eligible is False


async def test_toggle_off_not_eligible(db_session: AsyncSession) -> None:
    """026-match-record-friend-invite US3 (T042): invite_eligible is False
    when the target has turned off allow_friend_invite_from_match_pages."""
    viewer = await _verified(db_session, "cand-viewer8@example.com", "V")
    target = await _verified(db_session, "cand-target8@example.com", "T")
    target.allow_friend_invite_from_match_pages = False
    await db_session.commit()

    response = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])

    (candidate,) = response.candidates
    assert candidate.friendship_status == "none"
    assert candidate.invite_eligible is False


async def test_toggle_off_still_reports_existing_relationship_status(
    db_session: AsyncSession,
) -> None:
    """FR-009: the toggle only affects the `none` case's invite_eligible —
    an already-established relationship's friendship_status MUST still be
    reported correctly regardless of the toggle."""
    viewer = await _verified(db_session, "cand-viewer9@example.com", "V")
    target = await _verified(db_session, "cand-target9@example.com", "T")
    created = await create_friend_request_by_member_id(db_session, viewer.id, target.id)
    await respond_friend_request(
        db_session, target.id, uuid.UUID(created.friend_request_id), accept=True
    )
    target.allow_friend_invite_from_match_pages = False
    await db_session.commit()

    response = await get_invite_candidates_status(db_session, viewer.id, [str(target.id)])

    (candidate,) = response.candidates
    assert candidate.friendship_status == "friends"
    assert candidate.invite_eligible is False


async def test_batch_returns_multiple_candidates(db_session: AsyncSession) -> None:
    viewer = await _verified(db_session, "cand-viewer7@example.com", "V")
    t1 = await _verified(db_session, "cand-target7a@example.com", "T1")
    t2 = await _verified(db_session, "cand-target7b@example.com", "T2")

    response = await get_invite_candidates_status(
        db_session, viewer.id, [str(t1.id), str(t2.id)]
    )

    assert {c.member_id for c in response.candidates} == {str(t1.id), str(t2.id)}
