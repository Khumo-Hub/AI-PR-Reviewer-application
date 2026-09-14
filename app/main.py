from fastapi import FastAPI, HTTPException

from app.github_service import GitHubService, GitHubServiceError

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.2.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI PR Reviewer is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/github/pull-requests/{owner}/{repo}/{pr_number}")
def get_pull_request(owner: str, repo: str, pr_number: int) -> dict:
    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    github = GitHubService()
    try:
        return github.get_pull_request_review_input(f"{owner}/{repo}", pr_number)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        github.close()
