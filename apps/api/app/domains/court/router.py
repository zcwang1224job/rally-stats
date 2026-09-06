"""Court domain REST endpoints, per specs/002-court-management/contracts/courts-api.md."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ApiError
from app.domains.court import service
from app.domains.court.models import Court
from app.domains.court.schemas import (
    CourtByTokenResponse,
    CourtListResponse,
    CourtResponse,
    CreateCourtRequest,
    DeleteCourtResponse,
    RegenerateControlPanelLinkResponse,
    RegenerateLinkRequest,
    RegenerateScoreboardLinkResponse,
    RenameCourtRequest,
)
from app.domains.group.models import Group
from app.domains.group.security import require_admin
from app.domains.schedule.service import abandon_court_matches

router = APIRouter(tags=["courts"])


def _to_response(court: Court) -> CourtResponse:
    return CourtResponse(
        court_id=str(court.id),
        name=court.name,
        scoreboard_token=str(court.scoreboard_token),
        control_panel_token=str(court.control_panel_token),
        scoreboard_link_version=court.scoreboard_link_version,
        control_panel_link_version=court.control_panel_link_version,
        created_at=court.created_at,
    )


async def _admin_court(
    court_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Court:
    """Resolves the path's court_id and checks it belongs to the admin token's
    group — the court-scoped equivalent of the `group.id != group_id` guard
    used throughout the group router."""
    court = await service.get_court_by_id(session, court_id)
    if court.group_id != group.id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return court


@router.post("/groups/{group_id}/courts", response_model=CourtResponse, status_code=201)
async def create_court(
    group_id: uuid.UUID,
    payload: CreateCourtRequest,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtResponse:
    """Add a court to the group. Errors: `VALIDATION_ERROR`,
    `COURT_NAME_ALREADY_EXISTS`, `GROUP_DISBANDED`, `ADMIN_TOKEN_INVALID`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    court = await service.create_court(session, group, payload)
    return _to_response(court)


@router.get("/groups/{group_id}/courts", response_model=CourtListResponse)
async def list_courts(
    group_id: uuid.UUID,
    group: Annotated[Group, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtListResponse:
    """Active-only court list for the admin page's "場地設定" section.
    Errors: `ADMIN_TOKEN_INVALID`."""
    if group.id != group_id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    courts = await service.list_active_courts(session, group_id)
    responses = [_to_response(c) for c in courts]
    return CourtListResponse(courts=responses, active_court_count=len(responses))


@router.patch("/courts/{court_id}", response_model=CourtResponse)
async def rename_court(
    payload: RenameCourtRequest,
    court: Annotated[Court, Depends(_admin_court)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtResponse:
    """Rename a court (last-write-wins; see research.md #5 for why this has no
    dedicated optimistic-lock version). Errors: `VALIDATION_ERROR`,
    `COURT_NAME_ALREADY_EXISTS`, `COURT_DELETED`, `ADMIN_TOKEN_INVALID`."""
    updated = await service.rename_court(session, court, payload)
    return _to_response(updated)


@router.delete("/courts/{court_id}", response_model=DeleteCourtResponse)
async def delete_court(
    court: Annotated[Court, Depends(_admin_court)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeleteCourtResponse:
    """Soft-delete a court. NOT idempotent — deleting twice is an error.
    Errors: `COURT_DELETED`, `ADMIN_TOKEN_INVALID`."""
    had_active_match = await service.delete_court(
        session, court, abandon_unfinished_matches=abandon_court_matches
    )
    return DeleteCourtResponse(
        court_id=str(court.id), deleted=True, had_active_match=had_active_match
    )


@router.post(
    "/courts/{court_id}/regenerate-scoreboard-link",
    response_model=RegenerateScoreboardLinkResponse,
)
async def regenerate_scoreboard_link(
    payload: RegenerateLinkRequest,
    court: Annotated[Court, Depends(_admin_court)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateScoreboardLinkResponse:
    """Checks `deleted_at` BEFORE the version conflict check (spec FR-028).
    Errors: `COURT_DELETED`, `VERSION_CONFLICT`, `ADMIN_TOKEN_INVALID`."""
    updated = await service.regenerate_scoreboard_link(
        session, court.group_id, court, payload.expected_version
    )
    return RegenerateScoreboardLinkResponse(
        scoreboard_token=str(updated.scoreboard_token),
        scoreboard_link_version=updated.scoreboard_link_version,
    )


@router.post(
    "/courts/{court_id}/regenerate-control-panel-link",
    response_model=RegenerateControlPanelLinkResponse,
)
async def regenerate_control_panel_link(
    payload: RegenerateLinkRequest,
    court: Annotated[Court, Depends(_admin_court)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegenerateControlPanelLinkResponse:
    """Same guard ordering as the scoreboard-link sibling, independent version
    field (spec FR-036). Errors: `COURT_DELETED`, `VERSION_CONFLICT`,
    `ADMIN_TOKEN_INVALID`."""
    updated = await service.regenerate_control_panel_link(
        session, court.group_id, court, payload.expected_version
    )
    return RegenerateControlPanelLinkResponse(
        control_panel_token=str(updated.control_panel_token),
        control_panel_link_version=updated.control_panel_link_version,
    )


@router.get("/courts/by-token/{token}", response_model=CourtByTokenResponse)
async def get_court_by_token(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourtByTokenResponse:
    """Public, unauthenticated. Doubles as both scoreboard/control-panel page
    bootstrap and the 5-minute heartbeat poll (research.md #4). Errors:
    `LINK_NOT_FOUND`."""
    court, group, link_type = await service.get_court_by_token(session, token)
    link_version = (
        court.scoreboard_link_version
        if link_type == "scoreboard"
        else court.control_panel_link_version
    )
    return CourtByTokenResponse(
        court_id=str(court.id),
        group_id=str(group.id),
        name=court.name,
        link_type=link_type,
        link_version=link_version,
        deleted=court.deleted_at is not None,
        group_disbanded=group.status == "disbanded",
    )
