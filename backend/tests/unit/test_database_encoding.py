from types import SimpleNamespace

import pytest

from backend.app.generation.store import GenerationDatabaseEncodingError, GenerationStore
from backend.scripts import prepare_utf8_database as preparation


@pytest.mark.parametrize(
    "dialect,encoding,accepted",
    [
        ("postgresql", "UTF8", True),
        ("postgresql", "EUC_JP", False),
        ("postgresql", "SQL_ASCII", False),
        ("postgresql", None, False),
        ("sqlite", None, True),
        ("unknown", "UTF8", False),
    ],
)
async def test_generation_storage_encoding(dialect, encoding, accepted):
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name=dialect))

        async def scalar(self, statement):
            calls.append(str(statement))
            return encoding

    store = GenerationStore(Session)
    if accepted:
        await store.require_utf8()
    else:
        with pytest.raises(GenerationDatabaseEncodingError):
            await store.require_utf8()
    assert calls == (["SHOW server_encoding"] if dialect == "postgresql" else [])


@pytest.mark.parametrize("name", ["", "a;DROP DATABASE old", "UPPER", "a" * 64, "a-b", 'x"'])
def test_preparation_rejects_unsafe_identifiers(name):
    with pytest.raises(ValueError, match="invalid_database_name"):
        preparation.create_statement(name)


@pytest.mark.parametrize(
    "create,exists,allowed,reason",
    [
        (False, False, True, None),
        (True, False, True, None),
        (True, True, True, "target_database_exists"),
        (True, False, False, "database_creation_not_permitted"),
    ],
)
async def test_database_preparation_is_explicit_and_never_replaces_source(
    monkeypatch,
    create,
    exists,
    allowed,
    reason,
):
    writes = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalar(self, statement, values=None):
            sql = str(statement)
            if "current_database" in sql:
                return "legacy_fixture"
            if "SHOW server_encoding" in sql:
                return "EUC_JP"
            if "EXISTS" in sql:
                return exists
            if "rolcreatedb" in sql:
                return allowed
            if "pg_encoding_to_char" in sql:
                return "UTF8"
            raise AssertionError("unexpected query")

        async def exec_driver_sql(self, statement):
            writes.append(statement)

    class Engine:
        def connect(self):
            return Connection()

        async def dispose(self):
            pass

    monkeypatch.setattr(
        preparation,
        "Settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://user:sensitive@host/legacy_fixture"
        ),
    )
    monkeypatch.setattr(preparation, "create_async_engine", lambda *args, **kwargs: Engine())
    if reason:
        with pytest.raises(ValueError, match=reason):
            await preparation.prepare("new_utf8", create=create)
    else:
        report = await preparation.prepare("new_utf8", create=create)
        assert report["created"] is create
        assert report["source_unchanged"] and not report["data_copied"]
        assert "sensitive" not in str(report)
    assert len(writes) == (1 if create and not reason else 0)
    assert all(
        "DROP" not in sql
        and "ALTER" not in sql
        and "legacy_fixture" not in sql
        and "ENCODING 'UTF8'" in sql
        and "template0" in sql
        for sql in writes
    )


def test_preparation_never_prints_exception_details(monkeypatch, capsys):
    async def fail(*args, **kwargs):
        raise RuntimeError("never-log-sensitive")

    monkeypatch.setattr(preparation, "prepare", fail)
    monkeypatch.setattr("sys.argv", ["prepare"])
    assert preparation.main() == 1
    assert "never-log-sensitive" not in capsys.readouterr().out
