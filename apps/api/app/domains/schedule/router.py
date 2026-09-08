"""Schedule domain REST endpoints, per
specs/003-schedule-rotation/contracts/schedule-api.md."""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ApiError
from app.domains.court import service as court_service
from app.domains.court.models import Court
from app.domains.court.service import get_court_by_id
from app.domains.group.models import Group
from app.domains.group.security import require_admin
from app.domains.roster.models import RosterEntry
from app.domains.schedule import service
from app.domains.schedule.schemas import (
    AutoNextRoundRequest,
    AutoNextRoundResponse,
    CourtLiveState,
    CourtStateResponse,
    KickMemberResponse,
    ManualAssignRequest,
    MatchDetailResponse,
    PartnershipReassignRequest,
    PartnershipsResponse,
    RegenerateGuestLinkResponse,
    RoundMatchesResponse,
    ScheduleResponse,
    ScoreMutationResult,
    ScoreRequest,
)

router = APIRouter(tags=["schedule"])


async def _admin_court(
    court_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Court:
    """Same court-scoped admin guard as court/router.py's own dependency —
    duplicated rather than imported to avoid a schedule -> court -> schedule
    router import cycle; both delegate to the same `get_court_by_id`."""
    court = await get_court_by_id(session, court_id)
    if court.group_id != group.id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return court


@router.get("/groups/{group_id}/schedule", response_model=ScheduleResponse)
async def get_schedule(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScheduleResponse:
    """Admin-page read model: each court's current match (or why it's
    waiting) and the active roster's schedule status. Errors:
    `ADMIN_TOKEN_INVALID`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.build_schedule_snapshot(session, group)


@router.get("/groups/{group_id}/schedule/matches", response_model=RoundMatchesResponse)
async def get_round_matches(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoundMatchesResponse:
    """011-round-robin-scheduling: 本輪完整賽程清單（管理頁「本輪賽程清單」
    區塊），涵蓋 queued/in_progress/completed/abandoned 全部狀態，依產生
    順序排列，讓管理員能看到整份預先排好的循環賽賽程，而不只是每個場地
    目前這一場。Errors: `ADMIN_TOKEN_INVALID`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.build_round_matches_list(session, group)


@router.post("/groups/{group_id}/next-round", response_model=ScheduleResponse)
async def next_round(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScheduleResponse:
    """Forces the current round to end and generates the next one (FR-031).
    Errors: `ADMIN_TOKEN_INVALID`, `NO_COURTS_AVAILABLE`,
    `ROUND_GENERATION_IN_PROGRESS`, `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`
    (011-round-robin-scheduling FR-003)."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.generate_next_round(session, group)
    return await service.build_schedule_snapshot(session, updated)


@router.patch("/groups/{group_id}/auto-next-round", response_model=AutoNextRoundResponse)
async def set_auto_next_round(
    group_id: uuid.UUID,
    payload: AutoNextRoundRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AutoNextRoundResponse:
    """Errors: `ADMIN_TOKEN_INVALID`,
    `AUTO_NEXT_ROUND_NOT_SUPPORTED_IN_MANUAL_MODE`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.set_auto_next_round(session, group, payload.enabled)
    return AutoNextRoundResponse(auto_next_round=updated.auto_next_round)


@router.get("/groups/{group_id}/partnerships", response_model=PartnershipsResponse)
async def get_partnerships(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PartnershipsResponse:
    """Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.build_partnerships_snapshot(session, group)


@router.patch("/groups/{group_id}/partnerships", response_model=PartnershipsResponse)
async def reassign_partnership(
    group_id: uuid.UUID,
    payload: PartnershipReassignRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PartnershipsResponse:
    """Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `VALIDATION_ERROR`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    await service.manual_partnership_reassign(
        session, group, uuid.UUID(payload.player_a_id), uuid.UUID(payload.player_b_id)
    )
    await session.commit()
    return await service.build_partnerships_snapshot(session, group)


@router.post(
    "/courts/{court_id}/manual-assign", response_model=MatchDetailResponse, status_code=201
)
async def manual_assign(
    payload: ManualAssignRequest,
    court: Annotated[Court, Depends(_admin_court)],
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchDetailResponse:
    """Manual scheduling's court-by-court assignment (FR-011~015). Errors:
    `ADMIN_TOKEN_INVALID`, `COURT_NOT_WAITING`, `SCHEDULING_MECHANISM_MISMATCH`,
    `PARTICIPANT_ALREADY_PLAYING`, `PARTICIPANT_NOT_ACTIVE`,
    `DUPLICATE_PARTICIPANT`, `VALIDATION_ERROR`."""
    team_a = [uuid.UUID(pid) for pid, team in payload.teams.items() if team == "A"]
    team_b = [uuid.UUID(pid) for pid, team in payload.teams.items() if team == "B"]
    match = await service.manual_assign(session, group, court, team_a=team_a, team_b=team_b)
    return await service.build_match_detail(session, match, team_a, team_b)


@router.delete("/groups/{group_id}/members/{roster_entry_id}", response_model=KickMemberResponse)
async def kick_member(
    group_id: uuid.UUID,
    roster_entry_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KickMemberResponse:
    """Kicks a member from the roster (FR-037), converging the current
    round's schedule per FR-039~041 and publishing `member.left`. Errors:
    `ADMIN_TOKEN_INVALID`, `ROSTER_ENTRY_NOT_FOUND`,
    `ROSTER_ENTRY_ALREADY_LEFT`, `CANNOT_KICK_CREATOR`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    result = await session.execute(select(RosterEntry).where(RosterEntry.id == roster_entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)
    updated = await service.kick_member(session, group, entry)
    return KickMemberResponse(roster_entry_id=str(updated.id), status=updated.status)


@router.post(
    "/groups/{group_id}/members/{roster_entry_id}/regenerate-guest-link",
    response_model=RegenerateGuestLinkResponse,
)
async def regenerate_guest_link(
    group_id: uuid.UUID,
    roster_entry_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateGuestLinkResponse:
    """Constitution IV: admin can independently regenerate a guest's
    shareable link to invalidate a leaked copy — same guarantee already
    given for the admin PIN/join link/all-courts link. Errors:
    `ADMIN_TOKEN_INVALID`, `ROSTER_ENTRY_NOT_FOUND`, `NOT_A_GUEST_ENTRY`,
    `ROSTER_ENTRY_ALREADY_LEFT`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    result = await session.execute(select(RosterEntry).where(RosterEntry.id == roster_entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)
    updated = await service.regenerate_guest_session_token(session, group, entry)
    return RegenerateGuestLinkResponse(
        roster_entry_id=str(updated.id),
        guest_session_token=cast(str, updated.guest_session_token),
    )


# --- 007-live-scoreboard: 即時計分板與控制板 ---


def _court_state_response(
    court: Court, group: Group, link_type: str, state: CourtLiveState
) -> CourtStateResponse:
    return CourtStateResponse(
        court_id=str(court.id),
        group_id=str(group.id),
        name=court.name,
        link_type=link_type,
        link_version=court.scoreboard_link_version
        if link_type == "scoreboard"
        else court.control_panel_link_version,
        deleted=court.deleted_at is not None,
        group_disbanded=group.status == "disbanded",
        round_number=state.round_number,
        current_match=state.current_match,
        waiting_reason=state.waiting_reason,
        next_up=state.next_up,
    )


@router.get("/courts/by-token/{token}/state", response_model=CourtStateResponse)
async def get_court_state(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtStateResponse:
    """公開，無需登入（FR-020）——`token` 接受 `scoreboard_token` 或
    `control_panel_token`（唯讀，research.md #3 之權限邊界不適用於此端點）。
    Errors: `LINK_NOT_FOUND`."""
    court, group, link_type = await court_service.get_court_by_token(session, token)
    state = await service.court_live_state(session, court)
    return _court_state_response(court, group, link_type, state)


@router.post(
    "/courts/by-token/{token}/matches/{match_id}/score", response_model=ScoreMutationResult
)
async def score_by_token(
    token: uuid.UUID,
    match_id: uuid.UUID,
    payload: ScoreRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """僅接受 `control_panel_token`（research.md #3）。Errors:
    `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`。"""
    court, _group, link_type = await court_service.get_court_by_token(session, token)
    if link_type != "control_panel":
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return await service.apply_score_delta(session, court, match_id, payload.side, payload.delta)


@router.post("/courts/by-token/{token}/matches/{match_id}/end", response_model=ScoreMutationResult)
async def end_match_by_token(
    token: uuid.UUID,
    match_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """僅接受 `control_panel_token`（research.md #3）。Errors:
    `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`。"""
    court, _group, link_type = await court_service.get_court_by_token(session, token)
    if link_type != "control_panel":
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return await service.end_match_early(session, court, match_id)


@router.post(
    "/groups/{group_id}/courts/{court_id}/matches/{match_id}/score",
    response_model=ScoreMutationResult,
)
async def score_by_admin(
    group_id: uuid.UUID,
    match_id: uuid.UUID,
    payload: ScoreRequest,
    court: Annotated[Court, Depends(_admin_court)],
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """管理員版本（開團管理頁場地控制區塊，research.md #10）。Errors:
    `ADMIN_TOKEN_INVALID`、`MATCH_NOT_FOUND`。"""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.apply_score_delta(session, court, match_id, payload.side, payload.delta)


@router.post(
    "/groups/{group_id}/courts/{court_id}/matches/{match_id}/end",
    response_model=ScoreMutationResult,
)
async def end_match_by_admin(
    group_id: uuid.UUID,
    match_id: uuid.UUID,
    court: Annotated[Court, Depends(_admin_court)],
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """管理員版本。Errors: `ADMIN_TOKEN_INVALID`、`MATCH_NOT_FOUND`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.end_match_early(session, court, match_id)
