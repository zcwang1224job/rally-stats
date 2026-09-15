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
    ChangeMatchPlayerRequest,
    CourtLiveState,
    CourtStateResponse,
    KickMemberResponse,
    ManualAssignRequest,
    MatchDetailResponse,
    NextRoundRequest,
    PartnershipReassignRequest,
    PartnershipsResponse,
    RegenerateGuestLinkResponse,
    ReorderPlannedMatchesRequest,
    RoundMatchesResponse,
    ScheduleResponse,
    ScoreMutationResult,
    ScoreRequest,
    SwapPlannedMatchPlayersRequest,
    TemporaryPairingsResponse,
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
    payload: NextRoundRequest | None = None,
) -> ScheduleResponse:
    """Forces the current round to end and generates the next one (FR-031).
    017-fixed-partner-autofill: optional `temporary_pairings` body field
    (omitted/null/empty = unchanged existing behavior, US3) — only consumed
    when `scheduling_mechanism == "fixed_partner"` and `partner_source ==
    "manual"`; ignored otherwise. Errors: `ADMIN_TOKEN_INVALID`,
    `NO_COURTS_AVAILABLE`, `ROUND_GENERATION_IN_PROGRESS`,
    `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT` (011-round-robin-scheduling
    FR-003)."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    temporary_pairings = (
        [(uuid.UUID(p.player_a_id), uuid.UUID(p.player_b_id)) for p in payload.temporary_pairings]
        if payload is not None
        else None
    )
    updated = await service.generate_next_round(session, group, temporary_pairings)
    return await service.build_schedule_snapshot(session, updated)


@router.post("/groups/{group_id}/schedule/end-round", response_model=ScheduleResponse)
async def end_round(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScheduleResponse:
    """018-plan-then-start: the admin-facing "結束這一輪" step — force-ends
    whatever's still unfinished in the current round, without generating a
    new one. Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`
    (manual mode — use `/next-round` instead), `ROUND_GENERATION_IN_PROGRESS`,
    `ROUND_NOT_IN_PROGRESS` (nothing to end — the round is already
    finished)."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.end_current_round(session, group)
    return await service.build_schedule_snapshot(session, updated)


@router.post("/groups/{group_id}/schedule/plan", response_model=ScheduleResponse)
async def plan_round(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    payload: NextRoundRequest | None = None,
) -> ScheduleResponse:
    """018-plan-then-start: the admin-facing "規劃賽程安排" step for
    algorithmic mechanisms — generates the next round's matches without
    starting them, so the admin can review/adjust the plan (see
    `GET .../schedule/matches` and `POST .../schedule/matches/swap`) before
    `POST .../schedule/start`. Errors: `ADMIN_TOKEN_INVALID`,
    `SCHEDULING_MECHANISM_MISMATCH` (manual mode — use `/next-round`
    instead), `NO_COURTS_AVAILABLE`, `ROUND_GENERATION_IN_PROGRESS`,
    `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    temporary_pairings = (
        [(uuid.UUID(p.player_a_id), uuid.UUID(p.player_b_id)) for p in payload.temporary_pairings]
        if payload is not None
        else None
    )
    updated = await service.plan_next_round(session, group, temporary_pairings)
    return await service.build_schedule_snapshot(session, updated)


@router.post("/groups/{group_id}/schedule/start", response_model=ScheduleResponse)
async def start_round(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScheduleResponse:
    """018-plan-then-start: the "Next Round" confirm step that follows
    `POST .../schedule/plan` — pulls the already-planned round's matches
    onto courts. Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `NO_COURTS_AVAILABLE`, `ROUND_GENERATION_IN_PROGRESS`, `ROUND_NOT_PLANNED`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    updated = await service.start_planned_round(session, group)
    return await service.build_schedule_snapshot(session, updated)


@router.post("/groups/{group_id}/schedule/matches/swap", response_model=RoundMatchesResponse)
async def swap_planned_match_players(
    group_id: uuid.UUID,
    payload: SwapPlannedMatchPlayersRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoundMatchesResponse:
    """018-plan-then-start: swaps two players' match assignments for any two
    not-yet-terminal matches (`queued`/`in_progress`) — including a round
    already under way, not just `awaiting_start`. Errors:
    `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `MATCH_ALREADY_ENDED`, `VALIDATION_ERROR`, `DUPLICATE_PARTICIPANT`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    await service.swap_planned_match_players(
        session,
        group,
        uuid.UUID(payload.match_id_1),
        uuid.UUID(payload.roster_entry_id_1),
        uuid.UUID(payload.match_id_2),
        uuid.UUID(payload.roster_entry_id_2),
    )
    return await service.build_round_matches_list(session, group)


@router.post(
    "/groups/{group_id}/schedule/matches/change-player", response_model=RoundMatchesResponse
)
async def change_match_player(
    group_id: uuid.UUID,
    payload: ChangeMatchPlayerRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoundMatchesResponse:
    """018-plan-then-start: directly replaces one match participant with a
    specific substitute (as opposed to swapping with another match).
    Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `MATCH_ALREADY_ENDED`, `VALIDATION_ERROR`, `DUPLICATE_PARTICIPANT`,
    `PARTICIPANT_NOT_ACTIVE`, `PARTICIPANT_ALREADY_PLAYING`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    await service.change_match_player(
        session,
        group,
        uuid.UUID(payload.match_id),
        uuid.UUID(payload.old_roster_entry_id),
        uuid.UUID(payload.new_roster_entry_id),
    )
    return await service.build_round_matches_list(session, group)


@router.post("/groups/{group_id}/schedule/matches/reorder", response_model=RoundMatchesResponse)
async def reorder_planned_matches(
    group_id: uuid.UUID,
    payload: ReorderPlannedMatchesRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoundMatchesResponse:
    """018-plan-then-start: drag-reorders the round's still-`queued`
    call-up order — works whether the round is `awaiting_start` or already
    `in_progress`. Errors: `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `ROUND_NOT_PLANNED` (nothing queued left to reorder), `VALIDATION_ERROR`
    (match_ids isn't exactly a permutation of the round's queued matches)."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    await service.reorder_planned_matches(
        session, group, [uuid.UUID(match_id) for match_id in payload.match_ids]
    )
    return await service.build_round_matches_list(session, group)


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


@router.delete(
    "/groups/{group_id}/partnerships/{roster_entry_id}", response_model=PartnershipsResponse
)
async def dissolve_partnership(
    group_id: uuid.UUID,
    roster_entry_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PartnershipsResponse:
    """管理員手動拆散一組正式搭檔（涵蓋「只剩最後一組搭檔、沒有第三人可
    互換」的邊界情況——見 service.dissolve_partnership 說明）。Errors:
    `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `PARTNERSHIP_NOT_FOUND`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    await service.dissolve_partnership(session, group, roster_entry_id)
    await session.commit()
    return await service.build_partnerships_snapshot(session, group)


@router.post(
    "/groups/{group_id}/partnerships/random-preview", response_model=TemporaryPairingsResponse
)
async def preview_random_partner_pairing(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TemporaryPairingsResponse:
    """017-fixed-partner-autofill FR-001: pure, no-side-effect preview of a
    random pairing for currently-unpaired active members. Errors:
    `ADMIN_TOKEN_INVALID`, `SCHEDULING_MECHANISM_MISMATCH`,
    `PARTNER_SOURCE_MISMATCH`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return await service.preview_random_partner_pairing(session, group)


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
        scoreboard_scoring_enabled=group.scoreboard_scoring_enabled,
        round_number=state.round_number,
        current_match=state.current_match,
        waiting_reason=state.waiting_reason,
        next_up=state.next_up,
    )


def _can_score_by_token(link_type: str, group: Group) -> bool:
    """018-plan-then-start follow-up: `control_panel` links can always
    score (research.md #3's original boundary); a `scoreboard` link can
    ALSO score, but only once the group's admin has opted in via
    `PATCH /groups/{group_id}/scoreboard-scoring` — off by default, since
    the scoreboard link is typically shared more widely (posted for
    spectators) than the control-panel one."""
    return link_type == "control_panel" or (
        link_type == "scoreboard" and group.scoreboard_scoring_enabled
    )


@router.get("/courts/by-token/{token}/state", response_model=CourtStateResponse)
async def get_court_state(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtStateResponse:
    """公開，無需登入（FR-020）——`token` 接受 `scoreboard_token` 或
    `control_panel_token`（唯讀，research.md #3 之權限邊界不適用於此端點）。
    Errors: `LINK_NOT_FOUND`."""
    court, group, link_type, _owner_language = await court_service.get_court_by_token(
        session, token
    )
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
    """接受 `control_panel_token`，或該團已開啟 `scoreboard_scoring_enabled`
    時的 `scoreboard_token`（research.md #3 + 018-plan-then-start
    follow-up）。Errors: `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`。"""
    court, group, link_type, _owner_language = await court_service.get_court_by_token(
        session, token
    )
    if not _can_score_by_token(link_type, group):
        raise ApiError("LINK_NOT_FOUND", status_code=404)
    return await service.apply_score_delta(
        session, court, match_id, payload.side, payload.delta, source=link_type
    )


@router.post("/courts/by-token/{token}/matches/{match_id}/end", response_model=ScoreMutationResult)
async def end_match_by_token(
    token: uuid.UUID,
    match_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScoreMutationResult:
    """接受 `control_panel_token`，或該團已開啟 `scoreboard_scoring_enabled`
    時的 `scoreboard_token`（research.md #3 + 018-plan-then-start
    follow-up）。Errors: `LINK_NOT_FOUND`、`MATCH_NOT_FOUND`。"""
    court, group, link_type, _owner_language = await court_service.get_court_by_token(
        session, token
    )
    if not _can_score_by_token(link_type, group):
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
    return await service.apply_score_delta(
        session, court, match_id, payload.side, payload.delta, source="admin"
    )


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
