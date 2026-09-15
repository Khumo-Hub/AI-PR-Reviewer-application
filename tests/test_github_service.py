import httpx
import pytest

from app.github_service import GitHubService, GitHubServiceError


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


@pytest.mark.parametrize(
    ("status_code", "headers", "expected_detail"),
    [
        (401, {}, "GitHub authentication failed"),
        (403, {}, "GitHub permissions failed"),
        (403, {"X-RateLimit-Remaining": "0"}, "GitHub API rate limit exceeded"),
        (404, {}, "GitHub pull request not found"),
    ],
)
def test_github_error_responses(
    status_code: int,
    headers: dict[str, str],
    expected_detail: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, headers=headers)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    github = GitHubService(client=client, base_url="https://api.github.test")

    with pytest.raises(GitHubServiceError) as exc_info:
        github.get_pull_request_metadata("Khumo-Hub/AI-PR-Reviewer-application", 1)

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == expected_detail


def test_network_failure_maps_to_bad_gateway() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    github = GitHubService(client=client, base_url="https://api.github.test")

    with pytest.raises(GitHubServiceError) as exc_info:
        github.get_pull_request_metadata("Khumo-Hub/AI-PR-Reviewer-application", 1)

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to reach the GitHub API"


def test_large_diff_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 11)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    github = GitHubService(
        client=client,
        base_url="https://api.github.test",
        max_diff_bytes=10,
    )

    with pytest.raises(GitHubServiceError) as exc_info:
        github.get_pull_request_diff("Khumo-Hub/AI-PR-Reviewer-application", 1)

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "Pull request diff is too large to review"


@pytest.mark.parametrize("value", ["not-a-number", "0", "-1"])
def test_invalid_max_diff_env_fails_closed(monkeypatch, value: str) -> None:
    monkeypatch.setenv("MAX_PR_DIFF_BYTES", value)

    with pytest.raises(GitHubServiceError) as exc_info:
        GitHubService(client=httpx.Client())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "MAX_PR_DIFF_BYTES must be a positive integer"


def test_explicit_zero_max_diff_is_rejected() -> None:
    with pytest.raises(GitHubServiceError) as exc_info:
        GitHubService(client=httpx.Client(), max_diff_bytes=0)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "MAX_PR_DIFF_BYTES must be a positive integer"
