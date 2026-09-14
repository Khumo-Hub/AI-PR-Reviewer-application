from fastapi.testclient import TestClient

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

    monkeypatch.setattr("app.main.GitHubService", FakeGitHubService)

    response = client.get(
        "/github/pull-requests/Khumo-Hub/AI-PR-Reviewer-application/1"
    )

    assert response.status_code == 200
    assert response.json()["repository"] == "Khumo-Hub/AI-PR-Reviewer-application"
    assert response.json()["pull_request"]["number"] == 1


def test_pull_request_number_must_be_positive() -> None:
    response = client.get(
        "/github/pull-requests/Khumo-Hub/AI-PR-Reviewer-application/0"
    )
    assert response.status_code == 422
