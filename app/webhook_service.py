from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import HTTPException


logger = logging.getLogger(__name__)

SUPPORTED_PULL_REQUEST_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}


class DeliveryTracker:
    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._seen: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = Lock()

    def register(self, delivery_id: str) -> bool:
        with self._lock:
            if delivery_id in self._seen:
                return False
            self._seen.add(delivery_id)
            self._order.append(delivery_id)
            while len(self._order) > self.max_entries:
                oldest = self._order.popleft()
                self._seen.discard(oldest)
            return True

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()
            self._order.clear()


class ReviewTracker:
    """Suppress duplicate reviews for the same repository, PR and head commit.

    In-flight keys are memory-only. Only completed keys are persisted, so a process
    crash before completion cannot permanently block a later GitHub retry.
    """

    def __init__(
        self,
        max_entries: int = 1000,
        state_path: str | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.state_path = state_path
        self._seen: set[str] = set()
        self._completed: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = Lock()
        self._load()

    @staticmethod
    def key(repository: str, pr_number: int, head_sha: str) -> str:
        return f"{repository.lower()}:{pr_number}:{head_sha.lower()}"

    def _load(self) -> None:
        if not self.state_path:
            return
        path = Path(self.state_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("completed_review_keys", []) if isinstance(data, dict) else []
            for item in entries[-self.max_entries :]:
                if isinstance(item, str) and item not in self._seen:
                    self._seen.add(item)
                    self._completed.add(item)
                    self._order.append(item)
        except (OSError, json.JSONDecodeError):
            # Idempotency state is recoverable; a corrupt optional cache must not stop startup.
            self._seen.clear()
            self._completed.clear()
            self._order.clear()

    def _persist_locked(self) -> None:
        if not self.state_path:
            return
        path = Path(self.state_path)
        completed_order = [item for item in self._order if item in self._completed]
        payload = json.dumps({"completed_review_keys": completed_order})
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temp_name = temporary.name
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        except OSError:
            logger.exception("Unable to persist webhook review idempotency state")

    def _trim_locked(self) -> None:
        while len(self._order) > self.max_entries:
            oldest = self._order.popleft()
            self._seen.discard(oldest)
            self._completed.discard(oldest)

    def register(self, repository: str, pr_number: int, head_sha: str) -> bool:
        key = self.key(repository, pr_number, head_sha)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._order.append(key)
            self._trim_locked()
            return True

    def mark_completed(self, repository: str, pr_number: int, head_sha: str) -> None:
        key = self.key(repository, pr_number, head_sha)
        with self._lock:
            if key not in self._seen:
                self._seen.add(key)
                self._order.append(key)
                self._trim_locked()
            self._completed.add(key)
            self._persist_locked()

    def discard(self, repository: str, pr_number: int, head_sha: str) -> None:
        key = self.key(repository, pr_number, head_sha)
        with self._lock:
            if key not in self._seen and key not in self._completed:
                return
            self._seen.discard(key)
            self._completed.discard(key)
            self._order = deque(item for item in self._order if item != key)
            self._persist_locked()

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()
            self._completed.clear()
            self._order.clear()
            self._persist_locked()


tracker = DeliveryTracker()
review_tracker = ReviewTracker(state_path=os.getenv("REVIEW_STATE_PATH"))


def verify_github_signature(body: bytes, signature: str | None) -> None:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="GitHub webhook secret is not configured")
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid or missing GitHub webhook signature")

    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing GitHub webhook signature")


def parse_webhook_payload(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid GitHub webhook payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid GitHub webhook payload")
    return payload
