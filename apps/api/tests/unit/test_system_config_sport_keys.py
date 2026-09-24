"""043 T019: per-sport default group-name suffix and court name."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.system_config.service import get_default_court_name, get_default_group_name_suffix


async def test_badminton_and_no_sport_read_the_original_keys(db_session: AsyncSession) -> None:
    assert await get_default_group_name_suffix(db_session) == "的羽球團"
    assert await get_default_group_name_suffix(db_session, "badminton") == "的羽球團"
    assert await get_default_court_name(db_session, "badminton") == "球場一"


async def test_seeded_sport_reads_its_own_row(db_session: AsyncSession) -> None:
    assert await get_default_group_name_suffix(db_session, "billiards") == "的撞球團"
    assert await get_default_court_name(db_session, "billiards") == "球桌一"
    assert await get_default_court_name(db_session, "darts") == "靶台一"


async def test_custom_activities_share_the_other_row(db_session: AsyncSession) -> None:
    assert await get_default_group_name_suffix(db_session, "custom") == "的團"
    assert await get_default_court_name(db_session, "custom") == "場地一"


async def test_unseeded_sport_falls_back_to_the_original_key(db_session: AsyncSession) -> None:
    assert await get_default_group_name_suffix(db_session, "no_such_sport") == "的羽球團"
    assert await get_default_court_name(db_session, "no_such_sport") == "球場一"
