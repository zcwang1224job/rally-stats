"""Group domain service layer: create, disband, reauth, edit, PIN regeneration,
and (004) the browse/join flow.

`disband_group` accepts an `abandon_unfinished_matches` hook, wired in by
003's `abandon_group_matches` at the router layer (research.md #2 of 003),
transitioning unfinished matches to `abandoned` on disband (spec FR-033).
"""

import secrets
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from typing import Literal

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.realtime import court_channel, group_notifications_channel, publish
from app.domains.court.models import Court
from app.domains.group.models import Group, RoundHistory
from app.domains.group.schemas import (
    CreateGroupRequest,
    EditGroupRequest,
    EditScoringSettingsRequest,
    GroupMatchRecordsResponse,
    GroupStandingsResponse,
    MatchRecordDetailResponse,
    MatchRecordSummary,
    MemberStandingRow,
    RoundRecord,
    ScoreEventSummary,
)
from app.domains.group.security import (
    decrypt_group_password,
    encrypt_group_password,
    generate_admin_pin,
    hash_admin_pin,
    issue_admin_token,
    verify_admin_pin,
)
from app.domains.member.models import Member
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent
from app.domains.schedule.schemas import ParticipantSummary
from app.domains.schedule.service import handle_member_joined, handle_member_left
from app.system_config.service import get_max_group_members

AbandonMatchesHook = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]
# 013-group-invite-friends research.md #2: same optional-hook pattern as
# AbandonMatchesHook above, wired in by group_invite/router.py's disband
# endpoint (and the auto-disband sweep) so group.service never has to
# import group_invite.service directly.
InvalidatePendingInvitesHook = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]

_MATCH_RECORDS_PAGE_SIZE = 20

_SCORING_PRESETS = {
    "21pt": (21, 20, 30),
    "15pt": (15, 14, 21),
}

_DEFAULT_GROUP_NAME_SUFFIX = "的羽球團"
# 021-group-creation-defaults FR-001: a blank/omitted group name defaults
# to f"{建立者暱稱}{_DEFAULT_GROUP_NAME_SUFFIX}" (research.md #1).
_DEFAULT_COURT_NAME = "球場一"
# 021-group-creation-defaults FR-006: every group gets exactly one active
# court with this name, auto-created in the same transaction as the group
# itself (research.md #2).


async def _touch_activity(session: AsyncSession, group: Group) -> None:
    group.last_activity_at = datetime.now(UTC)


async def get_active_group_id_for_member(
    session: AsyncSession, member_id: uuid.UUID
) -> uuid.UUID | None:
    """The one Group a Member currently has an active RosterEntry in, if
    any — the read-side counterpart of `_raise_if_active_elsewhere`'s
    write-time guard, reused by the browse list (US: proactively disabling
    "加入" for every OTHER group there instead of only failing after the
    Member picks one and confirms).

    MUST join Group and filter out `status == "disbanded"` — disbanding a
    group deliberately does NOT touch its members' RosterEntry.status
    (`disband_group()`; a disbanded group stays readable/leavable, per
    005-member-view's edge cases and
    test_already_active_member_short_circuits_even_on_disbanded_group), so
    without this filter, a Member who was ever in a group that later got
    disbanded would look permanently "still active" there and be locked
    out of ever creating or joining another group again. `.limit(1)`
    defensively caps it at one row: this rule is only enforced going
    forward, so a Member with more than one genuinely-active RosterEntry
    from before it existed is possible, and `scalar_one_or_none()` would
    otherwise raise on that instead of just picking one to report."""
    result = await session.execute(
        select(RosterEntry.group_id)
        .join(Group, Group.id == RosterEntry.group_id)
        .where(
            RosterEntry.member_id == member_id,
            RosterEntry.status == "active",
            Group.status != "disbanded",
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _raise_if_active_elsewhere(
    session: AsyncSession, member_id: uuid.UUID, *, exclude_group_id: uuid.UUID | None = None
) -> None:
    """One active group per Member, at a time — deliberately Member-only:
    a Guest's identity (`guest_session_token`) is already scoped to a single
    group by design (FR-022, `RosterEntry.member_id` null) and has no
    cross-group identity to check against, so this can't be enforced for
    Guests at all. `exclude_group_id` only matters for `join_group`'s
    FR-020a same-group idempotency case, where the caller already knows
    about (and allows) their own existing entry in THIS group —
    `create_group` never has one yet, so it never passes this.

    `FOR UPDATE` on this Member's own row closes the TOCTOU window between
    this check and the caller's later INSERT+commit: without it, two
    near-simultaneous requests (a double-click, two tabs) could both read
    "not active anywhere" before either commits, and both go on to
    succeed. Same pessimistic-lock technique as schedule/service.py's
    `_lock_group_for_round_generation` — but deliberately no `nowait`
    here: blocking is the desired outcome (the second request should wait
    and then correctly see the first's committed row), not something to
    reject outright. Locks only this one Member's row, so unrelated
    Members' requests never contend."""
    await session.execute(select(Member.id).where(Member.id == member_id).with_for_update())
    active_group_id = await get_active_group_id_for_member(session, member_id)
    if active_group_id is not None and active_group_id != exclude_group_id:
        raise ApiError("ALREADY_ACTIVE_IN_ANOTHER_GROUP", status_code=409)


async def create_group(
    session: AsyncSession,
    payload: CreateGroupRequest,
    *,
    member: Member | None,
) -> tuple[Group, RosterEntry, str, str | None]:
    """Create a Group + the creator's RosterEntry + a default Court in one
    transaction (spec FR-001-012; 021-group-creation-defaults FR-001,
    FR-006, FR-007, research.md #1/#2)."""
    if member is not None:
        await _raise_if_active_elsewhere(session, member.id)

    max_allowed = await get_max_group_members(session)
    if payload.max_members > max_allowed:
        raise ApiError(
            "GROUP_MEMBER_CAP_EXCEEDED", status_code=400, detail={"max_allowed": max_allowed}
        )

    if member is not None and not member.nickname:
        raise ApiError("MEMBER_NICKNAME_NOT_SET", status_code=400)
    stripped_creator_nickname = (payload.creator_nickname or "").strip()
    if member is None and not stripped_creator_nickname:
        raise ApiError("NICKNAME_REQUIRED_FOR_GUEST", status_code=400)

    # 021-group-creation-defaults research.md #1: resolved once, here, so
    # both the default group name (below) and the RosterEntry (further
    # down) use the exact same value — moved up from where it used to be
    # computed (immediately before building RosterEntry).
    nickname = member.nickname if member else stripped_creator_nickname
    assert nickname is not None
    resolved_name = payload.name or f"{nickname}{_DEFAULT_GROUP_NAME_SUFFIX}"

    if payload.scoring_mode == "custom":
        assert payload.custom_scoring is not None
        target_score = payload.custom_scoring.target_score
        deuce_threshold = payload.custom_scoring.deuce_threshold
        cap_score = payload.custom_scoring.cap_score
    else:
        target_score, deuce_threshold, cap_score = _SCORING_PRESETS[payload.scoring_mode]

    password_ciphertext: bytes | None = None
    password_nonce: bytes | None = None
    if payload.password:
        password_ciphertext, password_nonce = encrypt_group_password(payload.password)

    admin_pin = generate_admin_pin()
    group = Group(
        name=resolved_name,
        password_ciphertext=password_ciphertext,
        password_nonce=password_nonce,
        max_members=payload.max_members,
        match_mode=payload.match_mode,
        scheduling_mechanism=payload.scheduling_mechanism,
        activity_time_start=payload.activity_time_start,
        activity_time_end=payload.activity_time_end,
        current_member_count=1,
        status="active",
        created_by_member_id=member.id if member else None,
        admin_pin_hash=hash_admin_pin(admin_pin),
        scoring_mode=payload.scoring_mode,
        target_score=target_score,
        deuce_threshold=deuce_threshold,
        cap_score=cap_score,
    )
    session.add(group)
    await session.flush()  # populate group.id via default

    guest_token = secrets.token_urlsafe(32) if member is None else None

    roster_entry = RosterEntry(
        group_id=group.id,
        member_id=member.id if member else None,
        nickname=nickname,
        status="active",
        is_creator=True,
        wait_count=None,
        guest_session_token=guest_token,
    )
    session.add(roster_entry)

    # 021-group-creation-defaults research.md #2: inserted directly (not
    # via create_court(), which owns its own commit + IntegrityError
    # handling for user-supplied names) so it shares this exact same
    # transaction — a failure anywhere above means neither the Group nor
    # this Court is persisted (FR-007). No name-collision handling is
    # needed: this is necessarily the group's first-ever court.
    default_court = Court(group_id=group.id, name=_DEFAULT_COURT_NAME)
    session.add(default_court)

    await session.commit()
    await session.refresh(group)
    await session.refresh(roster_entry)
    await session.refresh(default_court)

    # Same event shape create_court() publishes — lets any hypothetical
    # already-open all-courts screen pick it up the same way a manually
    # added court would (constitution III/VI).
    await publish(
        group_notifications_channel(str(group.id)),
        "court.added",
        {"court_id": str(default_court.id), "name": default_court.name},
    )

    return group, roster_entry, admin_pin, guest_token


async def get_group_by_id(session: AsyncSession, group_id: uuid.UUID) -> Group:
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise ApiError("GROUP_NOT_FOUND", status_code=404)
    return group


async def reauth_admin(
    session: AsyncSession, group_number: int, admin_pin: str
) -> tuple[str, Group]:
    settings = get_settings()
    result = await session.execute(select(Group).where(Group.group_number == group_number))
    group = result.scalar_one_or_none()
    if group is None:
        # Same error as "PIN incorrect" to avoid enumerating valid group numbers.
        raise ApiError("GROUP_ADMIN_PIN_INCORRECT", status_code=401)

    now = datetime.now(UTC)
    if group.admin_locked_until is not None and group.admin_locked_until > now:
        retry_after = int((group.admin_locked_until - now).total_seconds())
        raise ApiError(
            "GROUP_ADMIN_LOCKED", status_code=423, detail={"retry_after_seconds": retry_after}
        )

    if not verify_admin_pin(admin_pin, group.admin_pin_hash):
        group.admin_failed_attempts += 1
        if group.admin_failed_attempts >= settings.admin_pin_max_attempts:
            group.admin_locked_until = now + timedelta(minutes=settings.admin_pin_lockout_minutes)
        await session.commit()
        raise ApiError("GROUP_ADMIN_PIN_INCORRECT", status_code=401)

    group.admin_failed_attempts = 0
    group.admin_locked_until = None
    await _touch_activity(session, group)
    await session.commit()

    token = issue_admin_token(str(group.id), group.admin_token_version)
    return token, group


async def edit_group(
    session: AsyncSession, group: Group, payload: EditGroupRequest
) -> Group:
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)
    if payload.expected_version != group.base_settings_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    if payload.match_mode is not None and payload.match_mode != group.match_mode:
        effective_max = (
            payload.max_members if payload.max_members is not None else group.max_members
        )
        if payload.match_mode == "doubles" and effective_max < 4:
            raise ApiError("MATCH_MODE_MEMBER_CAP_CONFLICT", status_code=400)
        group.match_mode = payload.match_mode
        # The new minimum (2 for singles / 4 for doubles) is enforced by the
        # max_members validation block below, which reads the now-updated
        # group.match_mode.

    if payload.max_members is not None:
        max_allowed = await get_max_group_members(session)
        if payload.max_members > max_allowed:
            raise ApiError(
                "GROUP_MEMBER_CAP_EXCEEDED", status_code=400, detail={"max_allowed": max_allowed}
            )
        minimum = 2 if group.match_mode == "singles" else 4
        if payload.max_members < minimum:
            raise ApiError("VALIDATION_ERROR", status_code=422)
        group.max_members = payload.max_members

    if payload.name is not None:
        group.name = payload.name
    if payload.password is not None:
        ciphertext, nonce = encrypt_group_password(payload.password)
        group.password_ciphertext = ciphertext
        group.password_nonce = nonce
    if payload.activity_time_start is not None or payload.activity_time_end is not None:
        if (payload.activity_time_start is None) != (payload.activity_time_end is None):
            raise ApiError("VALIDATION_ERROR", status_code=422)
        if payload.activity_time_start >= payload.activity_time_end:  # type: ignore[operator]
            raise ApiError("VALIDATION_ERROR", status_code=422)
        group.activity_time_start = payload.activity_time_start
        group.activity_time_end = payload.activity_time_end
    if payload.scheduling_mechanism is not None:
        group.scheduling_mechanism = payload.scheduling_mechanism
        # spec 003 FR-016: manual scheduling MUST NOT support Auto Next
        # Round — switching into it force-disables an already-on toggle.
        if group.scheduling_mechanism == "manual":
            group.auto_next_round = False

    # 011-round-robin-scheduling FR-008/FR-010: partner_source only means
    # anything for fixed_partner — silently ignored otherwise (contracts
    # amendments), not a validation error. Toggling it never touches the
    # `partnerships` table itself (research.md #6); that table's data is
    # simply not read while `partner_source == "auto"`.
    if payload.partner_source is not None and group.scheduling_mechanism == "fixed_partner":
        group.partner_source = payload.partner_source

    # spec 003 FR-042: fixed_partner/individual_mixed only apply to doubles —
    # checked against the FINAL state (after any match_mode/scheduling_mechanism
    # change above), regardless of which field the caller actually changed.
    if group.scheduling_mechanism in ("fixed_partner", "individual_mixed") and (
        group.match_mode == "singles"
    ):
        raise ApiError("SCHEDULING_MECHANISM_MATCH_MODE_CONFLICT", status_code=400)

    group.base_settings_version += 1
    await _touch_activity(session, group)
    await session.commit()
    await session.refresh(group)
    return group


async def edit_scoring_settings(
    session: AsyncSession, group: Group, payload: EditScoringSettingsRequest
) -> Group:
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)
    if payload.expected_version != group.base_settings_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    if payload.scoring_mode == "custom":
        if payload.target_score is None or payload.target_score < 1:
            raise ApiError("INVALID_CUSTOM_SCORING", status_code=422)
        if payload.deuce_threshold is None or not (
            1 <= payload.deuce_threshold <= payload.target_score
        ):
            raise ApiError("INVALID_CUSTOM_SCORING", status_code=422)
        if payload.cap_score is None or payload.cap_score < payload.deuce_threshold:
            raise ApiError("INVALID_CUSTOM_SCORING", status_code=422)
        if payload.cap_score < payload.target_score:
            raise ApiError("INVALID_CUSTOM_SCORING", status_code=422)
        group.target_score = payload.target_score
        group.deuce_threshold = payload.deuce_threshold
        group.cap_score = payload.cap_score
    else:
        target_score, deuce_threshold, cap_score = _SCORING_PRESETS[payload.scoring_mode]
        group.target_score = target_score
        group.deuce_threshold = deuce_threshold
        group.cap_score = cap_score

    group.scoring_mode = payload.scoring_mode
    group.base_settings_version += 1
    await _touch_activity(session, group)
    await session.commit()
    await session.refresh(group)
    return group


async def disband_group(
    session: AsyncSession,
    group: Group,
    *,
    abandon_unfinished_matches: AbandonMatchesHook | None = None,
    invalidate_pending_invites: InvalidatePendingInvitesHook | None = None,
) -> Group:
    """Disband (manual or auto-triggered). Idempotent: re-disbanding an already
    disbanded group is a no-op rather than an error, since the auto-disband
    scheduler and manual disband may race harmlessly."""
    if group.status == "disbanded":
        return group

    group.status = "disbanded"
    group.disbanded_at = datetime.now(UTC)
    await _touch_activity(session, group)

    if abandon_unfinished_matches is not None:
        await abandon_unfinished_matches(session, group.id)
    if invalidate_pending_invites is not None:
        await invalidate_pending_invites(session, group.id)

    await session.commit()
    await session.refresh(group)

    # Broadcast group.disbanded: per-court channels + the group notifications channel
    # (contracts/ably-events.md — MUST NOT rely on a single wildcard channel).
    result = await session.execute(
        select(Court.id).where(Court.group_id == group.id, Court.deleted_at.is_(None))
    )
    disbanded_payload = {"event": "group.disbanded"}
    for (court_id,) in result.all():
        channel = court_channel(str(group.id), str(court_id))
        await publish(channel, "group.disbanded", disbanded_payload)
    await publish(
        group_notifications_channel(str(group.id)), "group.disbanded", disbanded_payload
    )

    return group


async def regenerate_admin_pin(session: AsyncSession, group: Group) -> tuple[str, str]:
    """Optimistic-lock on admin_token_version itself: re-read immediately before
    writing inside the same transaction context (the row was already loaded by
    require_admin in this request, so a concurrent regenerate that already
    committed would have changed admin_token_version — we detect that here)."""
    result = await session.execute(select(Group.admin_token_version).where(Group.id == group.id))
    current_version = result.scalar_one()
    if current_version != group.admin_token_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    new_pin = generate_admin_pin()
    group.admin_pin_hash = hash_admin_pin(new_pin)
    group.admin_token_version += 1
    group.admin_failed_attempts = 0
    group.admin_locked_until = None
    await _touch_activity(session, group)
    await session.commit()
    await session.refresh(group)

    new_token = issue_admin_token(str(group.id), group.admin_token_version)

    await publish(
        group_notifications_channel(str(group.id)),
        "link.regenerated",
        {"event": "link.regenerated", "group_id": str(group.id), "link_type": "admin"},
    )

    return new_pin, new_token


async def forgot_admin_pin(
    session: AsyncSession, group_id: uuid.UUID, member_id: uuid.UUID
) -> tuple[str, str]:
    """006-member-friends US4 (FR-028~032): member-only recovery path — no
    original PIN or password required, unlike `regenerate_admin_pin` (which
    needs an already-valid admin session). Reuses that function's exact
    core logic once the caller is confirmed to be this group's creator, so
    the two paths stay behaviorally identical (same version bump, same
    `link.regenerated` broadcast). Works on a disbanded group too — no
    `Group.status` check here, matching `resolve_active_roster_membership`'s
    established precedent of member-view/recovery endpoints staying
    readable after disband. Errors: `GROUP_NOT_FOUND`, `NOT_GROUP_CREATOR`."""
    group = await get_group_by_id(session, group_id)
    if group.created_by_member_id != member_id:
        raise ApiError("NOT_GROUP_CREATOR", status_code=403)
    return await regenerate_admin_pin(session, group)


async def get_group_if_creator(
    session: AsyncSession, group_id: uuid.UUID, member_id: uuid.UUID
) -> Group:
    """011-round-robin-scheduling follow-up: backs the "回到我的團" button's
    creator short-circuit — a logged-in member who created this group can
    jump straight back to the admin page without the PIN, but (unlike
    `forgot_admin_pin` above) MUST NOT reset the PIN or bump
    `admin_token_version` in the process; this is a read-only ownership
    check, the token itself gets (re)issued by the caller against the
    group's *current* version so existing admin sessions elsewhere stay
    valid. Same disbanded-group-readable precedent as `forgot_admin_pin`.
    Errors: `GROUP_NOT_FOUND`, `NOT_GROUP_CREATOR`."""
    group = await get_group_by_id(session, group_id)
    if group.created_by_member_id != member_id:
        raise ApiError("NOT_GROUP_CREATOR", status_code=403)
    return group


def get_group_password_plaintext(group: Group) -> str | None:
    if group.password_ciphertext is None or group.password_nonce is None:
        return None
    return decrypt_group_password(group.password_ciphertext, group.password_nonce)


async def get_group_by_all_courts_token(
    session: AsyncSession, token: uuid.UUID
) -> tuple[Group, list[Court]]:
    """Public bootstrap + heartbeat for the all-courts control panel
    (specs/002-court-management/contracts/courts-api.md). Deliberately does
    NOT return each court's own scoreboard/control_panel token — the
    all-courts panel operates by court_id, and callers holding only this
    all-courts token must not be able to discover other courts' individual
    link credentials (constitution IV)."""
    result = await session.execute(
        select(Group).where(Group.all_courts_control_panel_token == token)
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise ApiError("LINK_NOT_FOUND", status_code=404)

    courts_result = await session.execute(
        select(Court)
        .where(Court.group_id == group.id, Court.deleted_at.is_(None))
        .order_by(Court.created_at)
    )
    return group, list(courts_result.scalars().all())


async def regenerate_join_link(
    session: AsyncSession, group: Group, expected_version: int
) -> Group:
    """Per FR-033, the join link is validated by the backend at the moment a
    join request is submitted (004 spec) rather than via a live subscription
    — this MUST NOT publish any realtime event, unlike every other link type
    in this domain."""
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)
    if expected_version != group.join_link_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    group.join_link_token = uuid.uuid4()
    group.join_link_version += 1
    await session.commit()
    await session.refresh(group)
    return group


async def regenerate_all_courts_link(
    session: AsyncSession, group: Group, expected_version: int
) -> Group:
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)
    if expected_version != group.all_courts_link_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    group.all_courts_control_panel_token = uuid.uuid4()
    group.all_courts_link_version += 1
    await session.commit()
    await session.refresh(group)

    await publish(
        group_notifications_channel(str(group.id)),
        "link.regenerated",
        {"event": "link.regenerated", "group_id": str(group.id), "link_type": "all_courts"},
    )
    return group


_GROUP_LIST_PAGE_SIZE = 20


async def court_names_for_group(session: AsyncSession, group_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(Court.name)
        .where(Court.group_id == group_id, Court.deleted_at.is_(None))
        .order_by(Court.created_at)
    )
    return [row[0] for row in result.all()]


async def creator_nickname_for_group(session: AsyncSession, group_id: uuid.UUID) -> str:
    """FR-002: 開團者暱稱 — the creator's `RosterEntry` always exists (created
    in the same transaction as the group itself, per `create_group`)."""
    result = await session.execute(
        select(RosterEntry.nickname).where(
            RosterEntry.group_id == group_id, RosterEntry.is_creator.is_(True)
        )
    )
    return result.scalar_one()


async def list_groups(
    session: AsyncSession,
    *,
    page: int = 1,
    court_name: str | None = None,
    time_start: time | None = None,
    time_end: time | None = None,
    group_name: str | None = None,
    creator_nickname: str | None = None,
    match_mode: str | None = None,
) -> tuple[list[Group], int]:
    """Browse query (US1 base, extended by US5's filters); `joined_by_me`
    personalization (US6) is layered on top of this function's result set
    by the router, not here.

    research.md #7: the court name filter matches if ANY of the group's
    (non-deleted) courts hits — a group can have multiple courts. Time
    filters use overlap semantics (spec.md Assumptions) and MUST exclude
    groups with no activity time set when applied (FR-004), but MUST NOT
    exclude them when no time filter is given at all.

    group_name/creator_nickname are substring, case-insensitive matches
    (same convention as court_name); match_mode is an exact match (it's a
    closed enum, not free text). creator_nickname matches against the
    group's creator RosterEntry specifically (`is_creator`), not any
    member's nickname — same scope as `creator_nickname_for_group()`.
    """
    conditions = [Group.status == "active"]
    if court_name is not None:
        conditions.append(
            select(Court.id)
            .where(
                Court.group_id == Group.id,
                Court.deleted_at.is_(None),
                Court.name.ilike(f"%{court_name}%"),
            )
            .exists()
        )
    if time_start is not None and time_end is not None:
        conditions.extend(
            [
                Group.activity_time_start.is_not(None),
                Group.activity_time_end.is_not(None),
                Group.activity_time_start < time_end,
                Group.activity_time_end > time_start,
            ]
        )
    if group_name is not None:
        conditions.append(Group.name.ilike(f"%{group_name}%"))
    if creator_nickname is not None:
        conditions.append(
            select(RosterEntry.id)
            .where(
                RosterEntry.group_id == Group.id,
                RosterEntry.is_creator.is_(True),
                RosterEntry.nickname.ilike(f"%{creator_nickname}%"),
            )
            .exists()
        )
    if match_mode is not None:
        conditions.append(Group.match_mode == match_mode)

    count_result = await session.execute(
        select(func.count()).select_from(Group).where(*conditions)
    )
    total = count_result.scalar_one()
    total_pages = max(1, (total + _GROUP_LIST_PAGE_SIZE - 1) // _GROUP_LIST_PAGE_SIZE)

    result = await session.execute(
        select(Group)
        .where(*conditions)
        .order_by(Group.created_at.desc())
        .limit(_GROUP_LIST_PAGE_SIZE)
        .offset((page - 1) * _GROUP_LIST_PAGE_SIZE)
    )
    return list(result.scalars().all()), total_pages


def verify_password(group: Group, password: str) -> bool:
    """No lockout mechanism (FR-016) — pure comparison, no attempt counter."""
    if group.password_ciphertext is None or group.password_nonce is None:
        return True
    return decrypt_group_password(group.password_ciphertext, group.password_nonce) == password


async def join_group(
    session: AsyncSession,
    group: Group,
    *,
    member: Member | None,
    password: str | None,
    nickname: str | None,
    skip_password: bool = False,
) -> tuple[RosterEntry, bool]:
    """FR-011~027: the core join write path, shared by every join entry
    point (list, join-link, guest reconnect is separate). Returns
    `(roster_entry, created_new)` — `created_new=False` signals the FR-020a
    short-circuit (an already-active member, no new row written).

    The FR-020a short-circuit MUST run before the disbanded check: 005's
    member view (research.md #5) relies on being able to idempotently
    re-resolve an already-active member's `roster_entry_id` via this
    function on a disbanded group (e.g. to leave it), and that read-only
    short-circuit performs no write — only a genuinely new join attempt
    MUST be rejected once the group is disbanded.

    Also runs the one-active-group-per-Member check (`_raise_if_active_elsewhere`)
    right after that short-circuit, before any of the group-specific checks
    below (disbanded/full/password) — none of those matter if the Member
    isn't eligible to join a second group at all. Guest joins are exempt;
    see that function's docstring for why.

    `skip_password` (013-group-invite-friends, FR-007/Clarifications Q1):
    keyword-only, defaults to `False` — every pre-existing caller (list
    join, join-link, guest reconnect) omits it and keeps validating the
    password exactly as before. Only `group_invite.service.accept_invite()`
    passes `skip_password=True` — an invite is itself the creator's
    per-friend authorization, so the invitee never needs to know or enter
    the group's password (research.md #3). This intentionally does not read
    `group.password_ciphertext`/`password_nonce` at all in that path.
    """
    if member is not None:
        existing_result = await session.execute(
            select(RosterEntry).where(
                RosterEntry.group_id == group.id,
                RosterEntry.member_id == member.id,
                RosterEntry.status == "active",
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing, False

        await _raise_if_active_elsewhere(session, member.id, exclude_group_id=group.id)

    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)

    if group.current_member_count >= group.max_members:
        raise ApiError("GROUP_FULL", status_code=409)

    if not skip_password and not verify_password(group, password or ""):
        raise ApiError("GROUP_PASSWORD_INCORRECT", status_code=401)

    if member is not None:
        if not member.nickname:
            raise ApiError("MEMBER_NICKNAME_NOT_SET", status_code=400)
        resolved_nickname = member.nickname
    else:
        stripped = (nickname or "").strip()
        if not stripped or len(stripped) > 20:
            raise ApiError("NICKNAME_REQUIRED_FOR_GUEST", status_code=400)
        resolved_nickname = stripped

    update_result = await session.execute(
        update(Group)
        .where(Group.id == group.id, Group.current_member_count < Group.max_members)
        .values(current_member_count=Group.current_member_count + 1)
    )
    if update_result.rowcount == 0:
        raise ApiError("GROUP_FULL", status_code=409)

    guest_token = secrets.token_urlsafe(32) if member is None else None
    roster_entry = RosterEntry(
        group_id=group.id,
        member_id=member.id if member else None,
        nickname=resolved_nickname,
        status="active",
        is_creator=False,
        wait_count=None,
        guest_session_token=guest_token,
    )
    session.add(roster_entry)
    await session.flush()

    await handle_member_joined(session, group, roster_entry)
    await _touch_activity(session, group)
    await session.commit()
    await session.refresh(group)
    await session.refresh(roster_entry)

    await publish(
        group_notifications_channel(str(group.id)),
        "member.joined",
        {
            "event": "member.joined",
            "roster_entry_id": str(roster_entry.id),
            "nickname": resolved_nickname,
        },
    )
    return roster_entry, True


async def resolve_join_link(session: AsyncSession, join_link_token: uuid.UUID) -> Group:
    """US2: resolves the token itself; whether the group is disbanded/full
    is a field on the returned Group, not this function's concern (FR-009 —
    those are 200 responses with status fields, not error codes)."""
    result = await session.execute(select(Group).where(Group.join_link_token == join_link_token))
    group = result.scalar_one_or_none()
    if group is None:
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return group


async def resolve_guest_session(session: AsyncSession, guest_session_token: str) -> RosterEntry:
    """FR-023~025: an unknown token, a non-`active` roster entry (left/
    kicked), or a disbanded group are all indistinguishable failures here
    (research.md #4) — the frontend treats every case identically (start a
    fresh join flow)."""
    result = await session.execute(
        select(RosterEntry)
        .join(Group, Group.id == RosterEntry.group_id)
        .where(
            RosterEntry.guest_session_token == guest_session_token,
            RosterEntry.status == "active",
            Group.status == "active",
        )
    )
    roster_entry = result.scalar_one_or_none()
    if roster_entry is None:
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return roster_entry


async def active_roster_entry_for_member(
    session: AsyncSession, group_id: uuid.UUID, member_id: uuid.UUID
) -> RosterEntry | None:
    """US6: backs both `joined_by_me` (list) and `already_joined` (join-link
    preview) — a member's existing active `RosterEntry` in this group, if
    any."""
    result = await session.execute(
        select(RosterEntry).where(
            RosterEntry.group_id == group_id,
            RosterEntry.member_id == member_id,
            RosterEntry.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def resolve_active_roster_membership(
    session: AsyncSession,
    group_id: uuid.UUID,
    *,
    guest_session_token: str | None,
    member_id: uuid.UUID | None,
) -> RosterEntry:
    """005-member-view research.md #5: backs every read-only member-view
    endpoint (賽程/戰績/對戰紀錄) plus 退出組團's authorization check.
    Deliberately independent of `resolve_guest_session()` — this MUST NOT
    check `Group.status` (a disbanded group's member view stays readable per
    spec Edge Cases), unlike that function's join-flow semantics. Guest
    token and Member identity are mutually exclusive inputs; whichever is
    given must resolve to an `active` RosterEntry in this exact group, or
    the caller gets the same generic failure regardless of the reason
    (never-joined / already-left / wrong token) — research.md #5."""
    if guest_session_token is not None:
        result = await session.execute(
            select(RosterEntry).where(
                RosterEntry.group_id == group_id,
                RosterEntry.guest_session_token == guest_session_token,
                RosterEntry.status == "active",
            )
        )
        entry = result.scalar_one_or_none()
        if entry is not None:
            return entry
    elif member_id is not None:
        entry = await active_roster_entry_for_member(session, group_id, member_id)
        if entry is not None:
            return entry
    raise ApiError("MEMBERSHIP_REQUIRED", status_code=403)


async def verify_ever_group_member(
    session: AsyncSession, group_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    """014-member-groups-history FR-006 (Clarifications 2026-09-07):
    authorization boundary for the read-only participation-history feature
    — passes if this Member has EVER had a `RosterEntry` in this group,
    regardless of status (active/left/kicked). Deliberately independent of
    `resolve_active_roster_membership()` above, which requires an ACTIVE
    entry and backs live-operation endpoints (schedule/standings/leave) —
    loosening THAT function's threshold would accidentally let a former
    member call live operations again, a real authorization-boundary bug,
    not this feature's intent (research.md #3).

    Errors: `GROUP_MEMBERSHIP_NEVER_HELD` (403)."""
    result = await session.execute(
        select(RosterEntry.id).where(
            RosterEntry.group_id == group_id, RosterEntry.member_id == member_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise ApiError("GROUP_MEMBERSHIP_NEVER_HELD", status_code=403)


async def build_group_standings(session: AsyncSession, group: Group) -> GroupStandingsResponse:
    """005-member-view US2 (FR-005~010): per-round win/loss tally per
    research.md #4, extended for 011-round-robin-scheduling's singles full
    round-robin (a Member can have several *completed* matches within one
    round_number there — `RoundRecord` sums them all rather than the
    original formula's single won/lost/did_not_play/left outcome, which
    silently kept only the last match processed for each (member, round)
    pair). Rounds are exactly those that have ever been generated for this
    group (one `round_history` row per round, including round 1) — a group
    that hasn't pressed Next Round yet has no rows and thus no rounds to
    report.

    018-group-leaderboard (FR-001~FR-012): also ranks the returned
    `members` by total wins — standard competition ranking ("1224": ties
    share a rank, the next distinct value skips accordingly, research.md
    #6), secondary-sorted by `joined_at` (research.md #2). Only currently
    `active` roster entries are returned (FR-008) — a left/kicked member's
    past matches still count toward whichever *active* opponent they
    played, since that comes from `MatchParticipant`/`Match`, not from this
    roster query."""
    round_history_result = await session.execute(
        select(RoundHistory)
        .where(RoundHistory.group_id == group.id)
        .order_by(RoundHistory.round_number)
    )
    round_history_rows = list(round_history_result.scalars())
    rounds = [rh.round_number for rh in round_history_rows]
    started_at_by_round = {rh.round_number: rh.started_at for rh in round_history_rows}

    roster_result = await session.execute(
        select(RosterEntry)
        .where(RosterEntry.group_id == group.id, RosterEntry.status == "active")
        .order_by(RosterEntry.joined_at)
    )
    roster_entries = list(roster_result.scalars())

    participation: dict[tuple[uuid.UUID, int], list[tuple[str, str, str | None]]] = defaultdict(
        list
    )
    if roster_entries:
        entry_ids = [entry.id for entry in roster_entries]
        participants_result = await session.execute(
            select(MatchParticipant, Match)
            .join(Match, Match.id == MatchParticipant.match_id)
            .where(
                Match.group_id == group.id,
                Match.round_number.in_(rounds),
                MatchParticipant.roster_entry_id.in_(entry_ids),
            )
        )
        for participant, match in participants_result.all():
            participation[(participant.roster_entry_id, match.round_number)].append(
                (match.status, participant.team, match.winner_team)
            )

    unranked: list[tuple[RosterEntry, dict[int, RoundRecord], int, int]] = []
    for entry in roster_entries:
        row_rounds: dict[int, RoundRecord] = {}
        for round_number in rounds:
            started_at = started_at_by_round.get(round_number)
            if (
                entry.status in ("left", "kicked")
                and entry.left_at is not None
                and started_at is not None
                and entry.left_at <= started_at
            ):
                row_rounds[round_number] = RoundRecord(wins=0, losses=0, left=True)
            elif started_at is not None and entry.joined_at > started_at:
                row_rounds[round_number] = RoundRecord(wins=0, losses=0, left=False)
            else:
                wins = 0
                losses = 0
                for match_status, team, winner_team in participation.get(
                    (entry.id, round_number), []
                ):
                    if match_status == "completed":
                        if team == winner_team:
                            wins += 1
                        else:
                            losses += 1
                row_rounds[round_number] = RoundRecord(wins=wins, losses=losses, left=False)
        total_wins = sum(record.wins for record in row_rounds.values())
        total_losses = sum(record.losses for record in row_rounds.values())
        unranked.append((entry, row_rounds, total_wins, total_losses))

    # 018-group-leaderboard research.md #2/#6: sort by total_wins descending;
    # `sorted` is stable, and `unranked` starts in `joined_at` order (the
    # roster query above), so ties keep the earlier joiner first without any
    # extra tiebreak key. Standard competition ranking ("1224") — a run of
    # tied total_wins shares one rank number, and the next distinct value's
    # rank is its 1-based position, not "previous rank + 1".
    unranked.sort(key=lambda item: item[2], reverse=True)

    members: list[MemberStandingRow] = []
    previous_wins: int | None = None
    previous_rank = 0
    for position, (entry, row_rounds, total_wins, total_losses) in enumerate(unranked, start=1):
        if total_wins != previous_wins:
            previous_rank = position
            previous_wins = total_wins
        members.append(
            MemberStandingRow(
                roster_entry_id=str(entry.id),
                nickname=entry.nickname,
                current_status=entry.status,
                rounds=row_rounds,
                rank=previous_rank,
                total_wins=total_wins,
                total_losses=total_losses,
            )
        )

    return GroupStandingsResponse(
        current_round_number=group.current_round_number, rounds=rounds, members=members
    )


def _completed_matches_query() -> Select[tuple[Match]]:
    """005-member-view research.md #8: the shared "比賽結果" query base for
    both 團內對戰紀錄 (US3, filters by `group_id`) and 會員跨團對戰紀錄
    (US5, filters by an `EXISTS` on `roster_entries.member_id` — see
    `app/domains/member/service.py`, which imports this function)."""
    return select(Match).where(Match.status == "completed")


async def _build_match_record_summaries(
    session: AsyncSession, matches: list[Match]
) -> list[MatchRecordSummary]:
    if not matches:
        return []
    match_ids = [match.id for match in matches]
    result = await session.execute(
        select(MatchParticipant, RosterEntry)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id.in_(match_ids))
    )
    participants_by_match: dict[uuid.UUID, list[tuple[MatchParticipant, RosterEntry]]] = (
        defaultdict(list)
    )
    for participant, entry in result.all():
        participants_by_match[participant.match_id].append((participant, entry))

    summaries = []
    for match in matches:
        team_a: list[ParticipantSummary] = []
        team_b: list[ParticipantSummary] = []
        for participant, entry in participants_by_match.get(match.id, []):
            summary = ParticipantSummary(
                roster_entry_id=str(entry.id), nickname=entry.nickname, team=participant.team
            )
            (team_a if participant.team == "A" else team_b).append(summary)
        summaries.append(
            MatchRecordSummary(
                match_id=str(match.id),
                round_number=match.round_number,
                team_a=team_a,
                team_b=team_b,
                score_a=match.score_a,
                score_b=match.score_b,
                winner_team=match.winner_team,
                started_at=match.started_at,
                ended_at=match.ended_at,
            )
        )
    return summaries


async def build_group_match_records(
    session: AsyncSession, group_id: uuid.UUID, page: int = 1, *, nickname: str | None = None
) -> GroupMatchRecordsResponse:
    """005-member-view US3 (FR-011/012): 本團已完成比賽列表，僅限本團範圍，
    依比賽結束時間（`ended_at`）由新到舊排序（時間降冪；`round_number`
    僅作為時間相同時的次要排序鍵，一般不會出現同一輪不同場地同時結束的
    情況，但仍保留以確保排序結果穩定）。

    `nickname` (014-member-groups-history follow-up): keyword-only,
    defaults to `None` — every pre-existing caller (this domain's own admin
    match-records endpoint) omits it and keeps its existing behavior
    unchanged. When given, narrows to matches where ANY participant on
    EITHER team has a nickname containing it (case-insensitive substring)
    — a generic "who's in this match" search across the whole group's
    shared history, not scoped to any one viewer's own games."""
    base_query = _completed_matches_query().where(Match.group_id == group_id)
    if nickname:
        participant_nickname_exists = (
            select(MatchParticipant.id)
            .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
            .where(
                MatchParticipant.match_id == Match.id,
                RosterEntry.nickname.ilike(f"%{nickname}%"),
            )
            .exists()
        )
        base_query = base_query.where(participant_nickname_exists)

    count_result = await session.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()
    total_pages = max(1, (total + _MATCH_RECORDS_PAGE_SIZE - 1) // _MATCH_RECORDS_PAGE_SIZE)

    matches_result = await session.execute(
        base_query.order_by(Match.ended_at.desc(), Match.round_number.desc())
        .offset((page - 1) * _MATCH_RECORDS_PAGE_SIZE)
        .limit(_MATCH_RECORDS_PAGE_SIZE)
    )
    matches = list(matches_result.scalars())

    summaries = await _build_match_record_summaries(session, matches)
    return GroupMatchRecordsResponse(matches=summaries, page=page, total_pages=total_pages)


async def get_completed_match_or_404(session: AsyncSession, match_id: uuid.UUID) -> Match:
    """016-match-score-timeline research.md #2: shared match lookup for both
    new match-detail endpoints — reuses `_completed_matches_query()` so
    "what counts as a completed match" is defined in exactly one place."""
    result = await session.execute(_completed_matches_query().where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if match is None:
        raise ApiError("MATCH_NOT_FOUND", status_code=404)
    return match


async def build_match_record_detail(
    session: AsyncSession, match: Match
) -> MatchRecordDetailResponse:
    """016-match-score-timeline research.md #2/#3: reuses
    `_build_match_record_summaries()` for the existing basic-info fields,
    then layers on the `score_events` log (007-live-scoreboard's
    `apply_score_delta()` write path — this function never writes, only
    reads) as `elapsed_seconds`-stamped events plus a three-state
    `record_completeness` derived purely from the events themselves (no
    deploy-timestamp dependency):
    - no events -> `"none"`.
    - first event's `score_a + score_b == 1` -> `"complete"` (it really is
      the match's first point, so nothing was missed before recording).
    - otherwise -> `"partial"` (recording started mid-match).

    Ordered by `created_at, id` — `id` is a secondary sort key only for
    determinism when two events share a `created_at` (concurrent scoring,
    see `test_score_concurrency.py`); it carries no write-order meaning of
    its own."""
    [summary] = await _build_match_record_summaries(session, [match])

    events_result = await session.execute(
        select(ScoreEvent)
        .where(ScoreEvent.match_id == match.id)
        .order_by(ScoreEvent.created_at, ScoreEvent.id)
    )
    score_events = list(events_result.scalars())

    completeness: Literal["complete", "partial", "none"]
    if not score_events:
        completeness = "none"
    elif score_events[0].score_a + score_events[0].score_b == 1:
        completeness = "complete"
    else:
        completeness = "partial"

    started_at = match.started_at
    assert started_at is not None  # always set for completed matches (see MatchRecordSummary)
    event_summaries = [
        ScoreEventSummary(
            side=event.side,
            delta=event.delta,
            score_a=event.score_a,
            score_b=event.score_b,
            elapsed_seconds=int((event.created_at - started_at).total_seconds()),
        )
        for event in score_events
    ]

    return MatchRecordDetailResponse(
        **summary.model_dump(), record_completeness=completeness, events=event_summaries
    )


async def leave_group(
    session: AsyncSession,
    group: Group,
    roster_entry_id: uuid.UUID,
    *,
    guest_session_token: str | None,
    member_id: uuid.UUID | None,
) -> RosterEntry:
    """005-member-view US4 (FR-013~016): a general member leaving on their
    own — reuses 003's `handle_member_left()` verbatim (research.md #7,
    same convergence rules as an admin kick, `new_status` is the only
    difference). The caller MUST be proven to own `roster_entry_id` (Guest
    token or Member identity matches); any mismatch, or an already-non-
    active entry, is reported identically as `ROSTER_ENTRY_NOT_FOUND` —
    this MUST NOT reveal whether the entry exists to someone who can't
    prove ownership of it."""
    result = await session.execute(select(RosterEntry).where(RosterEntry.id == roster_entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.group_id != group.id or entry.status != "active":
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)

    if guest_session_token is not None:
        owns_entry = entry.guest_session_token == guest_session_token
    elif member_id is not None:
        owns_entry = entry.member_id == member_id
    else:
        owns_entry = False
    if not owns_entry:
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)

    await handle_member_left(session, group, entry, new_status="left")
    await session.commit()
    await session.refresh(entry)
    await session.refresh(group)

    await publish(
        group_notifications_channel(str(group.id)),
        "member.left",
        {"roster_entry_id": str(entry.id), "nickname": entry.nickname},
    )
    return entry
