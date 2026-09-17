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

    def claim_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        ...

    def complete_review(self, key: str, claim_token: str) -> bool:
        ...

    def release_review(self, key: str, claim_token: str) -> bool:
        ...

    def clear_reviews(self) -> None:
        ...


class PostgresStateStore:
    """Small persistent state store backed by Postgres.

    Microsoft OAuth state uses the app_state key/value table. Review idempotency
    uses review_claims so a PR/head can be claimed atomically across processes.
    """

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise StateStoreError("Database URL is not configured")
        self.database_url = database_url
        self._ensure_tables()

    def _connect(self):
        try:
            return psycopg.connect(self.database_url, autocommit=True)
        except Exception as exc:
            raise StateStoreError("Unable to connect to persistence database") from exc

    def _ensure_tables(self) -> None:
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
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS review_claims (
                            key TEXT PRIMARY KEY,
                            status TEXT NOT NULL,
                            claim_token TEXT NOT NULL,
                            lease_expires_at TIMESTAMPTZ,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            CONSTRAINT review_claims_status_check
                                CHECK (status IN ('in_progress', 'completed'))
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

    def claim_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        if lease_seconds < 1:
            raise StateStoreError("Review claim lease must be positive")
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO review_claims (
                            key, status, claim_token, lease_expires_at, updated_at
                        )
                        VALUES (
                            %s,
                            'in_progress',
                            %s,
                            NOW() + (%s * INTERVAL '1 second'),
                            NOW()
                        )
                        ON CONFLICT (key) DO UPDATE
                        SET status = 'in_progress',
                            claim_token = EXCLUDED.claim_token,
                            lease_expires_at = EXCLUDED.lease_expires_at,
                            updated_at = NOW()
                        WHERE review_claims.status <> 'completed'
                          AND (
                              review_claims.lease_expires_at IS NULL
                              OR review_claims.lease_expires_at <= NOW()
                          )
                        RETURNING key
                        """,
                        (key, claim_token, lease_seconds),
                    )
                    return cursor.fetchone() is not None
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to claim review work") from exc

    def complete_review(self, key: str, claim_token: str) -> bool:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE review_claims
                        SET status = 'completed',
                            lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE key = %s
                          AND claim_token = %s
                          AND status = 'in_progress'
                        RETURNING key
                        """,
                        (key, claim_token),
                    )
                    return cursor.fetchone() is not None
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to complete review claim") from exc

    def release_review(self, key: str, claim_token: str) -> bool:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM review_claims
                        WHERE key = %s
                          AND claim_token = %s
                          AND status = 'in_progress'
                        RETURNING key
                        """,
                        (key, claim_token),
                    )
                    return cursor.fetchone() is not None
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to release review claim") from exc

    def clear_reviews(self) -> None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM review_claims")
        except StateStoreError:
            raise
        except Exception as exc:
            raise StateStoreError("Unable to clear review claims") from exc


def build_state_store(database_url: str | None = None) -> StateStore | None:
    resolved = database_url or os.getenv("DATABASE_URL")
    if not resolved:
        return None
    return PostgresStateStore(resolved)
