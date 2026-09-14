from fastapi.testclient import TestClient

from app.ai_reviewer import AIReviewResult
from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "AI PR Reviewer is running"}


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pull_request_endpoint(monkeypatch) -> None:
    class FakeGitHubService:
        def get_pull_request_review_input(self, repository: str, number: int) -> dict:
            return {
                "repository": repository,
                "pull_request": {"number": number, "title": "Example PR"},
                "diff": "diff --git a/app/main.py b/app/main.py",
            }

        def close(self) -> None:
            pass

    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setattr("app.main.GitHubService", FakeGitHubService)

    response = client.get(
        "/github/pull-requests/Khumo-Hub/AI-PR-Reviewer-application/1"
    )

    assert response.status_code == 200
    assert response.json()["repository"] == "Khumo-Hub/AI-PR-Reviewer-application"
    assert response.json()["pull_request"]["number"] == 1


def test_ai_review_endpoint(monkeypatch) -> None:
    class FakeGitHubService:
        def get_pull_request_review_input(self, repository: str, number: int) -> dict:
            return {
                "repository": repository,
                "pull_request": {"number": number, "title": "Example PR"},
                "diff": "diff --git a/app/main.py b/app/main.py",
            }

        def close(self) -> None:
            pass

    class FakeAIReviewService:
        def review_pull_request(self, review_input: dict) -> AIReviewResult:
            return AIReviewResult(
                summary="Looks good.",
                risk="low",
                issues=[],
                tests_missing=[],
                recommendation="approve",
            )

        def close(self) -> None:
            pass

    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setenv("REVIEW_API_KEY", "test-review-key")
    monkeypatch.setattr("app.main.GitHubService", FakeGitHubService)
    monkeypatch.setattr("app.main.AIReviewService", FakeAIReviewService)

    response = client.post(
        "/reviews/Khumo-Hub/AI-PR-Reviewer-application/3",
        headers={"X-API-Key": "test-review-key"},
    )

    assert response.status_code == 200
    assert response.json()["review"]["recommendation"] == "approve"
    assert response.json()["review"]["risk"] == "low"


def test_outlook_draft_endpoint(monkeypatch) -> None:
    class FakeGitHubService:
        def get_pull_request_review_input(self, repository: str, number: int) -> dict:
            return {
                "repository": repository,
                "pull_request": {
                    "number": number,
                    "title": "Example PR",
                    "url": "https://github.com/example/repo/pull/4",
                },
                "diff": "diff --git a/app/main.py b/app/main.py",
            }

        def close(self) -> None:
            pass

    class FakeAIReviewService:
        def review_pull_request(self, review_input: dict) -> AIReviewResult:
            return AIReviewResult(
                summary="Looks good.",
                risk="low",
                issues=[],
                tests_missing=[],
                recommendation="approve",
            )

        def close(self) -> None:
            pass

    class FakeOutlookService:
        def create_review_draft(self, review_payload: dict) -> dict:
            assert review_payload["review"]["recommendation"] == "approve"
            return {
                "id": "draft-123",
                "subject": "PR Review",
                "is_draft": True,
                "web_link": "https://outlook.example/draft-123",
                "recipient": "reviewer@example.com",
            }

        def close(self) -> None:
            pass

    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )
    monkeypatch.setenv("REVIEW_API_KEY", "test-review-key")
    monkeypatch.setattr("app.main.GitHubService", FakeGitHubService)
    monkeypatch.setattr("app.main.AIReviewService", FakeAIReviewService)
    monkeypatch.setattr("app.main.OutlookService", FakeOutlookService)

    response = client.post(
        "/reviews/Khumo-Hub/AI-PR-Reviewer-application/4/outlook-draft",
        headers={"X-API-Key": "test-review-key"},
    )

    assert response.status_code == 200
    assert response.json()["review"]["recommendation"] == "approve"
    assert response.json()["outlook_draft"]["id"] == "draft-123"
    assert response.json()["outlook_draft"]["is_draft"] is True


def test_ai_review_endpoint_rejects_missing_key_before_services(monkeypatch) -> None:
    calls = {"github": 0, "ai": 0}

    class FailIfGitHubCalled:
        def __init__(self) -> None:
            calls["github"] += 1

    class FailIfAICalled:
        def __init__(self) -> None:
            calls["ai"] += 1

    monkeypatch.setenv("REVIEW_API_KEY", "test-review-key")
    monkeypatch.setattr("app.main.GitHubService", FailIfGitHubCalled)
    monkeypatch.setattr("app.main.AIReviewService", FailIfAICalled)

    response = client.post(
        "/reviews/Khumo-Hub/AI-PR-Reviewer-application/3"
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing review API key"}
    assert calls == {"github": 0, "ai": 0}


def test_ai_review_endpoint_rejects_wrong_key_before_services(monkeypatch) -> None:
    calls = {"github": 0}

    class FailIfGitHubCalled:
        def __init__(self) -> None:
            calls["github"] += 1

    monkeypatch.setenv("REVIEW_API_KEY", "test-review-key")
    monkeypatch.setattr("app.main.GitHubService", FailIfGitHubCalled)

    response = client.post(
        "/reviews/Khumo-Hub/AI-PR-Reviewer-application/3",
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401
    assert calls["github"] == 0


def test_ai_review_endpoint_requires_configured_key(monkeypatch) -> None:
    monkeypatch.delenv("REVIEW_API_KEY", raising=False)

    response = client.post(
        "/reviews/Khumo-Hub/AI-PR-Reviewer-application/3",
        headers={"X-API-Key": "some-key"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Review API key is not configured"}


def test_repository_must_be_allowed(monkeypatch) -> None:
    monkeypatch.setenv(
        "ALLOWED_GITHUB_REPOSITORIES",
        "Khumo-Hub/AI-PR-Reviewer-application",
    )

    response = client.get("/github/pull-requests/other/private-repo/1")

    assert response.status_code == 403
    assert response.json() == {"detail": "Repository is not allowed for review"}


def test_no_allowlist_defaults_to_deny(monkeypatch) -> None:
    monkeypatch.delenv("ALLOWED_GITHUB_REPOSITORIES", raising=False)

    response = client.get(
        "/github/pull-requests/Khumo-Hub/AI-PR-Reviewer-application/1"
    )

    assert response.status_code == 403


def test_pull_request_number_must_be_positive() -> None:
    response = client.get(
        "/github/pull-requests/Khumo-Hub/AI-PR-Reviewer-application/0"
    )
    assert response.status_code == 422
