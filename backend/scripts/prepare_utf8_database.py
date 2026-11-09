"""Explicit, non-destructive preparation. No config edits or data copies.

Dry run: python -m backend.scripts.prepare_utf8_database
Create:  python -m backend.scripts.prepare_utf8_database --create
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.settings import Settings


def create_statement(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
        raise ValueError("invalid_database_name")
    return (
        f"CREATE DATABASE \"{name}\" WITH TEMPLATE template0 ENCODING 'UTF8' "
        "LOCALE_PROVIDER libc LC_COLLATE 'C' LC_CTYPE 'C'"
    )


async def prepare(name: str, *, create: bool = False) -> dict:
    statement = create_statement(name)
    settings = Settings()
    if not settings.database_url.startswith("postgresql+asyncpg:"):
        raise ValueError("postgresql_required")
    engine = create_async_engine(
        settings.database_url,
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    try:
        async with engine.connect() as connection:
            source = await connection.scalar(text("SELECT current_database()"))
            encoding = await connection.scalar(text("SHOW server_encoding"))
            exists = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)"),
                {"name": name},
            )
            allowed = await connection.scalar(
                text("SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user")
            )
            if source == name:
                raise ValueError("target_must_differ_from_source")
            report = {
                "source_database": source,
                "source_encoding": encoding,
                "target_database": name,
                "target_exists": exists,
                "can_create_database": allowed,
                "dry_run": not create,
                "created": False,
                "source_unchanged": True,
                "data_copied": False,
                "config_changed": False,
            }
            if create:
                if exists:
                    raise ValueError("target_database_exists")
                if not allowed:
                    raise ValueError("database_creation_not_permitted")
                await connection.exec_driver_sql(statement)
                actual = await connection.scalar(
                    text(
                        "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname=:name"
                    ),
                    {"name": name},
                )
                report.update(created=True, target_encoding=actual)
                if actual != "UTF8":
                    raise ValueError("target_encoding_not_utf8")
            return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="repospec_viewer_utf8")
    parser.add_argument("--create", action="store_true", help="Create a new empty database")
    arguments = parser.parse_args()
    try:
        result = asyncio.run(prepare(arguments.name, create=arguments.create))
    except Exception as exc:
        reasons = {
            "invalid_database_name",
            "postgresql_required",
            "target_must_differ_from_source",
            "target_database_exists",
            "database_creation_not_permitted",
            "target_encoding_not_utf8",
        }
        reason = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc) in reasons
            else "preparation_failed"
        )
        print(
            json.dumps({"status": "failed", "reason": reason, "classification": type(exc).__name__})
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
