#!/usr/bin/env python3
"""Truncate every user-data table for a fresh-data reset.

`system_config` (shared settings) and `alembic_version` (migration state)
are deliberately left untouched — this resets user data only, not schema or
config. Run as a module from apps/api/ so both the `app` package import and
Settings' relative `.env` lookup resolve, same as `alembic`:

    python -m scripts.reset_data [--yes]
"""

import argparse
import asyncio
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

_DATA_TABLES = (
    "courts",
    "email_verification_tokens",
    "friend_requests",
    "group_invites",
    "groups",
    "match_participants",
    "matches",
    "members",
    "notifications",
    "pair_history",
    "partnerships",
    "password_reset_tokens",
    "roster_entries",
    "round_history",
    "score_events",
)


def _masked_database_url() -> str:
    parts = urlsplit(get_settings().database_url)
    if parts.password:
        netloc = parts.netloc.replace(parts.password, "***")
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts)


async def reset_data() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )
        # group_number_seq is a standalone sequence (not OWNED BY a column),
        # so RESTART IDENTITY above doesn't reset it — do it explicitly.
        await conn.execute(text("ALTER SEQUENCE group_number_seq RESTART WITH 100000"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    print(f"About to TRUNCATE {len(_DATA_TABLES)} tables on: {_masked_database_url()}")
    if not args.yes and input("Type 'yes' to continue: ") != "yes":
        print("Aborted.")
        return

    asyncio.run(reset_data())
    print("Done. system_config and alembic_version were left untouched.")


if __name__ == "__main__":
    main()
