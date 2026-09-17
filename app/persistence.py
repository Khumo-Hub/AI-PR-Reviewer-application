from __future__ import annotations

import os
from typing import Protocol

import psycopg


class StateStoreError(Exception):
    pass


class StateStore(Protocol):
    def get(self, key: str) -> str | None:
        ...

    def set(self, key: str, value: str) -> None:
        ...

    def delete(self, key: str) -> None:
        ...


class PostgresStateStore:
    """Small key/value state store backed by Postgres.

    The table is created automatically so a fresh hosted Postgres database can be
    connected by setting only DATABASE_URL.
    """

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise StateStoreError("Database URL is not configured")
        self.database_url = database_url
        self._ensure_table()

    def _connect(self):
        try:
            return psycopg.connect(self.database_url, autocommit=True)
        except Exception as exc:
            raise StateStoreError("Unable to connect to persistence database") from exc

    def _ensure_table(self) -> None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS app_state (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to initialize persistence database") from exc

    def get(self, key: str) -> str | None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT value FROM app_state WHERE key = %s", (key,))
                    row = cursor.fetchone()
                    return row[0] if row else None
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to read persistence state") from exc

    def set(self, key: str, value: str) -> None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO app_state (key, value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (key)
                        DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                        """,
                        (key, value),
                    )
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to write persistence state") from exc

    def delete(self, key: str) -> None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM app_state WHERE key = %s", (key,))
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to delete persistence state") from exc


def build_state_store(database_url: str | None = None) -> StateStore | None:
    resolved = database_url or os.getenv("DATABASE_URL")
    if not resolved:
        return None
    return PostgresStateStore(resolved)
