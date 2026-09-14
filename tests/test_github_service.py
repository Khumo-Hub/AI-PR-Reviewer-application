import httpx

from app.github_service import GitHubService


def test_get_pull_request_review_input() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/Khumo-Hub/AI-PR-Reviewer-application/pulls/1"

        if request.headers["Accept"] == "application/vnd.github.v3.diff":
            return httpx.Response(200, text="diff --git a/app/main.py b/app/main.py")

        return httpx.Response(
            200,
            json={
                "number": 1,
                "title": "Example PR",
                "state": "open",
                "html_url": "https://github.com/Khumo-Hub/AI-PR-Reviewer-application/pull/1",
                "user": {"login": "Khumo-Hub"},
                "base": {"ref": "main"},
                "head": {"ref": "feature/example", "sha": "abc123"},
                "mergeable": True,
                "changed_files": 2,
                "additions": 12,
                "deletions": 3,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    github = GitHubService(client=client, base_url="https://api.github.test")

    result = github.get_pull_request_review_input(
        "Khumo-Hub/AI-PR-Reviewer-application",
        1,
    )

    assert result["repository"] == "Khumo-Hub/AI-PR-Reviewer-application"
    assert result["pull_request"]["title"] == "Example PR"
    assert result["pull_request"]["head_sha"] == "abc123"
    assert result["diff"].startswith("diff --git")
