"""Unit test: user_number format (excludes confusing characters) and
collision retry (FR-018/019, research.md #8)."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.security import (
    _USER_NUMBER_ALPHABET,
    generate_unique_user_number,
    hash_password,
)


async def _make_taken_member(session: AsyncSession, email: str, user_number: str) -> Member:
    member = Member(email=email, password_hash=hash_password("abc12345"), user_number=user_number)
    session.add(member)
    await session.commit()
    return member


def test_alphabet_excludes_confusing_characters() -> None:
    for confusing in "0O1Il":
        assert confusing not in _USER_NUMBER_ALPHABET


@pytest.mark.asyncio
async def test_generates_8_char_number_from_alphabet(db_session: AsyncSession) -> None:
    number = await generate_unique_user_number(db_session)
    assert len(number) == 8
    assert all(c in _USER_NUMBER_ALPHABET for c in number)


@pytest.mark.asyncio
async def test_retries_on_collision(db_session: AsyncSession) -> None:
    await _make_taken_member(db_session, "taken@example.com", "AAAAAAAA")

    candidates = iter(["AAAAAAAA", "AAAAAAAA", "BBBBBBBB"])
    with patch(
        "app.domains.member.security._generate_user_number_candidate",
        side_effect=lambda: next(candidates),
    ):
        number = await generate_unique_user_number(db_session)
    assert number == "BBBBBBBB"


@pytest.mark.asyncio
async def test_collision_check_is_case_insensitive(db_session: AsyncSession) -> None:
    await _make_taken_member(db_session, "taken2@example.com", "aB3dEfGh")

    candidates = iter(["AB3DEFGH", "cD4eFgHi"])
    with patch(
        "app.domains.member.security._generate_user_number_candidate",
        side_effect=lambda: next(candidates),
    ):
        number = await generate_unique_user_number(db_session)
    assert number == "cD4eFgHi"


@pytest.mark.asyncio
async def test_raises_after_max_attempts_all_colliding(db_session: AsyncSession) -> None:
    await _make_taken_member(db_session, "taken3@example.com", "ZZZZZZZZ")

    with patch(
        "app.domains.member.security._generate_user_number_candidate",
        return_value="ZZZZZZZZ",
    ), pytest.raises(RuntimeError):
        await generate_unique_user_number(db_session)
