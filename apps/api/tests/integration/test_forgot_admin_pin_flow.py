"""Integration test: member creates a group -> forgets the PIN -> resets it
without re-entering anything -> old admin session is fully invalidated
(FR-028~032). Ably delivery of `link.regenerated` itself is not asserted
here — no existing test in this suite asserts real Ably delivery either
(the test stack's `ABLY_API_KEY` is a dummy key), consistent with
`test_regenerate_pin.py`'s own precedent of only asserting the token/PIN
state transition, not the broadcast."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_full_forgot_admin_pin_flow(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    member = await register(db_session, "forgotpinflow@example.com", "abc12345")
    member.verification_status = "verified"
    member.nickname = "小李"
    await db_session.commit()

    login_response = await client.post(
        "/auth/login", json={"email": "forgotpinflow@example.com", "password": "abc12345"}
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    created = (
        await client.post(
            "/groups",
            json={
                "name": "Flow Forgot Pin",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "turnstile_token": valid_turnstile_token,
            },
            headers=headers,
        )
    ).json()
    original_admin_token = created["admin_token"]

    # Confirm the original token can view the admin page before we forget it.
    original_view = await client.get(
        f"/groups/{created['group_id']}/admin",
        headers={"Authorization": f"Bearer {original_admin_token}"},
    )
    assert original_view.status_code == 200

    forgot_response = await client.post(
        f"/groups/{created['group_id']}/forgot-admin-pin", headers=headers
    )
    assert forgot_response.status_code == 200
    new_admin_token = forgot_response.json()["admin_token"]
    assert new_admin_token != original_admin_token

    # New token lands directly on the admin page — no re-entry of the PIN.
    new_view = await client.get(
        f"/groups/{created['group_id']}/admin",
        headers={"Authorization": f"Bearer {new_admin_token}"},
    )
    assert new_view.status_code == 200

    # Old token is now invalid.
    stale_view = await client.get(
        f"/groups/{created['group_id']}/admin",
        headers={"Authorization": f"Bearer {original_admin_token}"},
    )
    assert stale_view.status_code == 401
