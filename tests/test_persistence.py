from __future__ import annotations

import pytest

from app.persistence import PostgresStateStore, StateStoreError


class FakeCursor:
    def __init__(self, rows=None, fail: bool = False) -> None:
        self.rows = list(rows or [])
        self.fail = fail
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError("database failure")
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


def build_store(monkeypatch, cursor: FakeCursor) -> PostgresStateStore:
    monkeypatch.setattr(
        "app.persistence.psycopg.connect",
        lambda *args, **kwargs: FakeConnection(cursor),
    )
    return PostgresStateStore("postgresql://example")


def test_initialization_creates_state_and_claim_tables(monkeypatch) -> None:
    cursor = FakeCursor()
    build_store(monkeypatch, cursor)

    statements = "\n".join(sql for sql, _ in cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS app_state" in statements
    assert "CREATE TABLE IF NOT EXISTS review_claims" in statements


def test_get_set_delete(monkeypatch) -> None:
    cursor = FakeCursor(rows=[("value-1",)])
    store = build_store(monkeypatch, cursor)

    assert store.get("key-1") == "value-1"
    store.set("key-1", "value-2")
    store.delete("key-1")

    statements = "\n".join(sql for sql, _ in cursor.executed)
    assert "SELECT value FROM app_state" in statements
    assert "INSERT INTO app_state" in statements
    assert "DELETE FROM app_state" in statements


def test_atomic_claim_complete_and_release(monkeypatch) -> None:
    cursor = FakeCursor(rows=[("review-key",), ("review-key",), ("review-key",)])
    store = build_store(monkeypatch, cursor)

    assert store.claim_review("review-key", "token-1", 900) is True
    assert store.complete_review("review-key", "token-1") is True
    assert store.release_review("review-key", "token-1") is True

    statements = "\n".join(sql for sql, _ in cursor.executed)
    assert "ON CONFLICT (key) DO UPDATE" in statements
    assert "status = 'completed'" in statements
    assert "DELETE FROM review_claims" in statements


def test_claim_returns_false_when_existing_claim_is_active(monkeypatch) -> None:
    cursor = FakeCursor(rows=[])
    store = build_store(monkeypatch, cursor)

    assert store.claim_review("review-key", "token-2", 900) is False


def test_connection_failure_raises_state_store_error(monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("app.persistence.psycopg.connect", fail_connect)

    with pytest.raises(StateStoreError, match="Unable to connect"):
        PostgresStateStore("postgresql://example")


def test_database_operation_failure_is_wrapped(monkeypatch) -> None:
    cursor = FakeCursor()
    store = build_store(monkeypatch, cursor)
    cursor.fail = True

    with pytest.raises(StateStoreError, match="Unable to claim review work"):
        store.claim_review("review-key", "token-1", 900)
