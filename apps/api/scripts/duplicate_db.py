#!/usr/bin/env python3
"""Clone a database within the same local Postgres server via
`CREATE DATABASE ... TEMPLATE` — a fast local snapshot/backup, not a
cross-host dump (use pg_dump/pg_restore for that). Run as a module from
apps/api/ so Settings' relative `.env` lookup resolves, same as `alembic`:

    python -m scripts.duplicate_db --target rally_stats_backup
    python -m scripts.duplicate_db --target rally_stats_backup --source rally_stats --force
"""

import argparse
import asyncio
import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_ident(name: str, label: str) -> None:
    if not _IDENT_RE.match(name):
        raise SystemExit(
            f"{label} {name!r} isn't a safe Postgres identifier "
            "(letters/digits/underscore, can't start with a digit)"
        )


def _maintenance_url_and_default_source() -> tuple[str, str]:
    """Postgres refuses CREATE/DROP DATABASE on the database you're
    connected to, and TEMPLATE requires the template to have zero other
    connections — so this always connects to the `postgres` system database
    instead, never the source or target."""
    parts = urlsplit(get_settings().database_url)
    default_source = parts.path.lstrip("/")
    maintenance_url = urlunsplit(parts._replace(path="/postgres"))
    return maintenance_url, default_source


async def _terminate_connections(conn, dbname: str) -> None:
    await conn.execute(
        text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :dbname AND pid <> pg_backend_pid()"
        ),
        {"dbname": dbname},
    )


async def duplicate_db(target: str, source: str, maintenance_url: str, force: bool) -> None:
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await _terminate_connections(conn, source)

            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"), {"dbname": target}
                )
            ).scalar_one_or_none()
            if exists:
                if not force:
                    raise SystemExit(
                        f"Database {target!r} already exists — pass --force to overwrite it."
                    )
                await _terminate_connections(conn, target)
                await conn.execute(text(f'DROP DATABASE "{target}"'))

            await conn.execute(text(f'CREATE DATABASE "{target}" TEMPLATE "{source}"'))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="name of the new database to create")
    parser.add_argument(
        "--source", default=None, help="database to clone from (default: DATABASE_URL's database)"
    )
    parser.add_argument(
        "--force", action="store_true", help="drop --target first if it already exists"
    )
    args = parser.parse_args()

    maintenance_url, default_source = _maintenance_url_and_default_source()
    source = args.source or default_source
    _validate_ident(source, "--source")
    _validate_ident(args.target, "--target")

    print(f"Cloning {source!r} -> {args.target!r} ...")
    asyncio.run(duplicate_db(args.target, source, maintenance_url, args.force))
    print("Done.")


if __name__ == "__main__":
    main()
