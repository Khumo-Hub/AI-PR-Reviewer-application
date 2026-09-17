from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from app.persistence import StateStoreError
from app.webhook_service import ReviewTracker, tracker


class FakeAtomicStore:
    def __init__(self) -> None:
        self.claims: dict[str, tuple[str, str]] = {}
        self.fail_claim = False
        self.fail_renew = False
        self.prune_calls: list[int] = []

    def get(self, key: str):
        return None

    def set(self, key: str, value: str) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def claim_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        if self.fail_claim:
            raise StateStoreError("database unavailable")
        if key in self.claims:
            return False
        self.claims[key] = ("in_progress", claim_token)
        return True

    def renew_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        if self.fail_renew:
            raise StateStoreError("database unavailable")
        return self.claims.get(key) == ("in_progress", claim_token)

    def complete_review(self, key: str, claim_token: str) -> bool:
        current = self.claims.get(key)
        if current != ("in_progress", claim_token):
            return False
        self.claims[key] = ("completed", claim_token)
        return True

    def release_review(self, key: str, claim_token: str) -> bool:
        current = self.claims.get(key)
        if current != ("in_progress", claim_token):
            return False
        del self.claims[key]
        return True

    def prune_completed_reviews(self, max_entries: int) -> None:
        self.prune_calls.append(max_entries)
        completed = [
            key for key, (status, _) in self.claims.items() if status == "completed"
        ]
        for key in completed[:-max_entries]:
            del self.claims[key]

    def clear_reviews(self) -> None:
        self.claims.clear()


def test_two_tracker_instances_cannot_claim_same_review() -> None:
    store = FakeAtomicStore()
    first = ReviewTracker(state_store=store)
    second = ReviewTracker(state_store=store)

    assert first.register("owner/repo", 7, "abc123") is True
    assert second.register("owner/repo", 7, "abc123") is False


def test_active_claim_can_be_renewed() -> None:
    store = FakeAtomicStore()
    tracker_instance = ReviewTracker(state_store=store)

    assert tracker_instance.register("owner/repo", 7, "abc123") is True
    assert tracker_instance.renew("owner/repo", 7, "abc123") is True


def test_lost_claim_is_detected_before_external_work() -> None:
    store = FakeAtomicStore()
    tracker_instance = ReviewTracker(state_store=store)

    assert tracker_instance.register("owner/repo", 7, "abc123") is True
    key = ReviewTracker.key("owner/repo", 7, "abc123")
    store.claims[key] = ("in_progress", "other-worker-token")

    assert tracker_instance.renew("owner/repo", 7, "abc123") is False


def test_completed_database_claim_stays_deduplicated_and_is_pruned() -> None:
    store = FakeAtomicStore()
    first = ReviewTracker(state_store=store, max_entries=3)
    second = ReviewTracker(state_store=store, max_entries=3)

    assert first.register("owner/repo", 7, "abc123") is True
    first.mark_completed("owner/repo", 7, "abc123")
    assert store.prune_calls == [3]
    assert second.register("owner/repo", 7, "abc123") is False


def test_released_database_claim_can_be_retried() -> None:
    store = FakeAtomicStore()
    first = ReviewTracker(state_store=store)
    second = ReviewTracker(state_store=store)

    assert first.register("owner/repo", 7, "abc123") is True
    first.discard("owner/repo", 7, "abc123")
    assert second.register("owner/repo", 7, "abc123") is True


def test_webhook_fails_closed_when_persistence_claim_fails(monkeypatch) -> None:
    client = TestClient(app)
    tracker.clear()
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )

    def fail_register(repository: str, pr_number: int, head_sha: str) -> bool:
        raise StateStoreError("database unavailable")

    monkeypatch.setattr("app.main.review_tracker.register", fail_register)

    payload = {
        "action": "synchronize",
        "repository": {"full_name": "Khumo-Hub/AI-PR-Reviewer-application"},
        "pull_request": {
            "number": 13,
            "draft": False,
            "head": {"sha": "database-failure-sha"},
        },
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "database-failure-delivery",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Review persistence is temporarily unavailable"}
