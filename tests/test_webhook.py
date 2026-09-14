import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from app.webhook_service import tracker

client = TestClient(app)


def signed_headers(secret: str, body: bytes, event: str, delivery: str) -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


def pr_payload(action: str = "opened", draft: bool = False) -> dict:
    return {
        "action": action,
        "repository": {"full_name": "Khumo-Hub/AI-PR-Reviewer-application"},
        "pull_request": {"number": 6, "draft": draft},
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
    calls: list[tuple[str, int]] = []

    def fake_worker(repository: str, pr_number: int) -> None:
        calls.append((repository, pr_number))

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setattr("app.main.run_review_and_create_draft", fake_worker)

    body = json.dumps(pr_payload(action="synchronize")).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "schedule-1"),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "review_scheduled"}
    assert calls == [("Khumo-Hub/AI-PR-Reviewer-application", 6)]


def test_duplicate_delivery_is_ignored(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b"{}"
    headers = signed_headers("secret", body, "ping", "duplicate-1")

    first = client.post("/webhooks/github", content=body, headers=headers)
    second = client.post("/webhooks/github", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == {"status": "duplicate_ignored"}


def test_malformed_pull_request_payload_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    body = b"not-json"
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers("secret", body, "pull_request", "bad-json-1"),
    )
    assert response.status_code == 400
