"""Shared test setup for the group_invite domain's unit tests: a verified
Member, a Member-created Group (via the real create_group() service, so
created_by_member_id/RosterEntry/current_member_count all end up in their
normal post-creation state), and an accepted friendship between two
Members."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import create_friend_request, respond_friend_request
from app.domains.group.models import Group
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group
from app.domains.member.models import Member
from app.domains.member.service import register


async def verified_member(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    await session.refresh(member)
    return member


async def member_created_group(
    session: AsyncSession, creator: Member, **overrides: object
) -> Group:
    defaults: dict[str, object] = {
        "name": "Group Invite Test",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "turnstile_token": "unused",
    }
    defaults.update(overrides)
    payload = CreateGroupRequest(**defaults)
    group, _roster_entry, _admin_pin, _guest_token = await create_group(
        session, payload, member=creator
    )
    return group


async def become_friends(session: AsyncSession, a: Member, b: Member) -> str:
    created = await create_friend_request(session, a.id, b.user_number)
    await respond_friend_request(session, b.id, uuid.UUID(created.friend_request_id), accept=True)
    return created.friend_request_id
