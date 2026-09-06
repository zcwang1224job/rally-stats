"""Shared pytest fixtures: a real Postgres test database (migrated once per
session, transaction-rolled-back per test) and an httpx AsyncClient wired to
the FastAPI app with the DB dependency overridden to use that transaction.

Uses a real PostgreSQL test database rather than SQLite, because 001 relies
on Postgres-specific features (BYTEA, TIMESTAMPTZ, SEQUENCE, partial unique
indexes) that SQLite cannot faithfully emulate.
"""

import os
import subprocess
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "postgresql+asyncpg://rally:rally_dev@localhost:5432/rally_stats_test"

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
os.environ.setdefault("TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA")
os.environ.setdefault(
    "PASSWORD_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
)
os.environ.setdefault("ABLY_API_KEY", "dummy.test:key")


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db() -> None:
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    api_dir = os.path.dirname(os.path.dirname(__file__))
    subprocess.run(["alembic", "downgrade", "base"], cwd=api_dir, env=env, check=True)
    subprocess.run(["alembic", "upgrade", "head"], cwd=api_dir, env=env, check=True)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        # Service-layer code calls session.commit() internally, so we can't
        # rely on a rollback here to undo already-committed writes — truncate
        # everything the test may have written instead, keeping the schema
        # (and system_config seed data). We DO still rollback first, purely
        # to discard any uncommitted in-memory ORM mutations a test may have
        # left dirty (e.g. a service function that mutates an attribute then
        # raises before its own commit) — otherwise the TRUNCATE's implicit
        # autoflush tries to UPDATE a row that may already be gone, raising
        # StaleDataError during teardown instead of the test's real outcome.
        await session.rollback()
        from sqlalchemy import text

        await session.execute(
            text(
                "TRUNCATE TABLE match_participants, matches, pair_history, partnerships, "
                "round_history, roster_entries, courts, groups, members RESTART IDENTITY CASCADE"
            )
        )
        await session.execute(text("ALTER SEQUENCE group_number_seq RESTART WITH 100000"))
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.core.db import get_session
    from app.core.rate_limit import limiter
    from app.main import app

    # slowapi's Limiter keeps its per-IP counters in in-process memory for
    # the lifetime of the Python process (not per-request/per-test) — every
    # test hitting `client` shares the same 127.0.0.1 bucket. Without
    # resetting here, running the full suite together (rather than one file
    # at a time) accumulates enough `/auth/login`/`/auth/forgot-password`/
    # `/members/search` calls across unrelated tests to trip the 20/minute
    # cap on tests that have nothing to do with rate limiting themselves.
    limiter.reset()

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def valid_turnstile_token() -> str:
    # The 1x00000000000000000000AA Turnstile site/secret pair always passes.
    return "test-token"
