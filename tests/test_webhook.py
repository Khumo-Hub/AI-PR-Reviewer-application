import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.github_service import GitHubServiceError
from app.main import app, run_review_and_create_draft
from app.webhook_service import ReviewTracker, review_tracker, tracker

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_trackers() -> None:
    tracker.clear()
    review_tracker.clear()


def signed_headers(secret: str, body: bytes, event: str, delivery: str) -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


def pr_payload(
    action: str = "opened",
    draft: bool = False,
    head_sha: str = "abc123",
) -> dict:
    return {
        "action": action,
        "repository": {"full_name": "Khumo-Hub/AI-PR-Reviewer-application"},
        "pull_request": {
            "number": 6,
            "draft": draft,
            "head": {"sha": head_sha},
        },
    }


def test_missing_webhook_secret_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    response = client.post("/webhooks/github", content=b"{}")
    assert response.status_code == 503


def test_invalid_signature_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    response = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={
            "X-Hub-Signature-256": "sha256=bad",
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "invalid-signature",
        },
    )
    assert response.status_code == 401


def test_ping_returns_pong(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = json.dumps({"zen": "Keep it logically awesome."}).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "ping", "ping-1"),
    )
    assert response.status_code == 202
    assert response.json() == {"status": "pong"}


def test_irrelevant_event_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b"{}"
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "issues", "issues-1"),
    )
    assert response.status_code == 202
    assert response.json() == {"status": "event_ignored"}


def test_irrelevant_pull_request_action_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = json.dumps(pr_payload(action="closed")).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "closed-1"),
    )
    assert response.status_code == 202
    assert response.json() == {"status": "action_ignored"}


def test_draft_pull_request_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    body = json.dumps(pr_payload(draft=True)).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "draft-1"),
    )
    assert response.status_code == 202
    assert response.json() == {"status": "draft_ignored"}


def test_repository_allowlist_applies_to_webhook(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("ALLOWED_GITHUB_REPOSITORIES", "other/repo")
    body = json.dumps(pr_payload()).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "forbidden-1"),
    )
    assert response.status_code == 403


def test_supported_pull_request_schedules_review(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    def fake_worker(repository: str, pr_number: int, head_sha: str) -> None:
        calls.append((repository, pr_number, head_sha))

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setattr("app.main.run_review_and_create_draft", fake_worker)

    body = json.dumps(pr_payload(action="synchronize", head_sha="sha-1")).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "schedule-1"),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "review_scheduled"}
    assert calls == [("Khumo-Hub/AI-PR-Reviewer-application", 6, "sha-1")]


def test_duplicate_delivery_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b"{}"
    headers = signed_headers("secret", body, "ping", "duplicate-1")

    first = client.post("/webhooks/github", content=body, headers=headers)
    second = client.post("/webhooks/github", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == {"status": "duplicate_ignored"}


def test_same_pr_head_is_not_reviewed_twice(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    def fake_worker(repository: str, pr_number: int, head_sha: str) -> None:
        calls.append((repository, pr_number, head_sha))

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setattr("app.main.run_review_and_create_draft", fake_worker)

    body = json.dumps(pr_payload(head_sha="same-sha")).encode()
    first = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "delivery-1"),
    )
    second = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "delivery-2"),
    )

    assert first.json() == {"status": "review_scheduled"}
    assert second.json() == {"status": "review_already_scheduled"}
    assert calls == [("Khumo-Hub/AI-PR-Reviewer-application", 6, "same-sha")]


def test_new_head_sha_schedules_a_new_review(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []

    def fake_worker(repository: str, pr_number: int, head_sha: str) -> None:
        calls.append((repository, pr_number, head_sha))

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setattr("app.main.run_review_and_create_draft", fake_worker)

    first_body = json.dumps(pr_payload(head_sha="sha-1")).encode()
    second_body = json.dumps(pr_payload(action="synchronize", head_sha="sha-2")).encode()

    first = client.post(
        "/webhooks/github",
        content=first_body,
        headers=signed_headers("secret", first_body, "pull_request", "head-1"),
    )
    second = client.post(
        "/webhooks/github",
        content=second_body,
        headers=signed_headers("secret", second_body, "pull_request", "head-2"),
    )

    assert first.json() == {"status": "review_scheduled"}
    assert second.json() == {"status": "review_scheduled"}
    assert calls == [
        ("Khumo-Hub/AI-PR-Reviewer-application", 6, "sha-1"),
        ("Khumo-Hub/AI-PR-Reviewer-application", 6, "sha-2"),
    ]


def test_missing_head_sha_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    payload = pr_payload()
    payload["pull_request"].pop("head")
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "missing-head"),
    )

    assert response.status_code == 400


def test_stale_webhook_is_skipped_before_ai(monkeypatch) -> None:
    repository = "Khumo-Hub/AI-PR-Reviewer-application"
    review_tracker.register(repository, 6, "old-sha")

    class FakeGitHubService:
        def get_pull_request_review_input(self, repo: str, number: int) -> dict:
            return {
                "repository": repo,
                "pull_request": {"number": number, "head_sha": "new-sha"},
                "diff": "",
            }

        def close(self) -> None:
            pass

    def unexpected_ai_service():
        raise AssertionError("AI service must not run for stale webhook work")

    monkeypatch.setattr("app.main.GitHubService", FakeGitHubService)
    monkeypatch.setattr("app.main.AIReviewService", unexpected_ai_service)

    run_review_and_create_draft(repository, 6, "old-sha")

    assert review_tracker.register(repository, 6, "old-sha") is False


def test_failed_worker_releases_review_key_for_retry(monkeypatch) -> None:
    repository = "Khumo-Hub/AI-PR-Reviewer-application"
    review_tracker.register(repository, 6, "retry-sha")

    class FailingGitHubService:
        def get_pull_request_review_input(self, repo: str, number: int) -> dict:
            raise GitHubServiceError(502, "temporary failure")

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.main.GitHubService", FailingGitHubService)

    run_review_and_create_draft(repository, 6, "retry-sha")

    assert review_tracker.register(repository, 6, "retry-sha") is True


def test_inflight_review_is_not_persisted_across_recreation(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    first = ReviewTracker(state_path=str(state_path))
    assert first.register("owner/repo", 9, "abc123") is True

    second = ReviewTracker(state_path=str(state_path))
    assert second.register("owner/repo", 9, "abc123") is True


def test_completed_review_tracker_survives_recreation(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    first = ReviewTracker(state_path=str(state_path))
    assert first.register("Owner/Repo", 9, "ABC123") is True
    first.mark_completed("Owner/Repo", 9, "ABC123")

    second = ReviewTracker(state_path=str(state_path))
    assert second.register("owner/repo", 9, "abc123") is False


def test_persistent_review_tracker_discard_allows_retry(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    first = ReviewTracker(state_path=str(state_path))
    assert first.register("owner/repo", 9, "abc123") is True
    first.mark_completed("owner/repo", 9, "abc123")
    first.discard("owner/repo", 9, "abc123")

    second = ReviewTracker(state_path=str(state_path))
    assert second.register("owner/repo", 9, "abc123") is True


def test_malformed_pull_request_payload_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b"not-json"
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "bad-json-1"),
    )
    assert response.status_code == 400
