from __future__ import annotations

import os
from typing import Any

import httpx


class GitHubServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _resolve_max_diff_bytes(explicit_value: int | None) -> int:
    raw_value: int | str = (
        explicit_value
        if explicit_value is not None
        else os.getenv("MAX_PR_DIFF_BYTES", "500000")
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise GitHubServiceError(
            503,
            "MAX_PR_DIFF_BYTES must be a positive integer",
        ) from exc
    if value <= 0:
        raise GitHubServiceError(503, "MAX_PR_DIFF_BYTES must be a positive integer")
    return value


class GitHubService:
    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = "https://api.github.com",
        max_diff_bytes: int | None = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.max_diff_bytes = _resolve_max_diff_bytes(max_diff_bytes)
        self.client = client or httpx.Client(timeout=15.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-pr-reviewer-application",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str, accept: str) -> httpx.Response:
        try:
            response = self.client.get(url, headers=self._headers(accept))
        except httpx.RequestError as exc:
            raise GitHubServiceError(502, "Unable to reach the GitHub API") from exc

        if response.status_code >= 400:
            if response.status_code == 404:
                detail = "GitHub pull request not found"
            elif response.status_code == 401:
                detail = "GitHub authentication failed"
            elif response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                detail = "GitHub API rate limit exceeded"
            elif response.status_code == 403:
                detail = "GitHub permissions failed"
            else:
                detail = f"GitHub API returned status {response.status_code}"

            status_code = response.status_code if response.status_code < 500 else 502
            raise GitHubServiceError(status_code, detail)

        return response

    def get_pull_request_metadata(self, repository: str, number: int) -> dict[str, Any]:
        url = f"{self.base_url}/repos/{repository}/pulls/{number}"
        response = self._get(url, "application/vnd.github+json")

        try:
            data = response.json()
            return {
                "number": data["number"],
                "title": data["title"],
                "state": data["state"],
                "url": data["html_url"],
                "author": data["user"]["login"],
                "base_branch": data["base"]["ref"],
                "head_branch": data["head"]["ref"],
                "head_sha": data["head"]["sha"],
                "mergeable": data.get("mergeable"),
                "changed_files": data.get("changed_files", 0),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubServiceError(502, "Unexpected response from the GitHub API") from exc

    def get_pull_request_diff(self, repository: str, number: int) -> str:
        url = f"{self.base_url}/repos/{repository}/pulls/{number}"
        response = self._get(url, "application/vnd.github.v3.diff")
        diff_bytes = response.content
        if len(diff_bytes) > self.max_diff_bytes:
            raise GitHubServiceError(413, "Pull request diff is too large to review")
        return response.text

    def get_pull_request_review_input(self, repository: str, number: int) -> dict[str, Any]:
        return {
            "repository": repository,
            "pull_request": self.get_pull_request_metadata(repository, number),
            "diff": self.get_pull_request_diff(repository, number),
        }
