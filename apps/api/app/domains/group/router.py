"""Group domain REST endpoints, per specs/001-create-manage-group/contracts/groups-api.md."""

import uuid
from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ApiError
from app.core.rate_limit import limiter
from app.core.turnstile import verify_turnstile_token
from app.domains.court.models import Court
from app.domains.court.service import get_court_by_id
from app.domains.group import service
from app.domains.group.models import Group
from app.domains.group.schemas import (
    AdminGroupResponse,
    AllCourtsBootstrapResponse,
    AllCourtsCourtSummary,
    CreateGroupRequest,
    CreateGroupResponse,
    EditGroupRequest,
    EditScoringSettingsRequest,
    GroupListItem,
    GroupListResponse,
    GroupMatchRecordsResponse,
    GroupPublicResponse,
    GroupStandingsResponse,
    GuestSessionResponse,
    JoinGroupRequest,
    JoinGroupResponse,
    JoinLinkPreviewResponse,
    LeaveGroupRequest,
    LeaveGroupResponse,
    ReauthRequest,
    ReauthResponse,
    RegenerateAllCourtsLinkResponse,
    RegenerateJoinLinkResponse,
    RegenerateLinkRequest,
    RegeneratePinResponse,
    VerifyPasswordRequest,
    VerifyPasswordResponse,
)
from app.domains.group.security import issue_admin_token, require_admin
from app.domains.member.models import Member
from app.domains.member.security import optional_member, require_verified_member
from app.domains.schedule.schemas import (
    AllCourtsLiveState,
    ScheduleResponse,
    ScoreMutationResult,
    ScoreRequest,
)
from app.domains.schedule.service import (
    abandon_group_matches,
    apply_score_delta,
    auto_pair_on_enter_fixed_partner,
    build_schedule_snapshot,
    clear_partnerships_on_exit,
    court_live_state,
    end_match_early,
)

router = APIRouter(prefix="/groups", tags=["groups"])
# `GET /join/{join_link_token}` lives at the top level, not under `/groups`
# (architecture.md §3.1) — a second, prefix-less router registered alongside
# `router` in app/main.py.
join_router = APIRouter(tags=["groups"])


def _to_public(group: Group) -> GroupPublicResponse:
    return GroupPublicResponse(
        group_id=str(group.id),
        group_number=group.group_number,
        name=group.name,
        has_password=group.password_ciphertext is not None,
        current_member_count=group.current_member_count,
        max_members=group.max_members,
        match_mode=group.match_mode,
        scheduling_mechanism=group.scheduling_mechanism,
        partner_source=group.partner_source,
        activity_time_start=group.activity_time_start,
        activity_time_end=group.activity_time_end,
        status=group.status,
    )


def _to_admin_view(group: Group) -> AdminGroupResponse:
    return AdminGroupResponse(
        group=_to_public(group),
        password_plaintext=service.get_group_password_plaintext(group),
        read_only=group.status == "disbanded",
        base_settings_version=group.base_settings_version,
        admin_token_version=group.admin_token_version,
        join_link_token=str(group.join_link_token),
        join_link_version=group.join_link_version,
        all_courts_control_panel_token=str(group.all_courts_control_panel_token),
        all_courts_link_version=group.all_courts_link_version,
    )


@router.post("", response_model=CreateGroupResponse, status_code=201)
async def create_group(
    payload: CreateGroupRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> CreateGroupResponse:
    """Create a group (anonymous or member-authenticated) and its creator
    RosterEntry in one transaction. Requires a valid Turnstile token.

    Errors: `VALIDATION_ERROR`, `CAPTCHA_INVALID`, `CAPTCHA_EXPIRED`,
    `GROUP_MEMBER_CAP_EXCEEDED`, `NICKNAME_REQUIRED_FOR_GUEST`,
    `MEMBER_NICKNAME_NOT_SET`.
    """
    await verify_turnstile_token(payload.turnstile_token)
    group, roster_entry, admin_pin, guest_token = await service.create_group(
        session, payload, member=member
    )
    admin_token = issue_admin_token(str(group.id), group.admin_token_version)
    return CreateGroupResponse(
        group_id=str(group.id),
        group_number=group.group_number,
        admin_pin=admin_pin,
        admin_token=admin_token,
        current_member_count=group.current_member_count,
        roster_entry_id=str(roster_entry.id),
        guest_session_token=guest_token,
    )


@router.get("", response_model=GroupListResponse)
async def list_groups(
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
    page: int = 1,
    court_name: str | None = None,
    court_id: uuid.UUID | None = None,
    time_start: time | None = None,
    time_end: time | None = None,
) -> GroupListResponse:
    """Public group browse list (US1/US5); an optional `Authorization`
    Bearer token adds per-item `joined_by_me` personalization (US6, research.md
    #2). Excludes disbanded groups (data-model.md §1)."""
    groups, total_pages = await service.list_groups(
        session,
        page=page,
        court_name=court_name,
        court_id=court_id,
        time_start=time_start,
        time_end=time_end,
    )
    # Computed once for the whole list, not per item — a Member has at most
    # one active RosterEntry anywhere (the one-active-group invariant), so
    # this single lookup already answers "is it in THIS item's group or a
    # different one" for every item below.
    active_group_id = (
        await service.get_active_group_id_for_member(session, member.id)
        if member is not None
        else None
    )
    items = []
    for group in groups:
        court_names = await service.court_names_for_group(session, group.id)
        creator_nickname = await service.creator_nickname_for_group(session, group.id)
        joined_by_me = None
        created_by_me = None
        member_active_elsewhere = None
        if member is not None:
            existing = await service.active_roster_entry_for_member(session, group.id, member.id)
            joined_by_me = existing is not None
            created_by_me = group.created_by_member_id == member.id
            member_active_elsewhere = active_group_id is not None and active_group_id != group.id
        items.append(
            GroupListItem(
                **_to_public(group).model_dump(),
                court_names=court_names,
                creator_nickname=creator_nickname,
                joined_by_me=joined_by_me,
                created_by_me=created_by_me,
                member_active_elsewhere=member_active_elsewhere,
            )
        )
    return GroupListResponse(groups=items, page=page, total_pages=total_pages)


@router.post("/{group_id}/verify-password", response_model=VerifyPasswordResponse)
async def verify_password(
    group_id: uuid.UUID,
    payload: VerifyPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerifyPasswordResponse:
    """FR-016: no lockout — unlimited retries. Errors: `GROUP_NOT_FOUND`,
    `GROUP_DISBANDED`."""
    group = await service.get_group_by_id(session, group_id)
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)
    return VerifyPasswordResponse(correct=service.verify_password(group, payload.password))


@router.post("/{group_id}/join", response_model=JoinGroupResponse, status_code=201)
async def join_group(
    group_id: uuid.UUID,
    payload: JoinGroupRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> JoinGroupResponse:
    """Guest (no `Authorization` header) or member-authenticated join
    (006-issued Bearer token, US6). Errors: `GROUP_NOT_FOUND`,
    `GROUP_DISBANDED`, `GROUP_FULL`, `GROUP_PASSWORD_INCORRECT`,
    `NICKNAME_REQUIRED_FOR_GUEST`, `MEMBER_NICKNAME_NOT_SET`."""
    group = await service.get_group_by_id(session, group_id)
    roster_entry, created_new = await service.join_group(
        session, group, member=member, password=payload.password, nickname=payload.nickname
    )
    return JoinGroupResponse(
        roster_entry_id=str(roster_entry.id),
        nickname=roster_entry.nickname,
        guest_session_token=roster_entry.guest_session_token,
        created_new=created_new,
    )


@router.get("/{group_id}", response_model=GroupPublicResponse)
async def get_group_public(
    group_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> GroupPublicResponse:
    """Public group summary (join-preview / listing use). Never includes the
    group password, hashed or plaintext — only `has_password`. An optional
    `Authorization` Bearer token adds `already_joined` (US6, same signal as
    `GroupListItem.joined_by_me`) so the join flow can skip the password
    step for a member who's already in this group."""
    group = await service.get_group_by_id(session, group_id)
    response = _to_public(group)
    if member is not None:
        existing = await service.active_roster_entry_for_member(session, group.id, member.id)
        response.already_joined = existing is not None
    return response


@router.post("/reauth", response_model=ReauthResponse)
@limiter.limit("20/minute")
async def reauth(
    request: Request,  # noqa: ARG001 - required by slowapi
    payload: ReauthRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReauthResponse:
    """Exchange group number + admin PIN for a fresh admin token. Rate-limited
    and lockout-guarded (10 wrong attempts → 15 min lock, research.md #1).

    Errors: `GROUP_NOT_FOUND`, `GROUP_ADMIN_PIN_INCORRECT`,
    `GROUP_ADMIN_LOCKED` (`detail.retry_after_seconds`).
    """
    token, group = await service.reauth_admin(session, payload.group_number, payload.admin_pin)
    return ReauthResponse(admin_token=token, group_id=str(group.id))


@router.get("/{group_id}/admin", response_model=AdminGroupResponse)
async def get_admin_view(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
) -> AdminGroupResponse:
    """Full admin-page state, including the decrypted group password. The
    ONLY endpoint in this domain that returns password plaintext — always
    behind `require_admin` (SC-009).

    Errors: `ADMIN_TOKEN_INVALID`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return _to_admin_view(group)


@router.patch("/{group_id}", response_model=AdminGroupResponse)
async def edit_group(
    group_id: uuid.UUID,
    payload: EditGroupRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminGroupResponse:
    """Edit name/password/match_mode/max_members/activity time. Optimistic
    lock on `base_settings_version` (FR-028); response carries the new
    version so the caller can chain further edits without refetching.

    Errors: `ADMIN_TOKEN_INVALID`, `VERSION_CONFLICT`,
    `MATCH_MODE_MEMBER_CAP_CONFLICT`, `GROUP_MEMBER_CAP_EXCEEDED`,
    `GROUP_DISBANDED`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    previous_mechanism = group.scheduling_mechanism
    updated = await service.edit_group(session, group, payload)

    # spec 003 research.md #4: Partnership side effects of switching
    # scheduling_mechanism live here (router layer), not inside 001's
    # edit_group — auto-pairing/clearing requires querying a table owned by
    # the schedule domain, which edit_group (group-owned) has no business
    # knowing about.
    mechanism_changed = (
        payload.scheduling_mechanism is not None
        and payload.scheduling_mechanism != previous_mechanism
    )
    if mechanism_changed:
        if previous_mechanism == "fixed_partner":
            await clear_partnerships_on_exit(session, updated)
        if updated.scheduling_mechanism == "fixed_partner":
            await auto_pair_on_enter_fixed_partner(session, updated)
        await session.commit()

    return _to_admin_view(updated)


@router.patch("/{group_id}/scoring-settings", response_model=AdminGroupResponse)
async def edit_scoring_settings(
    group_id: uuid.UUID,
    payload: EditScoringSettingsRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminGroupResponse:
    """Edit the team-level match scoring settings (FR-013–016). Same
    `base_settings_version` optimistic lock as `PATCH /{group_id}`.

    Errors: `ADMIN_TOKEN_INVALID`, `VERSION_CONFLICT`, `GROUP_DISBANDED`,
    `INVALID_CUSTOM_SCORING`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.edit_scoring_settings(session, group, payload)
    return _to_admin_view(updated)


@router.post("/{group_id}/disband", response_model=GroupPublicResponse)
async def disband(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupPublicResponse:
    """Disband the group (idempotent). Same transaction: status flips to
    `disbanded`, unfinished matches are abandoned, and `group.disbanded` is
    published to every court channel plus the group notifications channel.

    Errors: `ADMIN_TOKEN_INVALID`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.disband_group(
        session, group, abandon_unfinished_matches=abandon_group_matches
    )
    return _to_public(updated)


@router.post("/{group_id}/regenerate-admin-pin", response_model=RegeneratePinResponse)
async def regenerate_admin_pin(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegeneratePinResponse:
    """Issue a new admin PIN, bumping `admin_token_version` so every
    previously-issued admin token (including the caller's own) is
    invalidated except the fresh one returned here (FR-026/027).

    Errors: `ADMIN_TOKEN_INVALID`, `VERSION_CONFLICT`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    new_pin, new_token = await service.regenerate_admin_pin(session, group)
    return RegeneratePinResponse(admin_pin=new_pin, admin_token=new_token)


@router.post("/{group_id}/forgot-admin-pin", response_model=RegeneratePinResponse)
async def forgot_admin_pin(
    group_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegeneratePinResponse:
    """006-member-friends US4: member-only PIN recovery, no admin session
    required. Errors: `GROUP_NOT_FOUND`, `NOT_GROUP_CREATOR`."""
    new_pin, new_token = await service.forgot_admin_pin(session, group_id, member.id)
    return RegeneratePinResponse(admin_pin=new_pin, admin_token=new_token)


@router.post("/{group_id}/creator-admin-token", response_model=ReauthResponse)
async def get_creator_admin_token(
    group_id: uuid.UUID,
    member: Annotated[Member, Depends(require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReauthResponse:
    """"回到我的團": a logged-in member who created this group gets a fresh
    admin token with no PIN prompt — unlike `forgot-admin-pin` above, this
    is purely additive (current `admin_token_version`, no reset), so
    clicking it repeatedly never disturbs an existing admin session
    elsewhere. Errors: `GROUP_NOT_FOUND`, `NOT_GROUP_CREATOR`."""
    group = await service.get_group_if_creator(session, group_id, member.id)
    token = issue_admin_token(str(group.id), group.admin_token_version)
    return ReauthResponse(admin_token=token, group_id=str(group.id))


@router.post("/{group_id}/regenerate-join-link", response_model=RegenerateJoinLinkResponse)
async def regenerate_join_link(
    group_id: uuid.UUID,
    payload: RegenerateLinkRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateJoinLinkResponse:
    """Per FR-033, this MUST NOT publish any realtime event — the join link
    is validated by the backend at join-request time, not via subscription.

    Errors: `ADMIN_TOKEN_INVALID`, `VERSION_CONFLICT`, `GROUP_DISBANDED`.
    """
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.regenerate_join_link(session, group, payload.expected_version)
    return RegenerateJoinLinkResponse(
        join_link_token=str(updated.join_link_token),
        join_link_version=updated.join_link_version,
    )


@router.post(
    "/{group_id}/regenerate-all-courts-link", response_model=RegenerateAllCourtsLinkResponse
)
async def regenerate_all_courts_link(
    group_id: uuid.UUID,
    payload: RegenerateLinkRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateAllCourtsLinkResponse:
    """Errors: `ADMIN_TOKEN_INVALID`, `VERSION_CONFLICT`, `GROUP_DISBANDED`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.regenerate_all_courts_link(session, group, payload.expected_version)
    return RegenerateAllCourtsLinkResponse(
        all_courts_control_panel_token=str(updated.all_courts_control_panel_token),
        all_courts_link_version=updated.all_courts_link_version,
    )


@router.get("/by-guest-token/{token}", response_model=GuestSessionResponse)
async def resolve_guest_session(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GuestSessionResponse:
    """FR-023: Guest reconnect/refresh. Errors: `LINK_NOT_FOUND`."""
    roster_entry = await service.resolve_guest_session(session, token)
    return GuestSessionResponse(
        roster_entry_id=str(roster_entry.id),
        group_id=str(roster_entry.group_id),
        nickname=roster_entry.nickname,
    )


@router.get("/by-all-courts-token/{token}", response_model=AllCourtsBootstrapResponse)
async def get_group_by_all_courts_token(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AllCourtsBootstrapResponse:
    """Public, unauthenticated. Bootstrap + 5-minute heartbeat for the
    all-courts control panel (specs/002-court-management). Errors:
    `LINK_NOT_FOUND`.
    """
    group, courts = await service.get_group_by_all_courts_token(session, token)
    return AllCourtsBootstrapResponse(
        group_id=str(group.id),
        all_courts_link_version=group.all_courts_link_version,
        group_disbanded=group.status == "disbanded",
        courts=[AllCourtsCourtSummary(court_id=str(c.id), name=c.name) for c in courts],
    )


# --- 007-live-scoreboard: 全部場地控制板 ---


async def _all_courts_court(
    token: uuid.UUID, court_id: uuid.UUID, session: AsyncSession
) -> tuple[Group, Court]:
    """Resolves the all-courts token to its group, then the target court by
    id — MUST also belong to that same group (research.md #4's authorization
    boundary applies equally here: an all-courts token from one group MUST
    NOT be usable to operate a court belonging to a different group)."""
    group, _courts = await service.get_group_by_all_courts_token(session, token)
    court = await get_court_by_id(session, court_id)
    if court.group_id != group.id:
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return group, court


@router.get("/by-all-courts-token/{token}/state", response_model=AllCourtsLiveState)
async def get_all_courts_state(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AllCourtsLiveState:
    """公開，無需登入。初始載入 + 斷線重連強制覆蓋（FR-024）。Errors:
    `LINK_NOT_FOUND`."""
    group, courts = await service.get_group_by_all_courts_token(session, token)
    states = [await court_live_state(session, court) for court in courts]
    return AllCourtsLiveState(
        group_id=str(group.id), round_number=group.current_round_number, courts=states
    )


@router.post(
    "/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/score",
    response_model=ScoreMutationResult,
)
async def score_by_all_courts_token(
    token: uuid.UUID,
    court_id: uuid.UUID,
    match_id: uuid.UUID,
    payload: ScoreRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """Errors: `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`."""
    _group, court = await _all_courts_court(token, court_id, session)
    return await apply_score_delta(session, court, match_id, payload.side, payload.delta)


@router.post(
    "/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/end",
    response_model=ScoreMutationResult,
)
async def end_match_by_all_courts_token(
    token: uuid.UUID,
    court_id: uuid.UUID,
    match_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """Errors: `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`."""
    _group, court = await _all_courts_court(token, court_id, session)
    return await end_match_early(session, court, match_id)


# --- 005-member-view: 團內成員視圖（賽程/戰績/對戰紀錄/退出組團）---


@router.get("/{group_id}/member-schedule", response_model=ScheduleResponse)
async def get_member_schedule(
    group_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
    guest_session_token: str | None = None,
) -> ScheduleResponse:
    """US1 (FR-003/004): a one-way read model reuse of the admin schedule
    snapshot (research.md #6) — disbanded groups stay readable (research.md
    #5), unlike the join flow. Errors: `MEMBERSHIP_REQUIRED`."""
    await service.resolve_active_roster_membership(
        session,
        group_id,
        guest_session_token=guest_session_token,
        member_id=member.id if member is not None else None,
    )
    group = await service.get_group_by_id(session, group_id)
    return await build_schedule_snapshot(session, group)


@router.get("/{group_id}/standings", response_model=GroupStandingsResponse)
async def get_group_standings(
    group_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
    guest_session_token: str | None = None,
) -> GroupStandingsResponse:
    """US2 (FR-005~010): four-state per-round standings, this team only
    (FR-009). Errors: `MEMBERSHIP_REQUIRED`."""
    await service.resolve_active_roster_membership(
        session,
        group_id,
        guest_session_token=guest_session_token,
        member_id=member.id if member is not None else None,
    )
    group = await service.get_group_by_id(session, group_id)
    return await service.build_group_standings(session, group)


@router.get("/{group_id}/match-records", response_model=GroupMatchRecordsResponse)
async def get_group_match_records(
    group_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
    guest_session_token: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> GroupMatchRecordsResponse:
    """US3 (FR-011/012): 本團已完成比賽列表。Errors: `MEMBERSHIP_REQUIRED`."""
    await service.resolve_active_roster_membership(
        session,
        group_id,
        guest_session_token=guest_session_token,
        member_id=member.id if member is not None else None,
    )
    return await service.build_group_match_records(session, group_id, page)


@router.post(
    "/{group_id}/roster/{roster_entry_id}/leave", response_model=LeaveGroupResponse, status_code=201
)
async def leave_group(
    group_id: uuid.UUID,
    roster_entry_id: uuid.UUID,
    payload: LeaveGroupRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> LeaveGroupResponse:
    """US4 (FR-013~016): a general member's self-service exit — MUST be the
    `roster_entry_id` owner (Guest token or Member identity match), never
    someone else's. Errors: `ROSTER_ENTRY_NOT_FOUND`."""
    group = await service.get_group_by_id(session, group_id)
    updated = await service.leave_group(
        session,
        group,
        roster_entry_id,
        guest_session_token=payload.guest_session_token,
        member_id=member.id if member is not None else None,
    )
    return LeaveGroupResponse(roster_entry_id=str(updated.id), status="left")


@join_router.get("/join/{join_link_token}", response_model=JoinLinkPreviewResponse)
async def resolve_join_link(
    join_link_token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> JoinLinkPreviewResponse:
    """US2: skips list search. `status`/`current_member_count` fields (not
    error codes) tell the frontend when the group is disbanded/full — see
    contracts/join-api.md. An optional `Authorization` Bearer token adds
    the FR-020a `already_joined` short-circuit signal (US6). Errors:
    `LINK_NOT_FOUND`."""
    group = await service.resolve_join_link(session, join_link_token)
    court_names = await service.court_names_for_group(session, group.id)
    creator_nickname = await service.creator_nickname_for_group(session, group.id)
    already_joined = False
    roster_entry_id = None
    if member is not None:
        existing = await service.active_roster_entry_for_member(session, group.id, member.id)
        if existing is not None:
            already_joined = True
            roster_entry_id = str(existing.id)
    return JoinLinkPreviewResponse(
        # `_to_public()` never sets `already_joined` itself (only this
        # router function's per-call logic does, right below) — excluded
        # here to avoid colliding with the explicit kwarg of the same name.
        **_to_public(group).model_dump(exclude={"already_joined"}),
        court_names=court_names,
        creator_nickname=creator_nickname,
        already_joined=already_joined,
        roster_entry_id=roster_entry_id,
    )
