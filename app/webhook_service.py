from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import deque
from threading import Lock
from typing import Any

from fastapi import HTTPException


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
    """Suppress duplicate reviews for the same repository, PR and head commit."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._seen: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = Lock()

    @staticmethod
    def key(repository: str, pr_number: int, head_sha: str) -> str:
        return f"{repository.lower()}:{pr_number}:{head_sha.lower()}"

    def register(self, repository: str, pr_number: int, head_sha: str) -> bool:
        key = self.key(repository, pr_number, head_sha)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._order.append(key)
            while len(self._order) > self.max_entries:
                oldest = self._order.popleft()
                self._seen.discard(oldest)
            return True

    def discard(self, repository: str, pr_number: int, head_sha: str) -> None:
        key = self.key(repository, pr_number, head_sha)
        with self._lock:
            self._seen.discard(key)

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()
            self._order.clear()


tracker = DeliveryTracker()
review_tracker = ReviewTracker()


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
